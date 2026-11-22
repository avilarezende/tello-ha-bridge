from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Iterable

if TYPE_CHECKING:
    from tello_bridge.tello_client import TelloClient

logger = logging.getLogger(__name__)

# Procedimentos conhecidos pelo app (usado quando a config não define a lista).
DEFAULT_PROCEDURES = ("hover_scan", "square_patrol", "forward_investigate", "land_safe")

# Comandos de voo aceitos via ordens remotas (defesa em profundidade).
KNOWN_COMMANDS = frozenset(
    {
        "takeoff",
        "land",
        "hover",
        "emergency",
        "forward",
        "back",
        "left",
        "right",
        "up",
        "down",
        "cw",
        "ccw",
    }
)


@dataclass
class AIStatus:
    active: bool = False
    procedure: str = ""
    step: str = "idle"
    message: str = "IA em espera"
    last_order: str = ""
    running: bool = False
    history: list[str] = field(default_factory=list)


class AIPilot:
    """Executa procedimentos automáticos e ordens vindas do Home Assistant."""

    def __init__(
        self,
        tello: TelloClient,
        move_distance_cm: int = 40,
        investigate_height_cm: int = 80,
        step_delay_s: float = 2.0,
        procedure_timeout_s: float = 120.0,
        on_status: Callable[[AIStatus], None] | None = None,
        *,
        allowed_procedures: Iterable[str] | None = None,
        min_battery_pct: int = 15,
    ) -> None:
        self.tello = tello
        self.move_distance_cm = move_distance_cm
        self.investigate_height_cm = investigate_height_cm
        self.step_delay_s = step_delay_s
        self.procedure_timeout_s = procedure_timeout_s
        self.on_status = on_status
        # A01 (defesa em profundidade): só procedimentos explicitamente
        # configurados podem ser disparados remotamente.
        self.allowed_procedures = frozenset(allowed_procedures or DEFAULT_PROCEDURES)
        self.min_battery_pct = min_battery_pct
        self.status = AIStatus()
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._lock = threading.Lock()

    @staticmethod
    def _safe_int(value: Any, default: int, lo: int, hi: int) -> int:
        """Converte para int com fallback e clamp — nunca lança exceção."""
        try:
            return max(lo, min(hi, int(value)))
        except (TypeError, ValueError):
            return default

    def battery_low(self) -> bool:
        """True quando há telemetria e a bateria está abaixo do mínimo seguro."""
        t = self.tello.telemetry
        if not t.connected:
            return False  # sem telemetria confiável, não bloquear
        try:
            return int(t.battery) < self.min_battery_pct
        except (TypeError, ValueError):
            return False

    def set_active(self, active: bool) -> None:
        self.status.active = active
        if not active:
            self.cancel()
            self.status.message = "Controle manual"
            self.status.procedure = ""
            self.status.step = "idle"
        else:
            self.status.message = "IA ativa — aguardando ordens do HA"
        self._emit()

    def cancel(self) -> None:
        self._cancel.set()
        self.tello.hover()
        self.status.running = False
        self.status.step = "cancelled"
        self._emit()

    def handle_order(self, kind: str, payload: dict) -> None:
        """kind: command | procedure | mode"""
        if not isinstance(payload, dict):
            self._log(f"Ordem ignorada — payload inválido: {type(payload).__name__}")
            return
        self.status.last_order = f"{kind}:{str(payload)[:200]}"
        self._log(f"Ordem recebida: {kind} {str(payload)[:200]}")

        if kind == "mode":
            value = str(payload.get("value", "")).lower()
            self.set_active(value in ("ai", "auto", "on", "true", "1"))
            return

        if not self.status.active:
            self._log("Ignorado — modo manual")
            return

        if kind == "procedure":
            name = str(payload.get("value") or payload.get("name") or "").strip()
            if name:
                self.start_procedure(name)
            return

        if kind == "command":
            cmd = str(payload.get("value") or payload.get("cmd") or "").lower()
            self._run_single_command(cmd, payload)

    def start_procedure(self, name: str) -> None:
        name = (name or "").strip()
        if name not in self.allowed_procedures:
            self.status.message = f"Procedimento desconhecido/não permitido: {name or '(vazio)'}"
            self._log(self.status.message)
            self._emit()
            return
        if name != "land_safe" and self.battery_low():
            self.status.message = (
                f"Bateria fraca ({self.tello.telemetry.battery}% < "
                f"{self.min_battery_pct}%) — {name} bloqueado"
            )
            self._log(self.status.message)
            self._emit()
            return
        with self._lock:
            if self.status.running:
                self.cancel()
                time.sleep(0.2)
            self._cancel.clear()
            self.status.running = True
            self.status.procedure = name
            self.status.step = "start"
            self.status.message = f"Iniciando {name}"
            self._emit()
            self._thread = threading.Thread(
                target=self._run_procedure, args=(name,), daemon=True, name=f"ai-{name}"
            )
            self._thread.start()

    def _run_single_command(self, cmd: str, payload: dict) -> None:
        # Valores vindos da rede são sanitizados com clamp (20-500 cm, 1-360°).
        dist = self._safe_int(payload.get("cm"), self.move_distance_cm, 20, 500)
        deg = self._safe_int(payload.get("degrees"), 90, 1, 360)
        if cmd not in KNOWN_COMMANDS:
            self._log(f"Comando desconhecido: {cmd!r}")
            return
        if cmd == "takeoff" and self.battery_low():
            self.status.message = (
                f"Bateria fraca ({self.tello.telemetry.battery}%) — decolagem bloqueada"
            )
            self._log(self.status.message)
            self._emit()
            return
        actions = {
            "takeoff": self.tello.takeoff,
            "land": self.tello.land,
            "hover": self.tello.hover,
            "emergency": self.tello.emergency,
            "forward": lambda: self.tello.move("forward", dist),
            "back": lambda: self.tello.move("back", dist),
            "left": lambda: self.tello.move("left", dist),
            "right": lambda: self.tello.move("right", dist),
            "up": lambda: self.tello.move("up", dist),
            "down": lambda: self.tello.move("down", dist),
            "cw": lambda: self.tello.rotate_cw(deg),
            "ccw": lambda: self.tello.rotate_ccw(deg),
        }
        fn = actions[cmd]
        self.status.message = f"Executando {cmd}"
        self._emit()
        try:
            ok = fn()
        except Exception as exc:  # noqa: BLE001
            self._log(f"{cmd}: erro {exc}")
            return
        self._log(f"{cmd}: {'ok' if ok else 'falhou'}")

    def _run_procedure(self, name: str) -> None:
        deadline = time.time() + self.procedure_timeout_s
        try:
            if name == "hover_scan":
                self._proc_hover_scan(deadline)
            elif name == "square_patrol":
                self._proc_square_patrol(deadline)
            elif name == "forward_investigate":
                self._proc_forward_investigate(deadline)
            elif name == "land_safe":
                self._step("land", "Pouso seguro")
                self.tello.land()
            else:
                self.status.message = f"Procedimento desconhecido: {name}"
                self._log(self.status.message)
        except Exception as exc:  # noqa: BLE001
            self.status.message = f"Erro na IA: {exc}"
            logger.exception("Procedimento IA falhou")
        finally:
            self.tello.hover()
            self.status.running = False
            if self._cancel.is_set():
                # Não sobrescreve o cancelamento com "Concluído".
                self.status.step = "cancelled"
            else:
                self.status.step = "done"
                if "Erro" not in self.status.message and "desconhecido" not in self.status.message:
                    self.status.message = f"Concluído: {name}"
            self._emit()

    def _proc_hover_scan(self, deadline: float) -> None:
        self._step("takeoff", "Decolagem para varredura")
        if not self.tello.telemetry.flying:
            self.tello.takeoff()
        self._sleep(deadline)
        # Ajuste de altura aproximado
        h = self.tello.telemetry.height_cm
        if h < self.investigate_height_cm - 20:
            self._step("climb", "Subindo para altura de investigação")
            self.tello.move("up", min(80, self.investigate_height_cm - max(h, 20)))
            self._sleep(deadline)
        for i, deg in enumerate((90, 90, 90, 90), start=1):
            if self._cancel.is_set() or time.time() > deadline:
                break
            self._step(f"scan_{i}", f"Girando varredura {i}/4")
            self.tello.rotate_cw(deg)
            self._sleep(deadline)
        self._step("hover", "Mantendo posição")
        self.tello.hover()

    def _proc_square_patrol(self, deadline: float) -> None:
        self._step("takeoff", "Decolagem — patrulha quadrada")
        if not self.tello.telemetry.flying:
            self.tello.takeoff()
        self._sleep(deadline)
        for i in range(1, 5):
            if self._cancel.is_set() or time.time() > deadline:
                break
            self._step(f"leg_{i}", f"Lado {i}/4 da patrulha")
            self.tello.move("forward", self.move_distance_cm)
            self._sleep(deadline)
            self.tello.rotate_cw(90)
            self._sleep(deadline)
        self.tello.hover()

    def _proc_forward_investigate(self, deadline: float) -> None:
        self._step("takeoff", "Decolagem — investigação frontal")
        if not self.tello.telemetry.flying:
            self.tello.takeoff()
        self._sleep(deadline)
        self._step("approach", "Avançando para investigar")
        self.tello.move("forward", self.move_distance_cm)
        self._sleep(deadline)
        self._step("look_left", "Olhando esquerda")
        self.tello.rotate_ccw(45)
        self._sleep(deadline)
        self._step("look_right", "Olhando direita")
        self.tello.rotate_cw(90)
        self._sleep(deadline)
        self._step("recenter", "Centralizando")
        self.tello.rotate_ccw(45)
        self._sleep(deadline)
        self.tello.hover()

    def _step(self, step: str, message: str) -> None:
        self.status.step = step
        self.status.message = message
        self._log(message)
        self._emit()

    def _sleep(self, deadline: float) -> None:
        end = min(time.time() + self.step_delay_s, deadline)
        while time.time() < end and not self._cancel.is_set():
            time.sleep(0.1)

    def _log(self, msg: str) -> None:
        self.status.history.append(f"{time.strftime('%H:%M:%S')} {msg}")
        self.status.history = self.status.history[-40:]
        logger.info(msg)

    def _emit(self) -> None:
        if self.on_status:
            self.on_status(self.status)
