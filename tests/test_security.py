from __future__ import annotations

from unittest.mock import MagicMock, patch

from tello_bridge.ai_pilot import AIPilot
from tello_bridge.controller import AppController, ControlMode
from tello_bridge.security import (
    ALLOWED_COMMANDS,
    RateLimiter,
    command_secret_ok,
    parse_int_clamped,
    redact_mapping,
    sanitize_device_name,
)


def test_sanitize_device_name_rejects_injection():
    assert sanitize_device_name("tello_drone") == "tello_drone"
    assert sanitize_device_name("../etc/passwd") == "tello_drone"
    assert sanitize_device_name("Tello-Drone") == "tello_drone"
    assert sanitize_device_name("") == "tello_drone"


def test_parse_int_clamped_handles_garbage():
    assert parse_int_clamped("40", 40, 20, 500) == 40
    assert parse_int_clamped("nope", 40, 20, 500) == 40
    assert parse_int_clamped(9999, 40, 20, 500) == 500
    assert parse_int_clamped(None, 40, 20, 500) == 40


def test_redact_mapping_hides_secrets():
    data = {"value": "takeoff", "secret": "abc", "token": "xyz", "nested": {"password": "p"}}
    out = redact_mapping(data)
    assert out["value"] == "takeoff"
    assert out["secret"] == "***"
    assert out["token"] == "***"
    assert out["nested"]["password"] == "***"


def test_command_secret_ok():
    assert command_secret_ok({"value": "land"}, "") is True
    assert command_secret_ok({"value": "land", "secret": "x"}, "x") is True
    assert command_secret_ok({"value": "land"}, "x") is False
    assert command_secret_ok({"value": "land", "secret": "y"}, "x") is False


def test_rate_limiter_blocks():
    lim = RateLimiter(max_events=2, window_s=60)
    assert lim.allow() is True
    assert lim.allow() is True
    assert lim.allow() is False


def test_ai_blocks_unknown_command_and_procedure():
    tello = MagicMock()
    tello.telemetry.flying = False
    pilot = AIPilot(tello=tello, step_delay_s=0.01, procedure_timeout_s=2)
    pilot.set_active(True)
    pilot.handle_order("command", {"value": "rm -rf /", "cm": "not-an-int"})
    tello.takeoff.assert_not_called()
    pilot.start_procedure("evil_proc")
    assert "não permitido" in pilot.status.message.lower() or "nao permitido" in pilot.status.message.lower()


def test_allowed_commands_include_safety():
    assert "land" in ALLOWED_COMMANDS
    assert "emergency" in ALLOWED_COMMANDS


def _cfg(**mqtt_extra) -> dict:
    mqtt = {
        "host": "ha.local",
        "port": 1883,
        "username": "",
        "password": "",
        "topic_prefix": "tello",
        "keepalive": 60,
        "allow_remote_mode_switch": True,
        "command_secret": "",
        "rate_limit_max": 50,
        "rate_limit_window_s": 5.0,
    }
    mqtt.update(mqtt_extra)
    return {
        "tello": {
            "ip": "192.168.10.1",
            "speed": 50,
            "move_distance_cm": 40,
            "investigate_height_cm": 80,
        },
        "home_assistant": {
            "url": "http://ha.local:8123",
            "token": "",
            "device_name": "tello_drone",
            "verify_tls": True,
        },
        "mqtt": mqtt,
        "ai": {
            "step_delay_s": 0.01,
            "procedure_timeout_s": 5,
            "procedures": ["land_safe", "hover_scan"],
        },
        "security": {
            "battery_land_percent": 15,
            "land_on_ai_error": True,
            "land_on_disconnect": True,
        },
    }


@patch("tello_bridge.controller.MqttBridge")
@patch("tello_bridge.controller.HomeAssistantClient")
@patch("tello_bridge.controller.TelloClient")
def test_mqtt_rejects_bad_secret(mock_tello, mock_ha, mock_mqtt):
    tello = MagicMock()
    mock_tello.return_value = tello
    mock_mqtt.return_value = MagicMock()
    mock_ha.return_value = MagicMock()

    tello.telemetry.connected = False
    tello.telemetry.flying = False
    tello.telemetry.battery = 100
    tello.telemetry.height_cm = 0
    tello.telemetry.temperature = 0.0
    tello.telemetry.video_on = False
    tello.telemetry.pitch = 0
    tello.telemetry.roll = 0
    tello.telemetry.yaw = 0

    ctrl = AppController(_cfg(command_secret="s3cret"))
    ctrl.set_mode(ControlMode.AI)
    ctrl._on_mqtt_command("command", {"value": "takeoff", "secret": "wrong"})
    tello.takeoff.assert_not_called()
    # land/emergency continuam permitidos (failsafe), mesmo com secret errado
    ctrl._on_mqtt_command("command", {"value": "land", "secret": "wrong"})
    tello.land.assert_called_once()


@patch("tello_bridge.controller.MqttBridge")
@patch("tello_bridge.controller.HomeAssistantClient")
@patch("tello_bridge.controller.TelloClient")
def test_mqtt_land_with_valid_secret(mock_tello, mock_ha, mock_mqtt):
    tello = MagicMock()
    mock_tello.return_value = tello
    mock_mqtt.return_value = MagicMock()
    mock_ha.return_value = MagicMock()

    ctrl = AppController(_cfg(command_secret="s3cret"))
    ctrl._on_mqtt_command("command", {"value": "land", "secret": "s3cret"})
    tello.land.assert_called_once()


@patch("tello_bridge.controller.MqttBridge")
@patch("tello_bridge.controller.HomeAssistantClient")
@patch("tello_bridge.controller.TelloClient")
def test_mqtt_mode_blocked_when_remote_switch_disabled(mock_tello, mock_ha, mock_mqtt):
    mock_tello.return_value = MagicMock()
    mock_mqtt.return_value = MagicMock()
    mock_ha.return_value = MagicMock()

    ctrl = AppController(_cfg(allow_remote_mode_switch=False))
    ctrl._on_mqtt_command("mode", {"value": "ai"})
    assert ctrl.mode == ControlMode.MANUAL


@patch("tello_bridge.controller.MqttBridge")
@patch("tello_bridge.controller.HomeAssistantClient")
@patch("tello_bridge.controller.TelloClient")
def test_battery_failsafe_lands(mock_tello, mock_ha, mock_mqtt):
    tello = MagicMock()
    tello.telemetry.connected = True
    tello.telemetry.flying = True
    tello.telemetry.battery = 10
    tello.telemetry.height_cm = 50
    tello.telemetry.temperature = 20.0
    tello.telemetry.video_on = False
    tello.telemetry.pitch = 0
    tello.telemetry.roll = 0
    tello.telemetry.yaw = 0
    mock_tello.return_value = tello
    mock_mqtt.return_value = MagicMock()
    ha = MagicMock()
    ha.token = ""
    ha.device_name = "tello_drone"
    mock_ha.return_value = ha

    ctrl = AppController(_cfg())
    ctrl._publish_state()
    tello.land.assert_called()
