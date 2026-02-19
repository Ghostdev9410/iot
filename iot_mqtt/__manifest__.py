# Copyright 2024 Odoo Community Association (OCA)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "IoT MQTT",
    "summary": "MQTT Protocol support for IoT devices",
    "version": "18.0.1.0.0",
    "category": "IoT",
    "website": "https://github.com/OCA/iot",
    "author": "Odoo Community Association (OCA)",
    "license": "AGPL-3",
    "application": False,
    "installable": True,
    "depends": ["iot_oca"],
    "data": [
        "security/ir.model.access.csv",
        "data/iot_system_data.xml",
        "views/iot_mqtt_broker_views.xml",
        "views/iot_device_views.xml",
    ],
}
