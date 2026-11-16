from __future__ import annotations

import logging
import threading
import time
from enum import Enum
from typing import Any, Callable

from tello_bridge.ai_pilot import AIPilot, AIStatus
from tello_bridge.ha_client import HomeAssistantClient
from tello_bridge.mqtt_bridge import MqttBridge
from tello_bridge.security import (
    ALLOWED_PROCEDURES,
    SAFETY_COMMANDS,
    RateLimiter,
    command_secret_ok,
    redact_mapping,
    sanitize_device_name,
)
from tello_bridge.tello_client import TelloClient, TelloTelemetry

logger = logging.getLogger(__name__)


class ControlMode(str, Enum):
    MANUAL = "manual"
    AI = "ai"


class AppController:
    """Orquestra Tello, HA, MQTT e piloto IA."""

    def __init__(self, cfg: dict[str, Any]) -> None:
        self.cfg = cfg
        tello_cfg = cfg.get("tello", {})
        ha_cfg = cfg.get("home_assistant", {})
        mqtt_cfg = cfg.get("mqtt", {})
        ai_cfg = cfg.get("ai", {})
        sec_cfg = cfg.get("security", {})

        self._command_secret = str(mqtt_cfg.get("command_secret", "") or "")
        self._allow_remote_mode_switch = bool(
            mqtt_cfg.get("allow_remote_mode_switch", True)
        )
        self._battery_land_percent = int(sec_cfg.get("battery_land_percent", 15))
        self._land_on_disconnect = bool(sec_cfg.get("land_on_disconnect", True))
        self._battery_land_done = False
        self._rate_limiter = RateLimiter(
            max_events=int(mqtt_cfg.get("rate_limit_max", 10)),
            window_s=float(mqtt_cfg.get("rate_limit_window_s", 5.0)),
        )

        allowed_procs = ai_cfg.get("procedures") or list(ALLOWED_PROCEDURES)
        allowed_procs = [p for p in allowed_procs if p in ALLOWED_PROCEDURES]

        device_name = sanitize_device_name(
            str(ha_cfg.get("device_name", "tello_drone"))
        )

        self.tello = TelloClient(
            ip=str(tello_cfg.get("ip", "192.168.10.1")),
            speed=int(tello_cfg.get("speed", 50)),
            land_on_disconnect=self._land_on_disconnect,
        )
        self.ha = HomeAssistantClient(
            url=str(ha_cfg.get("url", "http://homeassistant.local:8123")),
            token=str(ha_cfg.get("token", "")),
            device_name=device_name,
            verify_tls=bool(ha_cfg.get("verify_tls", True)),
        )
        self.mqtt = MqttBridge(
            host=str(mqtt_cfg.get("host", "homeassistant.local")),
            port=int(mqtt_cfg.get("port", 1883)),
            username=str(mqtt_cfg.get("username", "")),
            password=str(mqtt_cfg.get("password", "")),
            topic_prefix=str(mqtt_cfg.get("topic_prefix", "tello")),
            keepalive=int(mqtt_cfg.get("keepalive", 60)),
            tls=bool(mqtt_cfg.get("tls", False)),
            tls_insecure=bool(mqtt_cfg.get("tls_insecure", False)),
        )
        self.ai = AIPilot(
            tello=self.tello,
            move_distance_cm=int(tello_cfg.get("move_distance_cm", 40)),
            investigate_height_cm=int(tello_cfg.get("investigate_height_cm", 80)),
            step_delay_s=float(ai_cfg.get("step_delay_s", 2.0)),
            procedure_timeout_s=float(ai_cfg.get("procedure_timeout_s", 120)),
            on_status=self._on_ai_status,
            allowed_procedures=allowed_procs,
            land_on_error=bool(sec_cfg.get("land_on_ai_error", True)),
        )

        self.mode = ControlMode.MANUAL
        self._publish_stop = threading.Event()
        self._publish_thread: threading.Thread | None = None
        self._listeners: list[Callable[[], None]] = []
        self.mqtt.set_command_handler(self._on_mqtt_command)

    def add_listener(self, cb: Callable[[], None]) -> None:
        self._listeners.append(cb)

    def _notify(self) -> None:
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:  # noqa: BLE001
                logger.exception("listener")

    def start_services(self) -> None:
        self.ha.check_connection()
        self.mqtt.connect()
        self._publish_stop.clear()
        self._publish_thread = threading.Thread(
            target=self._publish_loop, daemon=True, name="ha-publish"
        )
        self._publish_thread.start()
        self._notify()

    def shutdown(self) -> None:
        self._publish_stop.set()
        self.ai.cancel()
        # Failsafe: pousar antes de encerrar se ainda voando
        if self.tello.telemetry.flying:
            logger.warning("Shutdown com drone voando — pousando")
            self.tello.land()
        self.tello.disconnect()
        self.mqtt.disconnect()
        self.ha.close()

    def connect_tello(self, with_video: bool = True) -> bool:
        ok = self.tello.connect()
        if ok and with_video:
            self.tello.start_video()
        self._battery_land_done = False
        self._publish_state()
        self._notify()
        return ok

    def disconnect_tello(self) -> None:
        self.tello.disconnect()
        self._publish_state()
        self._notify()

    def set_mode(self, mode: ControlMode | str) -> None:
        mode = ControlMode(mode)
        self.mode = mode
        self.ai.set_active(mode == ControlMode.AI)
        if mode == ControlMode.MANUAL:
            self.tello.hover()
        self.mqtt.publish("mode/state", mode.value)
        self._publish_state()
        self._notify()

    def toggle_mode(self) -> None:
        self.set_mode(
            ControlMode.AI if self.mode == ControlMode.MANUAL else ControlMode.MANUAL
        )

    # --- Manual (só no modo MANUAL) ---
    def manual_allowed(self) -> bool:
        return self.mode == ControlMode.MANUAL

    def takeoff(self) -> bool:
        if not self.manual_allowed():
            return False
        ok = self.tello.takeoff()
        self._notify()
        return ok

    def land(self) -> bool:
        # pouso permitido sempre (segurança)
        ok = self.tello.land()
        self._notify()
        return ok

    def emergency(self) -> bool:
        ok = self.tello.emergency()
        self._notify()
        return ok

    def send_rc(self, lr: int, fb: int, ud: int, yaw: int) -> bool:
        if not self.manual_allowed():
            return False
        return self.tello.send_rc(lr, fb, ud, yaw)

    def move(self, direction: str) -> bool:
        if not self.manual_allowed():
            return False
        cm = int(self.cfg.get("tello", {}).get("move_distance_cm", 40))
        return self.tello.move(direction, cm)

    def start_ai_procedure(self, name: str) -> None:
        if self.mode != ControlMode.AI:
            self.set_mode(ControlMode.AI)
        self.ai.start_procedure(name)

    def refresh_ha(self) -> bool:
        ok = self.ha.check_connection()
        self._notify()
        return ok

    def _on_mqtt_command(self, kind: str, payload: dict[str, Any]) -> None:
        # kind vem do último segmento: command | procedure | mode
        safe_payload = redact_mapping(payload)
        logger.info("MQTT %s %s", kind, safe_payload)

        # Failsafe land/emergency: sempre (mesmo sem secret / fora do rate limit)
        if kind == "command":
            cmd = str(payload.get("value") or payload.get("cmd") or "").lower().strip()
            if cmd in SAFETY_COMMANDS:
                getattr(self.tello, cmd)()
                self._notify()
                return

        if not command_secret_ok(payload, self._command_secret):
            logger.warning("MQTT rejeitado: command_secret inválido (%s)", kind)
            return

        if not self._rate_limiter.allow():
            logger.warning("MQTT rate limit — comando ignorado: %s", kind)
            return

        if kind == "mode":
            if not self._allow_remote_mode_switch:
                logger.warning("MQTT mode rejeitado: allow_remote_mode_switch=false")
                return
            value = str(payload.get("value", "")).lower()
            if value in ("manual", "ai"):
                self.set_mode(value)
            else:
                self.ai.handle_order("mode", payload)
            return
        if kind == "command":
            cmd = str(payload.get("value") or payload.get("cmd") or "").lower().strip()
            if self.mode == ControlMode.AI:
                self.ai.handle_order("command", payload)
            else:
                logger.info("MQTT command '%s' ignorado — modo manual", cmd)
            return
        if kind == "procedure":
            if self.mode != ControlMode.AI:
                if self._allow_remote_mode_switch:
                    self.set_mode(ControlMode.AI)
                else:
                    logger.warning(
                        "MQTT procedure rejeitado: modo não é IA "
                        "(defina modo via GUI ou allow_remote_mode_switch)"
                    )
                    return
            self.ai.handle_order("procedure", payload)

    def _on_ai_status(self, status: AIStatus) -> None:
        self.mqtt.publish(
            "ai/status",
            {
                "active": status.active,
                "procedure": status.procedure,
                "step": status.step,
                "message": status.message,
                "running": status.running,
            },
        )
        self._notify()

    def _maybe_battery_failsafe(self, t: TelloTelemetry) -> None:
        try:
            battery = int(t.battery)
        except (TypeError, ValueError):
            return
        if (
            bool(t.connected)
            and bool(t.flying)
            and battery > 0
            and battery <= self._battery_land_percent
            and not self._battery_land_done
        ):
            self._battery_land_done = True
            logger.warning(
                "Bateria %s%% ≤ %s%% — failsafe pouso",
                battery,
                self._battery_land_percent,
            )
            self.tello.land()
            self.mqtt.publish(
                "ai/status",
                {
                    "active": self.ai.status.active,
                    "procedure": "battery_failsafe",
                    "step": "land",
                    "message": f"Pouso automático: bateria {battery}%",
                    "running": False,
                },
            )

    def _publish_loop(self) -> None:
        while not self._publish_stop.wait(2.0):
            self._publish_state()
            # ping HA periodicamente
            if time.time() - self.ha.status.last_check > 10:
                self.ha.check_connection()
                self._notify()

    def _publish_state(self) -> None:
        t: TelloTelemetry = self.tello.telemetry
        self._maybe_battery_failsafe(t)
        payload = {
            "connected": t.connected,
            "battery": t.battery,
            "height_cm": t.height_cm,
            "temperature": t.temperature,
            "flying": t.flying,
            "video_on": t.video_on,
            "mode": self.mode.value,
            "ai_active": self.ai.status.active,
            "ai_procedure": self.ai.status.procedure,
            "ai_message": self.ai.status.message,
            "pitch": t.pitch,
            "roll": t.roll,
            "yaw": t.yaw,
        }
        self.mqtt.publish("state", payload)
        self.mqtt.publish("battery", t.battery)
        self.mqtt.publish("mode/state", self.mode.value)
        self.mqtt.publish("connected", "ON" if t.connected else "OFF")

        # Espelha no HA via REST se possível
        name = self.ha.device_name
        if self.ha.token:
            self.ha.set_state(
                f"sensor.{name}_battery",
                str(t.battery),
                {"unit_of_measurement": "%", "friendly_name": "Tello Bateria"},
            )
            self.ha.set_state(
                f"sensor.{name}_mode",
                self.mode.value,
                {"friendly_name": "Tello Modo"},
            )
            self.ha.set_state(
                f"binary_sensor.{name}_connected",
                "on" if t.connected else "off",
                {"device_class": "connectivity", "friendly_name": "Tello Conectado"},
            )
            self.ha.set_state(
                f"sensor.{name}_ai_status",
                self.ai.status.message,
                {
                    "procedure": self.ai.status.procedure,
                    "step": self.ai.status.step,
                    "friendly_name": "Tello IA",
                },
            )
