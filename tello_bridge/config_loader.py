from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from tello_bridge.security import sanitize_device_name

ROOT = Path(__file__).resolve().parent.parent
logger = logging.getLogger(__name__)


def load_config(path: Path | None = None) -> dict[str, Any]:
    load_dotenv(ROOT / ".env")
    cfg_path = path or (ROOT / "config.yaml")
    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    # Overrides do .env
    ha = cfg.setdefault("home_assistant", {})
    mqtt = cfg.setdefault("mqtt", {})
    tello = cfg.setdefault("tello", {})
    security = cfg.setdefault("security", {})

    # Aviso: token no YAML versionado é anti-padrão (preferir .env)
    yaml_token = str(ha.get("token") or "")
    if yaml_token.strip():
        logger.warning(
            "home_assistant.token definido em %s — prefira HA_TOKEN no .env "
            "(não versione secrets).",
            cfg_path.name,
        )

    if os.getenv("HA_URL"):
        ha["url"] = os.getenv("HA_URL")
    if os.getenv("HA_TOKEN"):
        ha["token"] = os.getenv("HA_TOKEN")
    if os.getenv("HA_VERIFY_TLS") is not None:
        ha["verify_tls"] = os.getenv("HA_VERIFY_TLS", "true").lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
    if os.getenv("MQTT_HOST"):
        mqtt["host"] = os.getenv("MQTT_HOST")
    if os.getenv("MQTT_PORT"):
        mqtt["port"] = int(os.getenv("MQTT_PORT", "1883"))
    if os.getenv("MQTT_USER") is not None:
        mqtt["username"] = os.getenv("MQTT_USER", "")
    if os.getenv("MQTT_PASSWORD") is not None:
        mqtt["password"] = os.getenv("MQTT_PASSWORD", "")
    if os.getenv("MQTT_TOPIC_PREFIX"):
        mqtt["topic_prefix"] = os.getenv("MQTT_TOPIC_PREFIX")
    if os.getenv("MQTT_TLS") is not None:
        mqtt["tls"] = os.getenv("MQTT_TLS", "false").lower() in ("1", "true", "yes", "on")
    if os.getenv("MQTT_TLS_INSECURE") is not None:
        mqtt["tls_insecure"] = os.getenv("MQTT_TLS_INSECURE", "false").lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
    if os.getenv("MQTT_COMMAND_SECRET") is not None:
        mqtt["command_secret"] = os.getenv("MQTT_COMMAND_SECRET", "")
    if os.getenv("TELLO_IP"):
        tello["ip"] = os.getenv("TELLO_IP")

    ha["device_name"] = sanitize_device_name(str(ha.get("device_name", "tello_drone")))
    ha.setdefault("verify_tls", True)

    mqtt.setdefault("tls", False)
    mqtt.setdefault("tls_insecure", False)
    mqtt.setdefault("command_secret", "")
    mqtt.setdefault("allow_remote_mode_switch", True)
    mqtt.setdefault("rate_limit_max", 10)
    mqtt.setdefault("rate_limit_window_s", 5.0)

    security.setdefault("battery_land_percent", 15)
    security.setdefault("land_on_ai_error", True)
    security.setdefault("land_on_disconnect", True)

    if not mqtt.get("username") and not mqtt.get("password"):
        logger.warning(
            "MQTT sem credenciais — qualquer cliente no broker pode publicar em "
            "%s/#. Configure MQTT_USER/MQTT_PASSWORD e ACL no Mosquitto.",
            mqtt.get("topic_prefix", "tello"),
        )

    return cfg
