from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_ha_package_yaml_parses():
    path = ROOT / "homeassistant" / "tello_package.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "input_select" in data
    assert "tello_mode" in data["input_select"]
    assert "tello_procedure" in data["input_select"]
    assert "input_button" in data
    assert "automation" in data
    assert "mqtt" in data


def test_manual_exists_and_mentions_edu():
    manual = (ROOT / "docs" / "MANUAL.md").read_text(encoding="utf-8")
    assert "Tello EDU" in manual
    assert "Station Mode" in manual
    assert "Home Assistant" in manual
    assert "MQTT" in manual


def test_readme_links_manual():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/MANUAL.md" in readme
