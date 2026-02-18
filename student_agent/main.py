from device_monitor import USBDeviceMonitor
from mqtt_client import MQTTClient
import json
import threading
import time
import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(BASE_DIR, "config.json")

with open(config_path) as f:
    config = json.load(f)


mqtt_client = MQTTClient(
    broker=config["mqtt_broker"],
    port=config["port"],
    lab_id=config["lab_id"],
    pc_id=config["pc_id"]
)

mqtt_client.connect()


def device_callback(device, status, timestamp):
    mqtt_client.publish_status(device, status, timestamp)


monitor = USBDeviceMonitor(on_change_callback=device_callback)
monitor.start()


# Heartbeat thread
def heartbeat_loop():
    while True:
        mqtt_client.send_heartbeat()
        time.sleep(30)


threading.Thread(target=heartbeat_loop, daemon=True).start()


print("Student Agent Running...")
while True:
    time.sleep(1)
