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
