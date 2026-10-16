from __future__ import annotations

from unittest.mock import MagicMock, patch

from tello_bridge.ha_client import HomeAssistantClient


def test_check_connection_without_token():
    client = HomeAssistantClient("http://ha.local:8123", token="")
    assert client.check_connection() is False
    assert "HA_TOKEN" in client.status.last_error


@patch("tello_bridge.ha_client.requests.Session")
def test_check_connection_ok(mock_session_cls):
    session = MagicMock()
    mock_session_cls.return_value = session
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"message": "API running.", "version": "2024.1.0"}
    session.get.return_value = resp

    client = HomeAssistantClient("http://ha.local:8123", token="abc")
    # evita chamadas extras de states
    client._refresh_related_states = MagicMock()  # type: ignore[method-assign]
    assert client.check_connection() is True
    assert client.status.connected is True
    assert client.status.version == "2024.1.0"
