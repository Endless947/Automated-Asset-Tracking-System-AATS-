from datetime import datetime, timezone


def classify_bluetooth_status(rssi, weak_threshold):
    if rssi is None:
        return "MISSING"
    if rssi < weak_threshold:
        return "WEAK_SIGNAL"
    return "CONNECTED"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    print("Status test:", classify_bluetooth_status(-82, -75))
    print("Now:", now_iso())
