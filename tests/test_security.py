"""Testes das defesas de segurança (OWASP A01/A02/A03/A05)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from tello_bridge.ha_client import HomeAssistantClient
from tello_bridge.mqtt_bridge import MAX_PAYLOAD_BYTES, MqttBridge

# ---------- MQTT: autenticação e validação de entrada ----------


def test_mqtt_prefix_is_sanitized():
    assert MqttBridge(host="x", topic_prefix="../tello/#+ ").prefix == "tello"
    assert MqttBridge(host="x", topic_prefix="").prefix == "tello"
    # separadores/wildcards são removidos (prefixos multi-nível não são aceitos)
    assert MqttBridge(host="x", topic_prefix="casa/drone1").prefix == "casadrone1"
    assert MqttBridge(host="x", topic_prefix="drone_1-a").prefix == "drone_1-a"


def test_mqtt_rejects_command_without_token():
    bridge = MqttBridge(host="x", command_token="segredo")
    seen: list = []
    bridge.set_command_handler(lambda kind, payload: seen.append((kind, payload)))
    bridge.handle_message("tello/command", {"value": "takeoff"})
    bridge.handle_message("tello/command", {"value": "takeoff", "token": "errado"})
    assert seen == []


def test_mqtt_accepts_command_with_token_and_strips_it():
    bridge = MqttBridge(host="x", command_token="segredo")
    seen: list = []
    bridge.set_command_handler(lambda kind, payload: seen.append((kind, payload)))
    bridge.handle_message("tello/command", {"value": "takeoff", "token": "segredo"})
    assert seen == [("command", {"value": "takeoff"})]
    # token nunca é repassado ao handler (não vaza para logs/estado)
    assert "token" not in seen[0][1]


def test_mqtt_without_token_configured_allows_commands():
    bridge = MqttBridge(host="x")
    assert bridge.auth_enabled is False
    seen: list = []
    bridge.set_command_handler(lambda kind, payload: seen.append(kind))
    bridge.handle_message("tello/command", {"value": "land"})
    assert seen == ["command"]


def test_mqtt_parse_payload_happy_path():
    assert MqttBridge.parse_payload(b'{"value": "land"}') == {"value": "land"}
    assert MqttBridge.parse_payload(b"land") == {"value": "land"}
    assert MqttBridge.parse_payload(b"[1, 2]") == {"value": [1, 2]}


def test_mqtt_parse_payload_oversize_rejected():
    assert MqttBridge.parse_payload(b"x" * (MAX_PAYLOAD_BYTES + 1)) is None


def test_mqtt_handler_exception_does_not_propagate():
    bridge = MqttBridge(host="x")

    def boom(kind, payload):
        raise RuntimeError("falha")

    bridge.set_command_handler(boom)
    # não deve lançar (protege a thread de rede do paho)
    bridge.handle_message("tello/command", {"value": "land"})


# ---------- Home Assistant: proteção do token Bearer ----------


def test_ha_refuses_plain_http_with_token_by_default():
    client = HomeAssistantClient("http://ha.local:8123", token="abc")
    assert client.uses_plain_http is True
    assert client.check_connection() is False
    assert "HTTP" in client.status.last_error


@patch("tello_bridge.ha_client.requests.Session")
def test_ha_plain_http_only_when_explicitly_allowed(mock_session_cls):
    session = MagicMock()
    mock_session_cls.return_value = session
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"message": "ok", "version": "1"}
    session.get.return_value = resp

    client = HomeAssistantClient(
        "http://ha.local:8123", token="abc", allow_insecure_http=True
    )
    client._refresh_related_states = MagicMock()  # type: ignore[method-assign]
    assert client.check_connection() is True
    _, kwargs = session.get.call_args
    assert kwargs["verify"] is True


@patch("tello_bridge.ha_client.requests.Session")
def test_ha_verify_tls_flag_reaches_requests(mock_session_cls):
    session = MagicMock()
    mock_session_cls.return_value = session
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"message": "ok"}
    session.get.return_value = resp

    client = HomeAssistantClient("https://ha.local:8123", token="abc", verify_tls=False)
    client._refresh_related_states = MagicMock()  # type: ignore[method-assign]
    assert client.check_connection() is True
    _, kwargs = session.get.call_args
    assert kwargs["verify"] is False


@patch("tello_bridge.ha_client.requests.Session")
def test_ha_error_does_not_leak_response_body(mock_session_cls):
    session = MagicMock()
    mock_session_cls.return_value = session
    resp = MagicMock()
    resp.status_code = 401
    resp.text = "segredo-do-servidor-que-nao-deve-vazar"
    session.get.return_value = resp

    client = HomeAssistantClient("https://ha.local:8123", token="abc")
    assert client.check_connection() is False
    assert "segredo" not in client.status.last_error
    assert "401" in client.status.last_error
