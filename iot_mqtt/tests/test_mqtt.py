# Copyright 2024 Odoo Community Association (OCA)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from unittest.mock import MagicMock, patch

from odoo import fields
from odoo.tests.common import TransactionCase


class TestMqttCallbacks(TransactionCase):
    def setUp(self):
        super().setUp()
        # Create Infrastructure
        self.broker = self.env["iot.mqtt.broker"].create(
            {"name": "Test Broker", "host": "test.mosquitto.org", "port": 1883}
        )
        self.system = self.env["iot.communication.system"].create({"name": "MQTT"})
        self.device = self.env["iot.device"].create(
            {
                "name": "Test Device",
                "communication_system_id": self.system.id,
                "mqtt_broker_id": self.broker.id,
                "mqtt_topic": "test/topic",
                "mqtt_qos": "1",
            }
        )

    def test_on_message_callback_logic(self):
        """Test that _on_message_callback correctly creates log
        and updates heartbeat.
        """
        userdata = {
            "dbname": self.env.cr.dbname,
            "uid": self.env.uid,
            "broker_id": self.broker.id,
            "broker_name": self.broker.name,
        }

        mock_msg = MagicMock()
        mock_msg.topic = "test/topic"
        mock_msg.payload = b'{"temp": 25}'
        mock_msg.qos = 1

        before_process = fields.Datetime.now()

        # Pass env=self.env to use the test transaction
        self.env["iot.mqtt.broker"]._on_message_callback(
            MagicMock(), userdata, mock_msg, env=self.env
        )

        logs = self.env["iot.mqtt.message"].search([("device_id", "=", self.device.id)])
        self.assertEqual(len(logs), 1, "Should have created exactly one log message")
        self.assertEqual(logs.payload, '{"temp": 25}')
        self.assertEqual(logs.direction, "in")

        self.device.invalidate_recordset()
        self.assertTrue(
            self.device.last_contact_date >= before_process,
            "Last contact date should be updated",
        )

    @patch("paho.mqtt.client.Client")
    def test_publish_action(self, mock_mqtt_client_cls):
        """Test that the publish action initializes client and calls publish."""
        mock_client_instance = mock_mqtt_client_cls.return_value
        mock_client_instance.publish.return_value.wait_for_publish.return_value = None

        self.device.mqtt_test_payload = '{"cmd": "ping"}'
        self.device.action_mqtt_publish_test()

        mock_mqtt_client_cls.assert_called()
        mock_client_instance.connect.assert_called_with(
            "test.mosquitto.org", 1883, keepalive=10
        )
        mock_client_instance.publish.assert_called()

        args, _ = mock_client_instance.publish.call_args
        self.assertEqual(args[0], "test/topic")
        self.assertIn("ping", args[1])

        logs = self.env["iot.mqtt.message"].search(
            [("device_id", "=", self.device.id), ("direction", "=", "out")]
        )
        self.assertEqual(len(logs), 1, "Should have created one OUT log")

    @patch("paho.mqtt.client.Client")
    def test_start_stop_listener(self, mock_mqtt_client_cls):
        """Test that start/stop listener manages the global client registry."""
        from ..models.iot_mqtt_broker import _MQTT_CLIENTS

        mock_client_instance = mock_mqtt_client_cls.return_value

        self.broker.action_start_listener()

        self.assertIn(self.broker.id, _MQTT_CLIENTS)
        mock_client_instance.connect.assert_called_with(
            "test.mosquitto.org", 1883, keepalive=60
        )
        mock_client_instance.loop_start.assert_called_once()

        self.broker.action_stop_listener()

        self.assertNotIn(self.broker.id, _MQTT_CLIENTS)
        mock_client_instance.loop_stop.assert_called_once()
        mock_client_instance.disconnect.assert_called_once()

    def test_on_connect_callback_subscribes(self):
        """Test that _on_connect_callback subscribes to device topics."""
        userdata = {
            "dbname": self.env.cr.dbname,
            "uid": self.env.uid,
            "broker_id": self.broker.id,
            "broker_name": self.broker.name,
        }
        mock_client = MagicMock()

        # Pass env=self.env to use the test transaction
        self.env["iot.mqtt.broker"]._on_connect_callback(
            mock_client, userdata, {}, 0, env=self.env
        )

        mock_client.subscribe.assert_called_once_with("test/topic", qos=1)

    @patch("paho.mqtt.client.Client")
    def test_connection_success(self, mock_mqtt_client_cls):
        """Test that action_test_connection returns success notification."""
        mock_client_instance = mock_mqtt_client_cls.return_value

        # Simulate the on_connect callback being fired (sets the Event)
        def fake_connect(host, port, keepalive=5):
            # Trigger on_connect callback to set the threading.Event
            if mock_client_instance.on_connect:
                mock_client_instance.on_connect(mock_client_instance, None, {}, 0)

        mock_client_instance.connect.side_effect = fake_connect

        result = self.broker.action_test_connection()

        self.assertEqual(result["type"], "ir.actions.client")
        self.assertEqual(result["tag"], "display_notification")
        self.assertEqual(result["params"]["type"], "success")
        mock_client_instance.loop_stop.assert_called_once()
        mock_client_instance.disconnect.assert_called_once()

    def test_clear_messages(self):
        """Test that action_clear_messages removes all MQTT messages."""
        self.env["iot.mqtt.message"].create(
            {
                "device_id": self.device.id,
                "direction": "in",
                "topic": "test/topic",
                "payload": "test1",
            }
        )
        self.env["iot.mqtt.message"].create(
            {
                "device_id": self.device.id,
                "direction": "out",
                "topic": "test/topic",
                "payload": "test2",
            }
        )

        self.assertEqual(len(self.device.mqtt_message_ids), 2)

        self.device.action_clear_messages()

        self.device.invalidate_recordset()
        self.assertEqual(len(self.device.mqtt_message_ids), 0)
