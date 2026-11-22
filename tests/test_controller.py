from __future__ import annotations

from unittest.mock import MagicMock, patch

from tello_bridge.controller import AppController, ControlMode


def _cfg() -> dict:
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
        },
        "mqtt": {
            "host": "ha.local",
            "port": 1883,
            "username": "",
            "password": "",
            "topic_prefix": "tello",
            "keepalive": 60,
        },
        "ai": {"step_delay_s": 0.01, "procedure_timeout_s": 5, "procedures": ["land_safe"]},
    }


@patch("tello_bridge.controller.MqttBridge")
@patch("tello_bridge.controller.HomeAssistantClient")
@patch("tello_bridge.controller.TelloClient")
def test_set_mode_toggles_ai(mock_tello, mock_ha, mock_mqtt):
    mock_mqtt.return_value = MagicMock()
    mock_ha.return_value = MagicMock()
    mock_tello.return_value = MagicMock()

    ctrl = AppController(_cfg())
    ctrl.set_mode(ControlMode.AI)
    assert ctrl.mode == ControlMode.AI
    assert ctrl.ai.status.active is True

    ctrl.set_mode("manual")
    assert ctrl.mode == ControlMode.MANUAL
    assert ctrl.ai.status.active is False


@patch("tello_bridge.controller.MqttBridge")
@patch("tello_bridge.controller.HomeAssistantClient")
@patch("tello_bridge.controller.TelloClient")
def test_manual_blocked_in_ai_mode(mock_tello, mock_ha, mock_mqtt):
    tello = MagicMock()
    mock_tello.return_value = tello
    mock_mqtt.return_value = MagicMock()
    mock_ha.return_value = MagicMock()

    ctrl = AppController(_cfg())
    ctrl.set_mode(ControlMode.AI)
    assert ctrl.takeoff() is False
    tello.takeoff.assert_not_called()


@patch("tello_bridge.controller.MqttBridge")
@patch("tello_bridge.controller.HomeAssistantClient")
@patch("tello_bridge.controller.TelloClient")
def test_land_always_allowed(mock_tello, mock_ha, mock_mqtt):
    tello = MagicMock()
    tello.land.return_value = True
    mock_tello.return_value = tello
    mock_mqtt.return_value = MagicMock()
    mock_ha.return_value = MagicMock()

    ctrl = AppController(_cfg())
    ctrl.set_mode(ControlMode.AI)
    assert ctrl.land() is True
    tello.land.assert_called_once()


@patch("tello_bridge.controller.MqttBridge")
@patch("tello_bridge.controller.HomeAssistantClient")
@patch("tello_bridge.controller.TelloClient")
def test_mqtt_mode_command(mock_tello, mock_ha, mock_mqtt):
    mock_tello.return_value = MagicMock()
    mock_mqtt.return_value = MagicMock()
    mock_ha.return_value = MagicMock()

    ctrl = AppController(_cfg())
    ctrl._on_mqtt_command("mode", {"value": "ai"})
    assert ctrl.mode == ControlMode.AI


@patch("tello_bridge.controller.MqttBridge")
@patch("tello_bridge.controller.HomeAssistantClient")
@patch("tello_bridge.controller.TelloClient")
def test_takeoff_blocked_on_low_battery(mock_tello, mock_ha, mock_mqtt):
    tello = MagicMock()
    tello.telemetry.connected = True
    tello.telemetry.battery = 5
    mock_tello.return_value = tello
    mock_mqtt.return_value = MagicMock()
    mock_ha.return_value = MagicMock()

    ctrl = AppController(_cfg())  # min_battery_pct padrão: 15
    assert ctrl.takeoff() is False
    tello.takeoff.assert_not_called()


@patch("tello_bridge.controller.MqttBridge")
@patch("tello_bridge.controller.HomeAssistantClient")
@patch("tello_bridge.controller.TelloClient")
def test_takeoff_allowed_with_good_battery(mock_tello, mock_ha, mock_mqtt):
    tello = MagicMock()
    tello.telemetry.connected = True
    tello.telemetry.battery = 80
    tello.takeoff.return_value = True
    mock_tello.return_value = tello
    mock_mqtt.return_value = MagicMock()
    mock_ha.return_value = MagicMock()

    ctrl = AppController(_cfg())
    assert ctrl.takeoff() is True
    tello.takeoff.assert_called_once()


@patch("tello_bridge.controller.MqttBridge")
@patch("tello_bridge.controller.HomeAssistantClient")
@patch("tello_bridge.controller.TelloClient")
def test_unknown_mqtt_command_ignored(mock_tello, mock_ha, mock_mqtt):
    tello = MagicMock()
    mock_tello.return_value = tello
    mock_mqtt.return_value = MagicMock()
    mock_ha.return_value = MagicMock()

    ctrl = AppController(_cfg())
    ctrl._on_mqtt_command("command", {"value": "self_destruct"})
    tello.land.assert_not_called()
    tello.emergency.assert_not_called()


@patch("tello_bridge.controller.MqttBridge")
@patch("tello_bridge.controller.HomeAssistantClient")
@patch("tello_bridge.controller.TelloClient")
def test_malformed_mqtt_payload_does_not_crash(mock_tello, mock_ha, mock_mqtt):
    mock_tello.return_value = MagicMock()
    mock_mqtt.return_value = MagicMock()
    mock_ha.return_value = MagicMock()

    ctrl = AppController(_cfg())
    # não deve lançar exceção
    ctrl._on_mqtt_command("command", "nao-e-dict")
