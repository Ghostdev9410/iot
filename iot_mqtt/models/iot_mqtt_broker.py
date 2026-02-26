# Copyright 2024 Odoo Community Association (OCA)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging
import threading

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.modules.registry import Registry

_logger = logging.getLogger(__name__)

# Global registry to keep track of running MQTT clients
# Key: broker_id, Value: mqtt.Client instance
_MQTT_CLIENTS = {}


class IotMqttBroker(models.Model):
    _name = "iot.mqtt.broker"
    _description = "MQTT Broker"

    name = fields.Char(required=True)
    host = fields.Char(required=True, default="localhost")
    port = fields.Integer(required=True, default=1883)
    username = fields.Char()
    password = fields.Char()
    use_ssl = fields.Boolean(string="Use SSL/TLS")

    is_listening = fields.Boolean(string="Listening", compute="_compute_is_listening")

    # Embedded broker configuration (future use)

    def _compute_is_listening(self):
        for rec in self:
            rec.is_listening = rec.id in _MQTT_CLIENTS

    @staticmethod
    def _on_connect_callback(client, userdata, flags, rc, properties=None, env=None):
        broker_name = userdata.get("broker_name", "Unknown")
        if rc == 0:
            _logger.info("MQTT Broker %s connected via Thread.", broker_name)
            try:
                if env:
                    devices = env["iot.device"].search(
                        [("mqtt_broker_id", "=", userdata["broker_id"])]
                    )
                    for dev in devices:
                        if dev.mqtt_topic:
                            client.subscribe(dev.mqtt_topic, qos=int(dev.mqtt_qos or 0))
                else:
                    dbname = userdata["dbname"]
                    uid = userdata["uid"]
                    broker_id = userdata["broker_id"]

                    db_registry = Registry(dbname)
                    with db_registry.cursor() as cr:
                        env = api.Environment(cr, uid, {})
                        devices = env["iot.device"].search(
                            [("mqtt_broker_id", "=", broker_id)]
                        )
                        for dev in devices:
                            if dev.mqtt_topic:
                                _logger.info("Subscribing to %s", dev.mqtt_topic)
                                client.subscribe(
                                    dev.mqtt_topic, qos=int(dev.mqtt_qos or 0)
                                )
            except Exception as e:
                _logger.error("Error in on_connect subscription: %s", e)
        else:
            _logger.error("MQTT Connection failed with code %s", rc)

    @staticmethod
    def _on_message_callback(client, userdata, msg, env=None):
        payload = msg.payload.decode("utf-8")
        topic = msg.topic
        _logger.info("MQTT MSG IN: %s -> %s", topic, payload)

        try:

            def process_message(env):
                devices = env["iot.device"].search(
                    [
                        ("mqtt_broker_id", "=", userdata["broker_id"]),
                        ("mqtt_topic", "=", topic),
                    ]
                )
                for dev in devices:
                    env["iot.mqtt.message"].create(
                        {
                            "device_id": dev.id,
                            "direction": "in",
                            "topic": topic,
                            "payload": payload,
                            "qos": str(msg.qos),
                        }
                    )
                    dev.write({"last_contact_date": fields.Datetime.now()})

            if env:
                process_message(env)
            else:
                dbname = userdata["dbname"]
                uid = userdata["uid"]

                db_registry = Registry(dbname)
                with db_registry.cursor() as cr:
                    env = api.Environment(cr, uid, {})
                    process_message(env)
                    cr.commit()  # pylint: disable=invalid-commit

        except Exception as e:
            _logger.error("Error processing MQTT message: %s", e)

    def action_start_listener(self):
        """Starts a background thread to listen for messages."""
        self.ensure_one()
        # paho-mqtt is imported inside the method to avoid ImportError
        # when the library is not installed (optional dependency).
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            raise UserError(_("paho-mqtt library not installed.")) from None

        self.action_stop_listener()

        # Context for callbacks to avoid thread-safety issues with 'self'
        mqtt_userdata = {
            "dbname": self.env.cr.dbname,
            "uid": self.env.uid,
            "broker_id": self.id,
            "broker_name": self.name,
        }

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, userdata=mqtt_userdata)

        if self.username:
            client.username_pw_set(self.username, self.password)
        if self.use_ssl:
            client.tls_set()

        client.on_connect = self._on_connect_callback
        client.on_message = self._on_message_callback

        try:
            client.connect(self.host, self.port, keepalive=60)
            client.loop_start()
            _MQTT_CLIENTS[self.id] = client
            return True
        except Exception as e:
            raise UserError(_("Could not start listener: %s") % e) from e

    def action_stop_listener(self):
        """Stops the background listener."""
        self.ensure_one()
        if self.id in _MQTT_CLIENTS:
            client = _MQTT_CLIENTS[self.id]
            client.loop_stop()
            client.disconnect()
            del _MQTT_CLIENTS[self.id]
        return True

    def action_test_connection(self):
        """Test the connection to the MQTT broker."""
        self.ensure_one()
        # paho-mqtt is imported inside the method to avoid ImportError
        # when the library is not installed (optional dependency).
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            raise UserError(
                _(
                    "The paho-mqtt library is not installed. "
                    "Please install it to use MQTT features."
                )
            ) from None

        connected_event = threading.Event()

        def _on_connect_test(client, userdata, flags, rc, properties=None):
            if rc == 0:
                connected_event.set()

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.on_connect = _on_connect_test

        if self.username:
            client.username_pw_set(self.username, self.password)

        if self.use_ssl:
            client.tls_set()

        try:
            client.connect(self.host, self.port, keepalive=5)
            client.loop_start()

            if connected_event.wait(timeout=5):
                return {
                    "type": "ir.actions.client",
                    "tag": "display_notification",
                    "params": {
                        "title": _("Connection Successful"),
                        "message": _(
                            "Successfully connected to MQTT broker at %(host)s:%(port)s"
                        )
                        % {"host": self.host, "port": self.port},
                        "type": "success",
                        "sticky": False,
                    },
                }
            else:
                raise UserError(
                    _("Could not connect to MQTT broker at %(host)s:%(port)s. Timeout.")
                    % {"host": self.host, "port": self.port}
                )

        except Exception as e:
            raise UserError(_("Failed to connect to MQTT broker: %s") % str(e)) from e
        finally:
            client.loop_stop()
            client.disconnect()
