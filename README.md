# Automated Asset Tracking System (AATS)

An IoT-based system for automated tracking of assets using Bluetooth Low Energy (BLE) beacons, MQTT for real-time communication, and a web-based admin dashboard.

## Features

- **Student Agent**: Monitors BLE devices and publishes data via MQTT.
- **Server**: Handles MQTT messages, stores data in SQLite database, and provides REST API.
- **Admin Dashboard**: Web interface for viewing tracked assets, alerts, and system status.
- **MQTT Broker**: Uses Mosquitto for message brokering.

## Project Structure

```
aats/
│
├── student_agent/
│   │
│   ├── main.py
│   ├── device_monitor.py
│   ├── bluetooth_monitor.py
│   ├── mqtt_client.py
│   ├── config.json
│   └── requirements.txt
│
├── server/
│   │
│   ├── app.py
│   ├── mqtt_listener.py
│   ├── database.py
│   ├── models.py
│   ├── config.py
│   ├── requirements.txt
│   │
│   └── database/
│       └── aats.db
│
├── admin_dashboard/
│   │
│   ├── index.html
│   ├── login.html
│   ├── dashboard.js
│   ├── styles.css
│   └── alert.mp3
│
├── mqtt_broker/
│   └── (Mosquitto runs here – no code needed)
│
└── README.md
```

## Prerequisites

- Python 3.8+
- MQTT Broker (Mosquitto)
- Web browser for dashboard
- BLE-capable devices for tracking

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/Automated_Asset_Tracking_System_AATS_project.git
cd Automated_Asset_Tracking_System_AATS_project
```

### 2. Install MQTT Broker

Install Mosquitto:

- On Ubuntu: `sudo apt install mosquitto`
- On macOS: `brew install mosquitto`
- On Windows: Download from [mosquitto.org](https://mosquitto.org/download/)

Start Mosquitto:

```bash
mosquitto
```

### 3. Setup Server

```bash
cd server
pip install -r requirements.txt
python app.py
```

### 4. Setup Student Agent

```bash
cd ../student_agent
pip install -r requirements.txt
python main.py
```

### 5. Admin Dashboard

Open `admin_dashboard/index.html` in your web browser.

## Usage

1. Start the MQTT broker.
2. Run the server.
3. Run the student agent on devices with BLE capabilities.
4. Access the admin dashboard to monitor assets.

## API Endpoints

- `GET /api/assets` - List all tracked assets
- `POST /api/alert` - Send alert

## Contributing

1. Fork the repository.
2. Create a feature branch.
3. Commit your changes.
4. Push to the branch.
5. Open a Pull Request.

## License

This project is licensed under the MIT License.

