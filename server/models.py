from typing import Optional

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class DeviceState(BaseModel):
    lab_id: str
    pc_id: str
    device_id: str
    device_label: Optional[str] = None
    device_type: str
    current_status: str
    severity: str
    alert_status: str
    rssi: Optional[int] = None
    pending_since: Optional[str] = None
    updated_at: str


class EventRecord(BaseModel):
    event_id: str
    lab_id: str
    pc_id: str
    device_id: str
    device_label: Optional[str] = None
    device_type: str
    status: str
    severity: str
    alert_status: str
    rssi: Optional[int] = None
    observed_at: Optional[str] = None
    agent_time: Optional[str] = None
    received_at: str
    source: Optional[str] = None
