"""Controles de segurança compartilhados (allowlists, rate limit, sanitização)."""

from __future__ import annotations

import re
import threading
import time
from typing import Any

# Comandos MQTT/IA permitidos (OWASP: allowlist de ações)
ALLOWED_COMMANDS = frozenset(
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

# Procedimentos conhecidos (deve coincidir com config.yaml / pacote HA)
ALLOWED_PROCEDURES = frozenset(
    {
        "hover_scan",
        "square_patrol",
        "forward_investigate",
        "land_safe",
    }
)

# Failsafe sempre aceitos, mesmo fora do modo IA
SAFETY_COMMANDS = frozenset({"land", "emergency"})

_DEVICE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SECRET_KEYS = frozenset(
    {"token", "password", "passwd", "secret", "authorization", "api_key", "apikey"}
)


def sanitize_device_name(name: str, default: str = "tello_drone") -> str:
    """Garante entity_id seguro para o Home Assistant (sem path/injection)."""
    cleaned = (name or default).strip().lower().replace("-", "_").replace(" ", "_")
    if not _DEVICE_NAME_RE.match(cleaned):
        return default
    return cleaned


def parse_int_clamped(
    value: Any, default: int, minimum: int, maximum: int
) -> int:
    """Converte valor arbitrário em int limitado; ignora lixo sem lançar."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    return max(minimum, min(maximum, n))


def redact_mapping(data: Any) -> Any:
    """Remove valores sensíveis de dicts/listas para logs."""
    if isinstance(data, dict):
        out: dict[str, Any] = {}
        for k, v in data.items():
            key = str(k).lower()
            if key in _SECRET_KEYS or any(s in key for s in ("token", "password", "secret")):
                out[k] = "***"
            else:
                out[k] = redact_mapping(v)
        return out
    if isinstance(data, list):
        return [redact_mapping(x) for x in data]
    return data


def command_secret_ok(payload: dict[str, Any], expected: str) -> bool:
    """Valida segredo compartilhado opcional em payloads MQTT."""
    if not expected:
        return True
    got = str(payload.get("secret") or payload.get("token") or "")
    return got == expected and got != ""


class RateLimiter:
    """Limita eventos por janela deslizante (thread-safe)."""

    def __init__(self, max_events: int = 10, window_s: float = 5.0) -> None:
        self.max_events = max(1, max_events)
        self.window_s = max(0.1, window_s)
        self._times: list[float] = []
        self._lock = threading.Lock()

    def allow(self) -> bool:
        now = time.monotonic()
        with self._lock:
            cutoff = now - self.window_s
            self._times = [t for t in self._times if t >= cutoff]
            if len(self._times) >= self.max_events:
                return False
            self._times.append(now)
            return True
