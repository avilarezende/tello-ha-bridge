from __future__ import annotations

from unittest.mock import MagicMock

from tello_bridge.ai_pilot import AIPilot


def _pilot(**kwargs) -> tuple[AIPilot, MagicMock]:
    tello = MagicMock()
    tello.telemetry.flying = False
    tello.telemetry.height_cm = 50
    # Sem telemetria de conexão no mock: battery guard não bloqueia os testes
    tello.telemetry.connected = False
    tello.takeoff.return_value = True
    tello.land.return_value = True
    tello.hover.return_value = True
    tello.move.return_value = True
    tello.rotate_cw.return_value = True
    tello.rotate_ccw.return_value = True
    delay = kwargs.pop("step_delay_s", 0.01)
    pilot = AIPilot(tello=tello, step_delay_s=delay, procedure_timeout_s=5, **kwargs)
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
    pilot, tello = _pilot()
    pilot.set_active(True)
    pilot.start_procedure("nao_existe")
    if pilot._thread:
        pilot._thread.join(timeout=3)
    assert "desconhecido" in pilot.status.message.lower()
    # A01: procedimento fora da lista NÃO pode decolar o drone
    tello.takeoff.assert_not_called()
    assert pilot.status.running is False


def test_procedure_not_in_allowlist_rejected():
    pilot, tello = _pilot(allowed_procedures=["land_safe"])
    pilot.set_active(True)
    pilot.start_procedure("hover_scan")
    tello.takeoff.assert_not_called()
    assert "não permitido" in pilot.status.message.lower()


def test_command_with_bad_numbers_uses_defaults():
    pilot, tello = _pilot()
    pilot.set_active(True)
    # Payload malicioso/malformado não pode derrubar a thread nem o app
    pilot.handle_order("command", {"value": "forward", "cm": "abc"})
    tello.move.assert_called_once_with("forward", 40)


def test_command_with_huge_numbers_is_clamped():
    pilot, tello = _pilot()
    pilot.set_active(True)
    pilot.handle_order("command", {"value": "forward", "cm": 999999})
    tello.move.assert_called_once_with("forward", 500)
    tello.reset_mock()
    pilot.handle_order("command", {"value": "cw", "degrees": -50})
    tello.rotate_cw.assert_called_once_with(1)


def test_takeoff_blocked_on_low_battery():
    pilot, tello = _pilot(min_battery_pct=15)
    tello.telemetry.connected = True
    tello.telemetry.battery = 5
    pilot.set_active(True)
    pilot.handle_order("command", {"value": "takeoff"})
    tello.takeoff.assert_not_called()
    assert "bateria" in pilot.status.message.lower()


def test_procedure_blocked_on_low_battery():
    pilot, tello = _pilot(min_battery_pct=15)
    tello.telemetry.connected = True
    tello.telemetry.battery = 5
    pilot.set_active(True)
    pilot.start_procedure("hover_scan")
    tello.takeoff.assert_not_called()
    assert pilot.status.running is False


def test_land_safe_allowed_even_on_low_battery():
    pilot, tello = _pilot(min_battery_pct=15)
    tello.telemetry.connected = True
    tello.telemetry.battery = 5
    pilot.set_active(True)
    pilot.start_procedure("land_safe")
    if pilot._thread:
        pilot._thread.join(timeout=3)
    tello.land.assert_called()


def test_malformed_payload_does_not_crash():
    pilot, tello = _pilot()
    pilot.set_active(True)
    pilot.handle_order("command", "nao-e-dict")  # não deve lançar
    tello.takeoff.assert_not_called()


def test_cancel_is_not_overwritten_by_done():
    # step_delay longo garante que o cancel chega com o procedimento em andamento
    pilot, tello = _pilot(step_delay_s=5)
    pilot.set_active(True)
    pilot.start_procedure("square_patrol")
    pilot.cancel()
    if pilot._thread:
        pilot._thread.join(timeout=3)
    assert pilot.status.step == "cancelled"
    assert "Concluído" not in pilot.status.message
