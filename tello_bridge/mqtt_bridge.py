from __future__ import annotations

import json
import logging
import threading
import uuid
from typing import Any, Callable

logger = logging.getLogger(__name__)


class MqttBridge:
    """Publica telemetria e escuta comandos do Home Assistant via MQTT."""

    def __init__(
        self,
        host: str,
        port: int = 1883,
        username: str = "",
        password: str = "",
        topic_prefix: str = "tello",
        keepalive: int = 60,
        tls: bool = False,
        tls_insecure: bool = False,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.prefix = topic_prefix.rstrip("/")
        self.keepalive = keepalive
        self.tls = tls
        self.tls_insecure = tls_insecure
        self.connected = False
        self.last_error = ""
        self._client = None
        self._on_command: Callable[[str, dict[str, Any]], None] | None = None
        self._lock = threading.Lock()
        self._client_id = f"tello_bridge_{uuid.uuid4().hex[:10]}"

    def set_command_handler(
        self, handler: Callable[[str, dict[str, Any]], None]
    ) -> None:
        self._on_command = handler

    def connect(self) -> bool:
        try:
            import paho.mqtt.client as mqtt

            client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=self._client_id,
            )
            if self.username:
                client.username_pw_set(self.username, self.password or None)

            if self.tls:
                # TLS no broker (ex.: 8883). tls_insecure só para lab com cert self-signed.
                client.tls_set()
                if self.tls_insecure:
                    client.tls_insecure_set(True)
                    logger.warning(
                        "MQTT TLS com verificação de certificado desabilitada "
                        "(tls_insecure=true) — use apenas em lab."
                    )

            def on_connect(client, userdata, flags, reason_code, properties=None):  # noqa: ANN001
                # paho v2: reason_code pode ser ReasonCode
                try:
                    ok = int(reason_code) == 0
                except Exception:  # noqa: BLE001
                    ok = str(reason_code) in ("Success", "0")
                self.connected = ok
                if ok:
                    # qos=1 nos comandos: entrega at-least-once
                    client.subscribe(f"{self.prefix}/command", qos=1)
                    client.subscribe(f"{self.prefix}/ai/procedure", qos=1)
                    client.subscribe(f"{self.prefix}/mode", qos=1)
                    self.last_error = ""
                    logger.info(
                        "MQTT conectado em %s:%s (tls=%s)",
                        self.host,
                        self.port,
                        self.tls,
                    )
                else:
                    self.last_error = f"MQTT reason={reason_code}"

            def on_disconnect(client, userdata, flags, reason_code, properties=None):  # noqa: ANN001
                self.connected = False

            def on_message(client, userdata, msg):  # noqa: ANN001
                topic = msg.topic
                try:
                    raw = msg.payload.decode("utf-8")
                    try:
                        payload = json.loads(raw)
                        if not isinstance(payload, dict):
                            payload = {"value": payload}
                    except json.JSONDecodeError:
                        payload = {"value": raw}
                except Exception:  # noqa: BLE001
                    payload = {}
                cmd = topic.split("/")[-1]
                if self._on_command:
                    self._on_command(cmd, payload)

            client.on_connect = on_connect
            client.on_disconnect = on_disconnect
            client.on_message = on_message
            client.connect(self.host, self.port, self.keepalive)
            client.loop_start()
            self._client = client
            return True
        except Exception as exc:  # noqa: BLE001
            self.connected = False
            self.last_error = str(exc)
            logger.warning("MQTT falhou: %s", exc)
            return False

    def disconnect(self) -> None:
        with self._lock:
            if self._client is None:
                return
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:  # noqa: BLE001
                pass
            self._client = None
            self.connected = False

    def publish(self, suffix: str, payload: dict[str, Any] | str | int | float | bool) -> None:
        if self._client is None:
            return
        topic = f"{self.prefix}/{suffix.lstrip('/')}"
        if isinstance(payload, (dict, list)):
            body = json.dumps(payload, ensure_ascii=False)
        else:
            body = str(payload)
        try:
            self._client.publish(topic, body, qos=0, retain=False)
        except Exception as exc:  # noqa: BLE001
            self.last_error = str(exc)
