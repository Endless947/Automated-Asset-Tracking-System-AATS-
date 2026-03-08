"""
AATS Admin Setup Script
=======================
Place this file in the ROOT of your AATS project (same level as server/ and admin_dashboard/).

To build into EXE:
    pip install pyinstaller
    pyinstaller --onefile --uac-admin admin_setup.py

The --uac-admin flag ensures Windows asks for Administrator permissions on launch.

# ============================================================
# FUTURE WORKS:
# ============================================================
# 1. SCOPED FIREWALL RULES
#    Currently firewall rules allow the entire local subnet.
#    Update open_firewall_ports() to scope to specific lab IPs:
#    e.g. add  remoteip=192.168.1.0/24  to the netsh command
#
# 2. MQTT AUTHENTICATION
#    Add password protection to Mosquitto so only authorized
#    agents can connect:
#    - Set allow_anonymous false in mosquitto.conf
#    - Create credentials: mosquitto_passwd -c C:\mosquitto\passwd labagent
#    - Add mqtt_username and mqtt_password to agent config.json
#    - Update mqtt_client.py in student_agent to send credentials
#
# 3. FASTAPI RATE LIMITING
#    Add a rate limiter to /auth/login to prevent brute force
#    attacks on the admin token. Use slowapi library.
# ============================================================
"""

import atexit
import ctypes
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser

# ── Configuration ──────────────────────────────────────────
BROADCAST_PORT     = 37020        # UDP port used to announce admin IP to agents
BROADCAST_MSG      = "AATS_ADMIN" # prefix agents listen for
BROADCAST_INTERVAL = 5            # seconds between each broadcast
DASHBOARD_PORT     = 5500
API_PORT           = 8000
MQTT_PORT          = 1883
MOSQUITTO_PATH     = r"C:\Program Files\mosquitto\mosquitto.exe"
# ───────────────────────────────────────────────────────────


def is_admin() -> bool:
    """Check if the script is running with Administrator privileges."""
    return bool(ctypes.windll.shell32.IsUserAnAdmin())


def get_python() -> str:
    """
    Get the real Python executable.
    When running as a PyInstaller EXE, sys.executable points to the EXE itself
    so we need to find the actual python.exe on the system instead.
    """
    if getattr(sys, "frozen", False):
        # Running as PyInstaller EXE — find python.exe on the system PATH
        result = subprocess.run(
            ["where", "python"], capture_output=True, text=True
        )
        lines = result.stdout.strip().splitlines()
        if lines:
            return lines[0]
        print("[!] Python not found on PATH. Please install Python and add it to PATH.")
        input("Press Enter to exit...")
        sys.exit(1)
    return sys.executable


def get_base_dir() -> str:
    """
    Get the project root directory.
    When running as a PyInstaller EXE from dist/, we go one level up
    to reach the actual project root where server/ and admin_dashboard/ live.
    """
    path = os.path.dirname(os.path.abspath(sys.argv[0]))
    if getattr(sys, "frozen", False):
        path = os.path.dirname(path)  # go up from dist/ to project root
    return path


def get_local_ip() -> str:
    """Get the local IPv4 address of this machine."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


def open_firewall_ports() -> None:
    """Open required ports in Windows Firewall."""
    print("[*] Configuring firewall rules...")
    rules = [
        ("AATS MQTT 1883",      MQTT_PORT),
        ("AATS API 8000",       API_PORT),
        ("AATS Dashboard 5500", DASHBOARD_PORT),
    ]
    for name, port in rules:
        # Delete existing rule first to avoid duplicates
        os.system(f'netsh advfirewall firewall delete rule name="{name}" >nul 2>&1')
        os.system(
            f'netsh advfirewall firewall add rule name="{name}" '
            f'dir=in action=allow protocol=TCP localport={port} enable=yes >nul 2>&1'
        )
    print("[+] Firewall rules configured.")


def start_mosquitto() -> subprocess.Popen | None:
    """Start the Mosquitto MQTT broker."""
    print("[*] Starting Mosquitto broker...")

    # Check if already running — net start fails if service is already up
    check = subprocess.run(
        ["sc", "query", "mosquitto"], capture_output=True, text=True
    )
    if "RUNNING" in check.stdout:
        print("[+] Mosquitto already running.")
        return None

    # Try starting as a Windows service
    result = os.system("net start mosquitto >nul 2>&1")
    if result == 0:
        print("[+] Mosquitto started as a service.")
        return None

    # Fall back to running the exe directly
    if os.path.exists(MOSQUITTO_PATH):
        proc = subprocess.Popen(
            [MOSQUITTO_PATH, "-v"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("[+] Mosquitto started directly.")
        return proc

    print("[!] Mosquitto not found! Please install it from https://mosquitto.org/download/")
    input("Press Enter to exit...")
    sys.exit(1)


def start_fastapi(base_dir: str) -> subprocess.Popen:
    """Start the FastAPI server using uvicorn."""
    print("[*] Starting FastAPI server...")
    server_dir = os.path.join(base_dir, "server")
    proc = subprocess.Popen(
        [get_python(), "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", str(API_PORT)],
        cwd=server_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print("[+] FastAPI server started.")
    return proc


def start_dashboard(base_dir: str) -> subprocess.Popen:
    """Serve the admin dashboard via Python's HTTP server."""
    print("[*] Starting dashboard server...")
    dashboard_dir = os.path.join(base_dir, "admin_dashboard")
    proc = subprocess.Popen(
        [get_python(), "-m", "http.server", str(DASHBOARD_PORT)],
        cwd=dashboard_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print("[+] Dashboard server started.")
    return proc


def broadcast_ip(ip: str, stop_event: threading.Event) -> None:
    """
    Continuously broadcast the admin IP over UDP so agent PCs
    can auto-discover it without manual config.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    message = f"{BROADCAST_MSG}:{ip}".encode()
    print(f"[*] Broadcasting IP {ip} every {BROADCAST_INTERVAL}s on UDP port {BROADCAST_PORT}...")
    while not stop_event.is_set():
        try:
            sock.sendto(message, ("<broadcast>", BROADCAST_PORT))
        except Exception:
            pass
        time.sleep(BROADCAST_INTERVAL)
    sock.close()


def shutdown(procs: list, stop_event: threading.Event) -> None:
    """Cleanly stop all started processes and close firewall ports."""
    print("\n[*] Shutting down AATS Admin...")
    stop_event.set()

    # Stop any subprocesses (fastapi, dashboard, direct mosquitto)
    for proc in procs:
        if proc is not None:
            proc.terminate()

    # Always stop Mosquitto — covers both service and direct launch
    os.system("net stop mosquitto >nul 2>&1")
    print("[+] Mosquitto stopped.")

    # Remove firewall rules on exit
    for name in ("AATS MQTT 1883", "AATS API 8000", "AATS Dashboard 5500"):
        os.system(f'netsh advfirewall firewall delete rule name="{name}" >nul 2>&1')

    print("[+] Firewall rules removed.")
    print("[+] AATS Admin stopped. Goodbye!")


def main() -> None:
    print("=" * 52)
    print("         AATS — Admin Setup & Launcher")
    print("=" * 52)

    # Require admin privileges
    if not is_admin():
        print("[!] This program must be run as Administrator.")
        print("    Right-click the EXE and select 'Run as administrator'.")
        input("\nPress Enter to exit...")
        sys.exit(1)

    # Locate project root correctly whether running as .py or .exe
    base_dir = get_base_dir()
    print(f"[+] Project root: {base_dir}")

    # Get this machine's IP
    ip = get_local_ip()
    print(f"[+] Admin PC IP detected: {ip}")

    # Setup
    open_firewall_ports()
    mosquitto_proc = start_mosquitto()
    time.sleep(2)  # give Mosquitto a moment to initialise

    fastapi_proc   = start_fastapi(base_dir)
    dashboard_proc = start_dashboard(base_dir)
    time.sleep(3)  # give servers a moment to start

    # Start IP broadcaster so agent PCs can auto-discover
    stop_event = threading.Event()
    broadcast_thread = threading.Thread(
        target=broadcast_ip,
        args=(ip, stop_event),
        daemon=True,
    )
    broadcast_thread.start()

    # Open the dashboard in the default browser
    dashboard_url = f"http://localhost:{DASHBOARD_PORT}/login.html"
    print(f"[*] Opening dashboard at {dashboard_url}")
    webbrowser.open(dashboard_url)

    # Summary
    print("\n" + "=" * 52)
    print("  AATS Admin is running!")
    print(f"  Dashboard : http://localhost:{DASHBOARD_PORT}/login.html")
    print(f"  API       : http://localhost:{API_PORT}")
    print(f"  MQTT      : {ip}:{MQTT_PORT}")
    print(f"  Broadcast : sending IP every {BROADCAST_INTERVAL}s")
    print("=" * 52)
    print("\n  Press Ctrl+C or close this window to stop all services.\n")

    procs = [p for p in [mosquitto_proc, fastapi_proc, dashboard_proc] if p]

    # Runs on ANY exit — X button, Ctrl+C, or crash
    atexit.register(shutdown, procs, stop_event)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass  # atexit handles cleanup


if __name__ == "__main__":
    main()