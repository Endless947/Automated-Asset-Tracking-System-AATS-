import subprocess
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class USBDeviceMonitor:
    def __init__(
        self,
        tracked_devices: List[Dict],
        poll_interval_sec: int = 2,
        on_change_callback: Optional[Callable[[Dict], None]] = None,
    ) -> None:
        self.tracked_devices = tracked_devices
        self.poll_interval_sec = poll_interval_sec
        self.on_change_callback = on_change_callback
        self.running = False
        self._state: Dict[str, str] = {}

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _get_present_instance_ids(self) -> List[str]:
        command = [
            "powershell",
            "-Command",
            "Get-PnpDevice -PresentOnly | Select-Object -ExpandProperty InstanceId",
        ]
        try:
            output = subprocess.check_output(
                command,
                text=True,
                timeout=10,
                creationflags=CREATE_NO_WINDOW,
            )
            return [line.strip().lower() for line in output.splitlines() if line.strip()]
        except Exception as exc:
            print(f"USB scan error: {exc}")
            return []

    def _is_connected(self, instance_ids: List[str], vid: str, pid: str) -> bool:
        marker = f"vid_{vid.lower()}&pid_{pid.lower()}"
        return any(marker in instance_id for instance_id in instance_ids)

    def _emit(self, payload: Dict) -> None:
        if self.on_change_callback:
            self.on_change_callback(payload)

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        thread = threading.Thread(target=self._monitor_loop, daemon=True)
        thread.start()

    def stop(self) -> None:
        self.running = False

    def _monitor_loop(self) -> None:
        while self.running:
            instance_ids = self._get_present_instance_ids()

            for device in self.tracked_devices:
                device_id = device["device_id"]
                vid = device["vid"]
                pid = device["pid"]
                alias = device.get("alias", device_id)

                connected = self._is_connected(instance_ids, vid, pid)
                new_status = "CONNECTED" if connected else "MISSING"
                old_status = self._state.get(device_id)

                if old_status != new_status:
                    self._state[device_id] = new_status
                    self._emit(
                        {
                            "device_id": device_id,
                            "device_label": alias,
                            "device_type": "usb",
                            "status": new_status,
                            "rssi": None,
                            "observed_at": self._now(),
                            "source": "usb_monitor",
                        }
                    )

            time.sleep(self.poll_interval_sec)
