from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


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
    if os.getenv("TELLO_IP"):
        tello["ip"] = os.getenv("TELLO_IP")

    return cfg
