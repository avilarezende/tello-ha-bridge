from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent


def _env_bool(name: str) -> bool | None:
    raw = os.getenv(name)
    if raw is None:
        return None
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("%s inválido (%r) — usando %s", name, raw, default)
        return default


def load_config(path: Path | None = None) -> dict[str, Any]:
    load_dotenv(ROOT / ".env")
    cfg_path = path or (ROOT / "config.yaml")
    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    # Overrides do .env
    ha = cfg.setdefault("home_assistant", {})
    mqtt = cfg.setdefault("mqtt", {})
    tello = cfg.setdefault("tello", {})

    if os.getenv("HA_URL"):
        ha["url"] = os.getenv("HA_URL")
    if os.getenv("HA_TOKEN"):
        ha["token"] = os.getenv("HA_TOKEN")
    if (v := _env_bool("HA_VERIFY_TLS")) is not None:
        ha["verify_tls"] = v
    if (v := _env_bool("HA_ALLOW_INSECURE_HTTP")) is not None:
        ha["allow_insecure_http"] = v

    if os.getenv("MQTT_HOST"):
        mqtt["host"] = os.getenv("MQTT_HOST")
    if os.getenv("MQTT_PORT"):
        default_port = 8883 if _env_bool("MQTT_TLS") else 1883
        mqtt["port"] = _env_int("MQTT_PORT", default_port)
    if os.getenv("MQTT_USER") is not None:
        mqtt["username"] = os.getenv("MQTT_USER", "")
    if os.getenv("MQTT_PASSWORD") is not None:
        mqtt["password"] = os.getenv("MQTT_PASSWORD", "")
    if os.getenv("MQTT_TOPIC_PREFIX"):
        mqtt["topic_prefix"] = os.getenv("MQTT_TOPIC_PREFIX")
    if (v := _env_bool("MQTT_TLS")) is not None:
        mqtt["tls"] = v
    if (v := _env_bool("MQTT_TLS_INSECURE")) is not None:
        mqtt["tls_insecure"] = v
    if os.getenv("MQTT_COMMAND_TOKEN"):
        mqtt["command_token"] = os.getenv("MQTT_COMMAND_TOKEN")

    if os.getenv("TELLO_IP"):
        tello["ip"] = os.getenv("TELLO_IP")
    if os.getenv("MIN_BATTERY_PCT"):
        tello["min_battery_pct"] = _env_int("MIN_BATTERY_PCT", 15)
    if os.getenv("CRITICAL_BATTERY_PCT"):
        tello["critical_battery_pct"] = _env_int("CRITICAL_BATTERY_PCT", 10)

    # A05: segredos em texto claro no config.yaml correm risco de ir pro Git.
    if ha.get("token"):
        logger.warning(
            "Token do HA definido no config.yaml — prefira HA_TOKEN no .env "
            "(o config.yaml pode ser commitado por engano)."
        )
    if mqtt.get("password"):
        logger.warning(
            "Senha MQTT definida no config.yaml — prefira MQTT_PASSWORD no .env."
        )

    return cfg
