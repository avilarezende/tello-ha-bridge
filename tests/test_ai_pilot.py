from __future__ import annotations

from unittest.mock import MagicMock

from tello_bridge.ai_pilot import AIPilot


def _pilot() -> tuple[AIPilot, MagicMock]:
    tello = MagicMock()
    tello.telemetry.flying = False
    tello.telemetry.height_cm = 50
    tello.takeoff.return_value = True
    tello.land.return_value = True
    tello.hover.return_value = True
    tello.move.return_value = True
    tello.rotate_cw.return_value = True
    tello.rotate_ccw.return_value = True
    pilot = AIPilot(tello=tello, step_delay_s=0.01, procedure_timeout_s=5)
    return pilot, tello


def test_manual_mode_ignores_orders():
    pilot, tello = _pilot()
    pilot.set_active(False)
    pilot.handle_order("command", {"value": "takeoff"})
    tello.takeoff.assert_not_called()


def test_ai_mode_runs_command():
    pilot, tello = _pilot()
    pilot.set_active(True)
    pilot.handle_order("command", {"value": "takeoff"})
    tello.takeoff.assert_called_once()


def test_mode_order_activates_ai():
    pilot, _ = _pilot()
    pilot.handle_order("mode", {"value": "ai"})
    assert pilot.status.active is True


def test_land_safe_procedure():
    pilot, tello = _pilot()
    pilot.set_active(True)
    pilot.start_procedure("land_safe")
    if pilot._thread:
        pilot._thread.join(timeout=3)
    tello.land.assert_called()
    assert pilot.status.running is False


def test_unknown_procedure_sets_message():
    pilot, _ = _pilot()
    pilot.set_active(True)
    pilot.start_procedure("nao_existe")
    if pilot._thread:
        pilot._thread.join(timeout=3)
    assert "desconhecido" in pilot.status.message.lower()
