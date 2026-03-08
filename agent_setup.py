"""
AATS Agent Setup & Launcher
============================
Place this file in the ROOT of your AATS project (same level as student_agent/).

To build into EXE:
    pip install pyinstaller
    pyinstaller --onefile agent_setup.py

On first run  : detects admin IP, scans USB devices, writes config.json, registers
                auto-start on Windows boot, then launches the agent.
On later runs : skips setup and launches the agent directly.
"""

import json
import os
import socket
import subprocess
import sys
import time
import winreg

# ── Configuration ──────────────────────────────────────────
BROADCAST_PORT    = 37020
BROADCAST_MSG     = "AATS_ADMIN"
BROADCAST_TIMEOUT = 30   # seconds to wait for admin broadcast before asking manually
STARTUP_REG_NAME  = "AATSAgent"
STARTUP_REG_KEY   = r"Software\Microsoft\Windows\CurrentVersion\Run"
# ───────────────────────────────────────────────────────────


def get_base_dir() -> str:
    """Project root — works both as .py and as PyInstaller EXE."""
    path = os.path.dirname(os.path.abspath(sys.argv[0]))
    if getattr(sys, "frozen", False):
        path = os.path.dirname(path)  # go up from dist/ to project root
    return path


def get_python() -> str:
    """Get real python.exe — needed when running as a PyInstaller EXE."""
    if getattr(sys, "frozen", False):
        result = subprocess.run(
            ["where", "python"], capture_output=True, text=True
        )
        lines = result.stdout.strip().splitlines()
        if lines:
            return lines[0]
        print("[!] Python not found on PATH. Please install Python.")
        input("Press Enter to exit...")
        sys.exit(1)
    return sys.executable


def config_path(base_dir: str) -> str:
    return os.path.join(base_dir, "student_agent", "config.json")


def is_setup_done(base_dir: str) -> bool:
    """Check if config.json already exists and has a real broker IP."""
    path = config_path(base_dir)
    if not os.path.exists(path):
        return False
    try:
        with open(path) as f:
            cfg = json.load(f)
        broker = cfg.get("broker", "")
        return broker not in ("", "localhost", "127.0.0.1")
    except Exception:
        return False


# ── Uninstall ───────────────────────────────────────────────

def unregister_autostart() -> None:
    """Remove agent from Windows registry auto-start."""
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, STARTUP_REG_KEY, 0, winreg.KEY_SET_VALUE
        )
        winreg.DeleteValue(key, STARTUP_REG_NAME)
        winreg.CloseKey(key)
        print("[+] Agent removed from auto-start.")
    except FileNotFoundError:
        print("[!] Agent was not registered for auto-start.")
    except Exception as e:
        print(f"[!] Could not remove auto-start: {e}")


def uninstall(base_dir: str) -> None:
    """Remove auto-start registration and clear config.json."""
    print("\n[*] Uninstalling AATS Agent...")
    unregister_autostart()

    cfg = config_path(base_dir)
    if os.path.exists(cfg):
        os.remove(cfg)
        print("[+] config.json cleared.")
    else:
        print("[!] No config.json found — nothing to clear.")

    print("\n[+] Uninstall complete.")
    print("    The agent will no longer start on boot.")
    print("    You can delete the project folder manually if needed.")
    input("\nPress Enter to exit...")


# ── Step 1: Discover Admin IP ───────────────────────────────

def listen_for_broadcast() -> str | None:
    """Listen for UDP broadcast from admin EXE. Returns IP or None on timeout."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(1)
    try:
        sock.bind(("", BROADCAST_PORT))
    except OSError:
        print("[!] Could not bind to broadcast port — may already be in use.")
        return None

    print(f"[*] Listening for Admin PC broadcast for up to {BROADCAST_TIMEOUT}s...")
    deadline = time.time() + BROADCAST_TIMEOUT
    while time.time() < deadline:
        try:
            data, _ = sock.recvfrom(1024)
            msg = data.decode()
            if msg.startswith(f"{BROADCAST_MSG}:"):
                ip = msg.split(":", 1)[1]
                print(f"[+] Admin PC found at: {ip}")
                return ip
        except socket.timeout:
            remaining = int(deadline - time.time())
            print(f"    Still searching... ({remaining}s left)", end="\r")
    print()
    return None


def get_admin_ip() -> str:
    """Try broadcast first, fall back to manual input."""
    ip = listen_for_broadcast()
    if ip:
        return ip
    print("\n[!] Could not find Admin PC automatically.")
    while True:
        ip = input("    Please type the Admin PC IP address manually: ").strip()
        if ip:
            return ip


# ── Step 2: Get PC ID ───────────────────────────────────────

def get_pc_id() -> str:
    while True:
        pc_id = input("[?] Enter a unique PC ID for this machine (e.g. PC01): ").strip()
        if pc_id:
            return pc_id


# ── Step 3: Scan USB Devices ────────────────────────────────

def scan_usb_devices() -> list[dict]:
    """Use PowerShell to list connected USB HID devices with VID/PID."""
    print("[*] Scanning connected USB devices...")
    ps_cmd = (
        "Get-PnpDevice -Class HIDClass | "
        "Where-Object {$_.Status -eq 'OK'} | "
        "Select-Object FriendlyName, DeviceID | "
        "ConvertTo-Json"
    )
    result = subprocess.run(
        ["powershell", "-Command", ps_cmd],
        capture_output=True, text=True
    )
    devices = []
    try:
        raw = json.loads(result.stdout)
        if isinstance(raw, dict):
            raw = [raw]
        for item in raw:
            name = item.get("FriendlyName", "Unknown")
            dev_id = item.get("DeviceID", "")
            vid, pid = "", ""
            for part in dev_id.upper().split("\\"):
                if "VID_" in part and "PID_" in part:
                    for segment in part.split("&"):
                        if segment.startswith("VID_"):
                            vid = segment[4:8].lower()
                        elif segment.startswith("PID_"):
                            pid = segment[4:8].lower()
            if vid and pid:
                devices.append({"name": name, "vid": vid, "pid": pid})
    except Exception:
        pass
    return devices


def pick_usb_devices(devices: list[dict]) -> list[dict]:
    """Show device list and let user pick which ones to monitor."""
    if not devices:
        print("[!] No USB HID devices found. Skipping USB monitoring.")
        return []

    print("\n[*] Connected USB devices found:")
    for i, d in enumerate(devices):
        print(f"    {i + 1}. {d['name']} (VID:{d['vid']} PID:{d['pid']})")

    print("\n[?] Enter the numbers of devices to monitor (e.g. 1,3) or press Enter to skip:")
    selection = input("    > ").strip()

    if not selection:
        return []

    chosen = []
    for part in selection.split(","):
        try:
            idx = int(part.strip()) - 1
            if 0 <= idx < len(devices):
                d = devices[idx]
                chosen.append({
                    "device_id": d["name"].lower().replace(" ", "_"),
                    "vid": d["vid"],
                    "pid": d["pid"],
                    "alias": d["name"],
                })
        except ValueError:
            pass
    return chosen


# ── Step 4: Write config.json ───────────────────────────────

def write_config(base_dir: str, admin_ip: str, pc_id: str, usb_devices: list[dict]) -> None:
    cfg = {
        "lab_id": "LAB1",
        "pc_id": pc_id,
        "broker": admin_ip,
        "port": 1883,
        "scan_interval_sec": 2,
        "heartbeat_interval_sec": 30,
        "agent_version": "1.0.0",
        "usb_devices": usb_devices,
        "bluetooth_devices": []
    }
    path = config_path(base_dir)
    with open(path, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"[+] config.json written.")


# ── Step 5: Register auto-start on Windows boot ─────────────

def register_autostart(base_dir: str) -> None:
    """Add agent to Windows registry so it starts on every boot."""
    main_py = os.path.join(base_dir, "student_agent", "main.py")
    python  = get_python()
    command = f'"{python}" "{main_py}"'
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, STARTUP_REG_KEY, 0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, STARTUP_REG_NAME, 0, winreg.REG_SZ, command)
        winreg.CloseKey(key)
        print("[+] Agent registered to auto-start on Windows boot.")
    except Exception as e:
        print(f"[!] Could not register auto-start: {e}")


# ── Step 6: Launch the agent ────────────────────────────────

def launch_agent(base_dir: str) -> None:
    """Start the student agent and wait for it."""
    main_py   = os.path.join(base_dir, "student_agent", "main.py")
    agent_dir = os.path.join(base_dir, "student_agent")
    python    = get_python()

    print("[*] Starting agent...")
    proc = subprocess.Popen(
        [python, main_py],
        cwd=agent_dir,
    )
    print("[+] Agent is running! Close this window to stop the agent.\n")
    proc.wait()


# ── Main ────────────────────────────────────────────────────

def main() -> None:
    print("=" * 52)
    print("         AATS — Agent Setup & Launcher")
    print("=" * 52)
    print("\n  1. Run / Setup agent")
    print("  2. Uninstall agent (remove auto-start + clear config)")

    choice = input("\n  Choose (1/2): ").strip()

    base_dir = get_base_dir()

    if choice == "2":
        uninstall(base_dir)
        return

    # ── Run / Setup ──────────────────────────────────────────
    if is_setup_done(base_dir):
        print("\n[+] Setup already complete. Launching agent...\n")
        launch_agent(base_dir)
        return

    print("\n[*] First time setup — let's get this PC configured!\n")

    # Step 1 — Find Admin PC
    admin_ip = get_admin_ip()

    # Step 2 — PC ID
    pc_id = get_pc_id()

    # Step 3 — Scan and pick USB devices
    usb_devices_raw = scan_usb_devices()
    usb_devices     = pick_usb_devices(usb_devices_raw)

    # Step 4 — Write config.json
    write_config(base_dir, admin_ip, pc_id, usb_devices)

    # Step 5 — Register auto-start on boot
    register_autostart(base_dir)

    print("\n" + "=" * 52)
    print("  Setup complete!")
    print(f"  Admin IP  : {admin_ip}")
    print(f"  PC ID     : {pc_id}")
    print(f"  Devices   : {len(usb_devices)} USB device(s) configured")
    print("  Auto-start: registered for Windows boot")
    print("=" * 52 + "\n")

    # Step 6 — Launch agent
    launch_agent(base_dir)


if __name__ == "__main__":
    main()