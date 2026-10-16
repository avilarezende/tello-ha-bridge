from __future__ import annotations

from pathlib import Path

from tello_bridge.config_loader import load_config


def test_load_config_has_required_sections(tmp_path: Path, monkeypatch):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        """
tello:
  ip: "192.168.10.1"
  speed: 40
home_assistant:
  url: "http://ha.local:8123"
  token: ""
  device_name: "tello_drone"
mqtt:
  host: "ha.local"
  port: 1883
  topic_prefix: "tello"
ai:
  procedures:
    - hover_scan
app:
  window_title: "Test"
  refresh_ms: 500
""",
        encoding="utf-8",
    )
    monkeypatch.delenv("HA_URL", raising=False)
    monkeypatch.delenv("HA_TOKEN", raising=False)
    monkeypatch.delenv("TELLO_IP", raising=False)

    cfg = load_config(cfg_file)
    assert cfg["tello"]["ip"] == "192.168.10.1"
    assert cfg["tello"]["speed"] == 40
    assert cfg["home_assistant"]["device_name"] == "tello_drone"
    assert "hover_scan" in cfg["ai"]["procedures"]


def test_env_overrides_config(tmp_path: Path, monkeypatch):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        """
tello:
  ip: "192.168.10.1"
home_assistant:
  url: "http://old:8123"
  token: "old"
mqtt:
  host: "old-mqtt"
  port: 1883
  topic_prefix: "tello"
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("HA_URL", "http://new-ha:8123")
    monkeypatch.setenv("HA_TOKEN", "new-token")
    monkeypatch.setenv("MQTT_HOST", "new-mqtt")
    monkeypatch.setenv("MQTT_PORT", "1884")
    monkeypatch.setenv("TELLO_IP", "10.0.0.9")

    cfg = load_config(cfg_file)
    assert cfg["home_assistant"]["url"] == "http://new-ha:8123"
    assert cfg["home_assistant"]["token"] == "new-token"
    assert cfg["mqtt"]["host"] == "new-mqtt"
    assert cfg["mqtt"]["port"] == 1884
    assert cfg["tello"]["ip"] == "10.0.0.9"
