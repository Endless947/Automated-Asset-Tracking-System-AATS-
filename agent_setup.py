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
import ctypes

# ── Configuration ──────────────────────────────────────────
BROADCAST_PORT    = 37020
BROADCAST_MSG     = "AATS_ADMIN"
BROADCAST_TIMEOUT = 30   # seconds to wait for admin broadcast before asking manually
STARTUP_REG_NAME  = "AATSAgent"
STARTUP_REG_KEY   = r"Software\Microsoft\Windows\CurrentVersion\Run"
AGENT_SERVICE_NAME = "AATSAgentService"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
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


def is_admin() -> bool:
    """Check if process has Administrator privileges."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


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


def service_exists() -> bool:
    """Return True if the Windows service already exists."""
    result = subprocess.run(["sc", "query", AGENT_SERVICE_NAME], capture_output=True, text=True)
    return result.returncode == 0 and "does not exist" not in result.stdout.lower()


def setup_windows_service(base_dir: str) -> bool:
    """Install (if needed) and start the agent as a Windows service."""
    if not is_admin():
        print("[!] Not running as Administrator; cannot configure Windows service.")
        return False

    service_script = os.path.join(base_dir, "student_agent", "windows_service.py")
    service_dir = os.path.join(base_dir, "student_agent")
    python = get_python()

    if not os.path.exists(service_script):
        print("[!] windows_service.py not found; skipping service setup.")
        return False

    if not service_exists():
        print("[*] Installing AATS Windows service...")
        install = subprocess.run([python, service_script, "install"], cwd=service_dir)
        if install.returncode != 0:
            print("[!] Service installation failed.")
            return False

    print("[*] Starting AATS Windows service...")
    start = subprocess.run([python, service_script, "start"], cwd=service_dir)
    if start.returncode != 0:
        print("[!] Service start failed.")
        return False

    print("[+] Windows service is running.")
    return True


def uninstall(base_dir: str) -> None:
    """Remove auto-start registration and clear config.json."""
    print("\n[*] Uninstalling AATS Agent...")
    if is_admin() and service_exists():
        service_script = os.path.join(base_dir, "student_agent", "windows_service.py")
        service_dir = os.path.join(base_dir, "student_agent")
        python = get_python()
        print("[*] Removing Windows service...")
        subprocess.run([python, service_script, "stop"], cwd=service_dir)
        subprocess.run([python, service_script, "remove"], cwd=service_dir)

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
        capture_output=True,
        text=True,
        creationflags=CREATE_NO_WINDOW,
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


def setup_startup_mode(base_dir: str) -> str:
    """
    Prefer Windows service for true boot-time resilience.
    Fall back to user logon auto-start via registry.
    """
    if setup_windows_service(base_dir):
        # Service startup makes Run-key startup redundant.
        unregister_autostart()
        return "service"

    register_autostart(base_dir)
    return "registry"


def get_startup_status() -> str:
    """Return a user-facing startup mode status string."""
    if service_exists():
        return "Windows service (starts at boot, no user login required)"

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, STARTUP_REG_KEY, 0, winreg.KEY_READ
        )
        winreg.QueryValueEx(key, STARTUP_REG_NAME)
        winreg.CloseKey(key)
        return "Registry startup (starts after this user logs in)"
    except Exception:
        return "Not configured"


# ── Step 6: Launch the agent ────────────────────────────────

def launch_agent(base_dir: str) -> None:
    """Start the student agent detached so setup window can be closed."""
    main_py   = os.path.join(base_dir, "student_agent", "main.py")
    agent_dir = os.path.join(base_dir, "student_agent")
    python    = get_python()

    print("[*] Starting agent...")
    detached = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
    new_group = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    subprocess.Popen(
        [python, main_py],
        cwd=agent_dir,
        creationflags=detached | new_group,
        close_fds=True,
    )
    print("[+] Agent launched in background. You can close this setup window.\n")


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
        if service_exists():
            if setup_windows_service(base_dir):
                print(f"[+] Startup status: {get_startup_status()}")
                print("[+] Service start confirmed. Exiting setup.")
                input("\nPress Enter to exit...")
                return
        launch_agent(base_dir)
        print(f"[+] Startup status: {get_startup_status()}")
        input("Press Enter to exit...")
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

    # Step 5 — Configure startup mode
    startup_mode = setup_startup_mode(base_dir)

    print("\n" + "=" * 52)
    print("  Setup complete!")
    print(f"  Admin IP  : {admin_ip}")
    print(f"  PC ID     : {pc_id}")
    print(f"  Devices   : {len(usb_devices)} USB device(s) configured")
    if startup_mode == "service":
        print("  Auto-start: Windows service (boot resilient)")
    else:
        print("  Auto-start: registry startup (after user login)")
    print(f"  Startup status: {get_startup_status()}")
    print("=" * 52 + "\n")

    # Step 6 — Launch agent
    if startup_mode == "service":
        print("[+] Service mode is active. Agent will run independently of this EXE.")
    else:
        launch_agent(base_dir)

    input("Press Enter to exit...")


if __name__ == "__main__":
    main()