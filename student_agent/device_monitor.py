import subprocess
import time
import threading
from datetime import datetime


class USBDeviceMonitor:
    def __init__(self, on_change_callback=None):
        self.on_change_callback = on_change_callback
        self.running = False
        self.known_devices = set()

    def get_connected_usb_devices(self):
        try:
            command = [
                "powershell",
                "-Command",
                "Get-PnpDevice | Where-Object {$_.Status -eq 'OK'} | "
                "Where-Object {$_.Class -in @('USB','HIDClass','Mouse','Keyboard')} | "
                "Select-Object -ExpandProperty FriendlyName"
            ]

            result = subprocess.check_output(command, text=True)
            devices = set()

            for line in result.split("\n"):
                line = line.strip()
                if line:
                    devices.add(line)

            return devices

        except Exception as e:
            print("Error fetching devices:", e)
            return set()


    def start(self):
        self.running = True
        self.known_devices = self.get_connected_usb_devices()
        thread = threading.Thread(target=self.monitor_loop, daemon=True)
        thread.start()

    def stop(self):
        self.running = False

    def monitor_loop(self):
        while self.running:
            current_devices = self.get_connected_usb_devices()

            connected = current_devices - self.known_devices
            for device in connected:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"[CONNECTED] {device} at {timestamp}")
                if self.on_change_callback:
                    self.on_change_callback(device, "connected", timestamp)

            disconnected = self.known_devices - current_devices
            for device in disconnected:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"[DISCONNECTED] {device} at {timestamp}")
                if self.on_change_callback:
                    self.on_change_callback(device, "disconnected", timestamp)

            self.known_devices = current_devices
            time.sleep(2)
