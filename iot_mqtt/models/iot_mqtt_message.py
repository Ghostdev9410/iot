# Copyright 2024 Odoo Community Association (OCA)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models


class IotMqttMessage(models.Model):
    _name = "iot.mqtt.message"
    _description = "MQTT Message Log"
    _order = "create_date desc"

    device_id = fields.Many2one("iot.device", ondelete="cascade", required=True)
    direction = fields.Selection(
        [("in", "Received (IN)"), ("out", "Sent (OUT)")],
        required=True,
    )

    topic = fields.Char(required=True)
    payload = fields.Text()
    qos = fields.Selection([("0", "0"), ("1", "1"), ("2", "2")])
    is_retained = fields.Boolean(string="Retained")
