To use this module with an IoT Device:

1.  Go to **IoT > Devices**.
2.  Select or create a Device.
3.  In the **MQTT Configuration** tab:
    *   Select the **MQTT Broker**.
    *   Set the **MQTT Topic** (e.g., `sensor/temp/01`).
    *   Set the **QoS** level.
4.  Once the Listener is active on the Broker, any message sent to this topic will be logged in the device's **MQTT Messages** tab.
5.  You can also send a test message from Odoo to the device using the **Publish Test** button.
