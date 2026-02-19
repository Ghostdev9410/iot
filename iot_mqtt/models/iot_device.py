# Copyright 2024 Odoo Community Association (OCA)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models


class IotDevice(models.Model):
    _inherit = "iot.device"

    mqtt_broker_id = fields.Many2one("iot.mqtt.broker", string="MQTT Broker")
    mqtt_broker_is_listening = fields.Boolean(
        related="mqtt_broker_id.is_listening", string="Listener Active", readonly=True
    )
    mqtt_topic = fields.Char(string="MQTT Topic")
    mqtt_qos = fields.Selection(
        [
            ("0", "0 - At most once"),
            ("1", "1 - At least once"),
            ("2", "2 - Exactly once"),
        ],
        string="QoS",
        default="0",
    )

    # Message Log & Testing
    mqtt_message_ids = fields.One2many(
        "iot.mqtt.message", "device_id", string="MQTT Messages"
    )
    mqtt_test_payload = fields.Text(string="Test Payload", default='{"action": "test"}')

    def action_mqtt_publish_test(self):
        self.ensure_one()
        if not self.mqtt_broker_id:
            raise models.UserError(_("Please select an MQTT Broker first."))
        if not self.mqtt_topic:
            raise models.UserError(_("Please set an MQTT Topic."))

        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            raise models.UserError(_("paho-mqtt library not installed.")) from None

        broker = self.mqtt_broker_id
        client = mqtt.Client(protocol=mqtt.MQTTv311)

        if broker.username:
            client.username_pw_set(broker.username, broker.password)
        if broker.use_ssl:
            client.tls_set()

        try:
            client.connect(broker.host, broker.port, keepalive=10)
            client.loop_start()

            info = client.publish(
                self.mqtt_topic, self.mqtt_test_payload, qos=int(self.mqtt_qos)
            )
            info.wait_for_publish(timeout=5)

            if info.is_published():
                self.env["iot.mqtt.message"].create(
                    {
                        "device_id": self.id,
                        "direction": "out",
                        "topic": self.mqtt_topic,
                        "payload": self.mqtt_test_payload,
                        "qos": self.mqtt_qos,
                    }
                )

                return True
            else:
                raise models.UserError(_("Publish timed out."))

        except Exception as e:
            raise models.UserError(_("MQTT Publish Error: %s") % e) from e
        finally:
            client.loop_stop()
            client.disconnect()

    def action_clear_messages(self):
        self.ensure_one()
        self.mqtt_message_ids.unlink()
        return True

    @api.onchange("communication_system_id")
    def _onchange_communication_system(self):
        # Optional: Auto-set defaults if system is MQTT
        # Need to identify if the selected system is MQTT.
        # This logic might need to check the system name or a new type field on system.
        pass
