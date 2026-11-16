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


def test_security_doc_exists():
    path = ROOT / "SECURITY.md"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "OWASP" in text
    assert "MQTT" in text


def test_ha_package_sets_ai_before_procedure():
    path = ROOT / "homeassistant" / "tello_package.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    run = next(a for a in data["automation"] if a["id"] == "tello_run_procedure_mqtt")
    topics = [
        step["data"]["topic"]
        for step in run["action"]
        if isinstance(step, dict) and step.get("service") == "mqtt.publish"
    ]
    assert "tello/mode" in topics
    assert "tello/ai/procedure" in topics
    assert topics.index("tello/mode") < topics.index("tello/ai/procedure")
