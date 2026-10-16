from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TelloTelemetry:
    connected: bool = False
    battery: int = 0
    height_cm: int = 0
    temperature: float = 0.0
    pitch: int = 0
    roll: int = 0
    yaw: int = 0
    speed_x: int = 0
    speed_y: int = 0
    speed_z: int = 0
    flying: bool = False
    video_on: bool = False
    last_error: str = ""
    updated_at: float = field(default_factory=time.time)


class TelloClient:
    """Wrapper do DJI Tello com telemetria e frames de vídeo."""

    def __init__(self, ip: str = "192.168.10.1", speed: int = 50) -> None:
        self.ip = ip
        self.speed = speed
        self._drone = None
        self.telemetry = TelloTelemetry()
        self._lock = threading.RLock()
        self._poll_thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._on_frame: Callable[[np.ndarray], None] | None = None
        self._latest_frame: np.ndarray | None = None
        self._frame_lock = threading.Lock()

    def set_frame_callback(self, cb: Callable[[np.ndarray], None] | None) -> None:
        self._on_frame = cb

    def get_latest_frame(self) -> np.ndarray | None:
        with self._frame_lock:
            if self._latest_frame is None:
                return None
            return self._latest_frame.copy()

    def connect(self) -> bool:
        try:
            from djitellopy import Tello

            with self._lock:
                if self._drone is not None:
                    return True
                drone = Tello(host=self.ip)
                drone.connect()
                drone.set_speed(self.speed)
                self._drone = drone
                self.telemetry.connected = True
                self.telemetry.last_error = ""
                self._stop.clear()
                self._poll_thread = threading.Thread(
                    target=self._poll_loop, name="tello-poll", daemon=True
                )
                self._poll_thread.start()
                logger.info("Tello conectado em %s (bateria %s%%)", self.ip, drone.get_battery())
                return True
        except Exception as exc:  # noqa: BLE001
            self.telemetry.connected = False
            self.telemetry.last_error = str(exc)
            logger.exception("Falha ao conectar no Tello")
            return False

    def disconnect(self) -> None:
        self._stop.set()
        with self._lock:
            if self._drone is None:
                return
            try:
                if self.telemetry.video_on:
                    self._drone.streamoff()
            except Exception:  # noqa: BLE001
                pass
            try:
                self._drone.end()
            except Exception:  # noqa: BLE001
                pass
            self._drone = None
            self.telemetry.connected = False
            self.telemetry.video_on = False
            self.telemetry.flying = False

    def start_video(self) -> bool:
        with self._lock:
            if self._drone is None:
                return False
            try:
                self._drone.streamon()
                self.telemetry.video_on = True
                return True
            except Exception as exc:  # noqa: BLE001
                self.telemetry.last_error = str(exc)
                logger.exception("Falha ao iniciar vídeo")
                return False

    def stop_video(self) -> None:
        with self._lock:
            if self._drone is None:
                return
            try:
                self._drone.streamoff()
            except Exception:  # noqa: BLE001
                pass
            self.telemetry.video_on = False

    def takeoff(self) -> bool:
        return self._cmd(lambda d: d.takeoff(), flying=True)

    def land(self) -> bool:
        return self._cmd(lambda d: d.land(), flying=False)

    def emergency(self) -> bool:
        return self._cmd(lambda d: d.emergency(), flying=False)

    def send_rc(self, lr: int, fb: int, ud: int, yaw: int) -> bool:
        """Controle contínuo: left-right, forward-back, up-down, yaw (-100..100)."""
        with self._lock:
            if self._drone is None or not self.telemetry.connected:
                return False
            try:
                self._drone.send_rc_control(
                    int(np.clip(lr, -100, 100)),
                    int(np.clip(fb, -100, 100)),
                    int(np.clip(ud, -100, 100)),
                    int(np.clip(yaw, -100, 100)),
                )
                return True
            except Exception as exc:  # noqa: BLE001
                self.telemetry.last_error = str(exc)
                return False

    def move(self, direction: str, cm: int) -> bool:
        mapping = {
            "forward": "move_forward",
            "back": "move_back",
            "left": "move_left",
            "right": "move_right",
            "up": "move_up",
            "down": "move_down",
        }
        method = mapping.get(direction)
        if not method:
            return False
        cm = int(np.clip(cm, 20, 500))
        return self._cmd(lambda d: getattr(d, method)(cm))

    def rotate_cw(self, degrees: int) -> bool:
        degrees = int(np.clip(degrees, 1, 360))
        return self._cmd(lambda d: d.rotate_clockwise(degrees))

    def rotate_ccw(self, degrees: int) -> bool:
        degrees = int(np.clip(degrees, 1, 360))
        return self._cmd(lambda d: d.rotate_counter_clockwise(degrees))

    def hover(self) -> bool:
        return self.send_rc(0, 0, 0, 0)

    def _cmd(self, fn, flying: bool | None = None) -> bool:
        with self._lock:
            if self._drone is None or not self.telemetry.connected:
                self.telemetry.last_error = "Tello não conectado"
                return False
            try:
                fn(self._drone)
                if flying is not None:
                    self.telemetry.flying = flying
                self.telemetry.last_error = ""
                return True
            except Exception as exc:  # noqa: BLE001
                self.telemetry.last_error = str(exc)
                logger.exception("Comando Tello falhou")
                return False

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                drone = self._drone
            if drone is None:
                break
            try:
                self.telemetry.battery = int(drone.get_battery())
                self.telemetry.height_cm = int(drone.get_height())
                try:
                    self.telemetry.temperature = float(drone.get_temperature())
                except Exception:  # noqa: BLE001
                    pass
                try:
                    self.telemetry.pitch = int(drone.get_pitch())
                    self.telemetry.roll = int(drone.get_roll())
                    self.telemetry.yaw = int(drone.get_yaw())
                except Exception:  # noqa: BLE001
                    pass
                self.telemetry.updated_at = time.time()
                self.telemetry.connected = True
            except Exception as exc:  # noqa: BLE001
                self.telemetry.last_error = str(exc)

            if self.telemetry.video_on:
                try:
                    frame = drone.get_frame_read().frame
                    if frame is not None:
                        # djitellopy entrega BGR; GUI usa RGB
                        rgb = frame[:, :, ::-1].copy()
                        with self._frame_lock:
                            self._latest_frame = rgb
                        if self._on_frame:
                            self._on_frame(rgb)
                except Exception:  # noqa: BLE001
                    pass

            time.sleep(0.05)
