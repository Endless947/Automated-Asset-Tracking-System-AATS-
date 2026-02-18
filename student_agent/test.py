from device_monitor import USBDeviceMonitor

def callback(device, status, timestamp):
    print(f"Callback -> {device} {status} at {timestamp}")

monitor = USBDeviceMonitor(on_change_callback=callback)
monitor.start()

input("Monitoring... Press Enter to stop.\n")
