"""Tests unitaires pour la normalisation et déduplication des payloads Zabbix."""

from datetime import datetime, timezone
import pytest
from packages.connectors.zabbix.src.normalizer import (
    compute_idempotency_key,
    normalize_zabbix_payload,
    parse_event_severity,
    parse_event_status,
)
from packages.contracts.src.events import EventSeverity, EventStatus


def test_parse_event_severity():
    assert parse_event_severity("4") == EventSeverity.HIGH
    assert parse_event_severity("5") == EventSeverity.DISASTER
    assert parse_event_severity("WARNING") == EventSeverity.WARNING
    assert parse_event_severity(None) == EventSeverity.WARNING


def test_parse_event_status():
    assert parse_event_status("PROBLEM") == EventStatus.PROBLEM
    assert parse_event_status("RECOVERY") == EventStatus.RECOVERY
    assert parse_event_status("RESOLVED") == EventStatus.RECOVERY
    assert parse_event_status("0") == EventStatus.RECOVERY


def test_compute_idempotency_key():
    key1 = compute_idempotency_key("1001", "PROBLEM", "901")
    key2 = compute_idempotency_key("1001", "PROBLEM", "901")
    key3 = compute_idempotency_key("1001", "RECOVERY", "901")
    assert key1 == key2
    assert key1 != key3
    assert len(key1) == 64  # SHA-256


def test_normalize_zabbix_payload_full():
    raw_payload = {
        "event_id": "45821",
        "event_type": "PROBLEM",
        "host_id": "10452",
        "host_name": "SRV-APP-01",
        "trigger_id": "9821",
        "severity": "HIGH",
        "problem": "CPU utilization above 90%",
        "metric": "system.cpu.util",
        "value": 96.4,
        "timestamp": "2026-11-02T12:30:00Z",
        "ip": "192.168.1.50",
    }
    normalized = normalize_zabbix_payload(raw_payload)

    assert normalized.event_id == "45821"
    assert normalized.event_type == EventStatus.PROBLEM
    assert normalized.host_name == "SRV-APP-01"
    assert normalized.severity == EventSeverity.HIGH
    assert normalized.value == 96.4
    assert normalized.ip_address == "192.168.1.50"
    assert len(normalized.idempotency_key) == 64
