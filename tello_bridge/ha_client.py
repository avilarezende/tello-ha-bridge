from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import requests

logger = logging.getLogger(__name__)


@dataclass
class HAStatus:
    connected: bool = False
    url: str = ""
    version: str = ""
    location_name: str = ""
    latency_ms: float = 0.0
    last_error: str = ""
    last_check: float = field(default_factory=time.time)
    states_sample: dict[str, str] = field(default_factory=dict)


class HomeAssistantClient:
    """Cliente REST simples do Home Assistant."""

    def __init__(self, url: str, token: str, device_name: str = "tello_drone") -> None:
        self.url = url.rstrip("/")
        self.token = token or ""
        self.device_name = device_name
        self.status = HAStatus(url=self.url)
        self._session = requests.Session()
        if self.token:
            self._session.headers.update(
                {
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                }
            )

    def check_connection(self) -> bool:
        if not self.token:
            self.status.connected = False
            self.status.last_error = "HA_TOKEN não configurado (.env)"
            self.status.last_check = time.time()
            return False
        try:
            t0 = time.perf_counter()
            r = self._session.get(f"{self.url}/api/", timeout=5)
            latency = (time.perf_counter() - t0) * 1000
            if r.status_code != 200:
                self.status.connected = False
                self.status.last_error = f"HTTP {r.status_code}: {r.text[:120]}"
                self.status.last_check = time.time()
                return False
            data = r.json()
            self.status.connected = True
            self.status.latency_ms = round(latency, 1)
            self.status.version = str(data.get("version", ""))
            self.status.location_name = str(data.get("message", "API OK"))
            self.status.last_error = ""
            self.status.last_check = time.time()
            self._refresh_related_states()
            return True
        except Exception as exc:  # noqa: BLE001
            self.status.connected = False
            self.status.last_error = str(exc)
            self.status.last_check = time.time()
            logger.warning("HA offline: %s", exc)
            return False

    def _refresh_related_states(self) -> None:
        entity_ids = [
            f"sensor.{self.device_name}_battery",
            f"sensor.{self.device_name}_mode",
            f"switch.{self.device_name}_ai_control",
            f"binary_sensor.{self.device_name}_connected",
        ]
        sample: dict[str, str] = {}
        for eid in entity_ids:
            try:
                r = self._session.get(f"{self.url}/api/states/{eid}", timeout=3)
                if r.status_code == 200:
                    st = r.json()
                    sample[eid] = str(st.get("state", "?"))
                else:
                    sample[eid] = f"n/d ({r.status_code})"
            except Exception:  # noqa: BLE001
                sample[eid] = "erro"
        self.status.states_sample = sample

    def call_service(
        self, domain: str, service: str, data: dict[str, Any] | None = None
    ) -> bool:
        if not self.status.connected and not self.check_connection():
            return False
        try:
            r = self._session.post(
                f"{self.url}/api/services/{domain}/{service}",
                json=data or {},
                timeout=8,
            )
            return r.status_code in (200, 201)
        except Exception as exc:  # noqa: BLE001
            self.status.last_error = str(exc)
            return False

    def set_state(
        self, entity_id: str, state: str, attributes: dict[str, Any] | None = None
    ) -> bool:
        payload: dict[str, Any] = {"state": state}
        if attributes:
            payload["attributes"] = attributes
        try:
            r = self._session.post(
                f"{self.url}/api/states/{entity_id}",
                json=payload,
                timeout=5,
            )
            return r.status_code in (200, 201)
        except Exception as exc:  # noqa: BLE001
            self.status.last_error = str(exc)
            return False
