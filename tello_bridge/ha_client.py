from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

import requests

from tello_bridge.security import sanitize_device_name

logger = logging.getLogger(__name__)

_ENTITY_SAFE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


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

    def __init__(
        self,
        url: str,
        token: str,
        device_name: str = "tello_drone",
        verify_tls: bool = True,
    ) -> None:
        self.url = url.rstrip("/")
        self.token = token or ""
        self.device_name = sanitize_device_name(device_name)
        self.verify_tls = verify_tls
        self.status = HAStatus(url=self.url)
        self._session = requests.Session()
        self._session.verify = verify_tls
        if not verify_tls:
            logger.warning(
                "HA verify_tls=false — certificado TLS não será validado (lab only)."
            )
        if self.token:
            self._session.headers.update(
                {
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                }
            )

    def close(self) -> None:
        try:
            self._session.close()
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _safe_http_error(status_code: int, text: str) -> str:
        # Não ecoa corpo completo (pode conter detalhes internos / tokens).
        return f"HTTP {status_code}"

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
                self.status.last_error = self._safe_http_error(r.status_code, r.text)
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
            self.status.last_error = type(exc).__name__
            self.status.last_check = time.time()
            logger.warning("HA offline: %s", type(exc).__name__)
            return False

    def _entity(self, domain: str, suffix: str) -> str:
        eid = f"{domain}.{self.device_name}_{suffix}"
        if not _ENTITY_SAFE.match(eid):
            raise ValueError(f"entity_id inválido: {eid}")
        return eid

    def _refresh_related_states(self) -> None:
        entity_ids = [
            self._entity("sensor", "battery"),
            self._entity("sensor", "mode"),
            self._entity("switch", "ai_control"),
            self._entity("binary_sensor", "connected"),
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
        if not re.match(r"^[a-z][a-z0-9_]*$", domain) or not re.match(
            r"^[a-z][a-z0-9_]*$", service
        ):
            self.status.last_error = "domain/service inválido"
            return False
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
            self.status.last_error = type(exc).__name__
            return False

    def set_state(
        self, entity_id: str, state: str, attributes: dict[str, Any] | None = None
    ) -> bool:
        if not _ENTITY_SAFE.match(entity_id):
            self.status.last_error = "entity_id inválido"
            return False
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
            self.status.last_error = type(exc).__name__
            return False
