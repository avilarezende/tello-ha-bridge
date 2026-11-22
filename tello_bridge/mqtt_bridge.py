from __future__ import annotations

import hmac
import json
import logging
import os
import re
import socket
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Tamanho máximo aceito para um payload MQTT de comando (defesa contra abuso/DoS).
MAX_PAYLOAD_BYTES = 4096

# Prefixo de tópico: apenas caracteres seguros (bloqueia wildcards +/# e separadores).
_PREFIX_RE = re.compile(r"[^A-Za-z0-9_-]")


class MqttBridge:
    """Publica telemetria e escuta comandos do Home Assistant via MQTT.

    Segurança (OWASP):
    - A01: quando ``command_token`` está definido, todo comando precisa trazer o
      campo ``token`` no JSON, verificado em tempo constante.
    - A02: suporte a TLS (``use_tls``); sem ele, credenciais trafegam em claro
      e um aviso é registrado em log.
    """

    def __init__(
        self,
        host: str,
        port: int = 1883,
        username: str = "",
        password: str = "",
        topic_prefix: str = "tello",
        keepalive: int = 60,
        *,
        use_tls: bool = False,
        tls_insecure: bool = False,
        command_token: str = "",
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.prefix = self.sanitize_prefix(topic_prefix)
        self.keepalive = keepalive
        self.use_tls = use_tls
        self.tls_insecure = tls_insecure
        self._command_token = command_token or ""
        self.connected = False
        self.last_error = ""
        self._client = None
        self._on_command: Callable[[str, dict[str, Any]], None] | None = None
        self._on_rejected: Callable[[str], None] | None = None
        self._lock = threading.Lock()

    @staticmethod
    def sanitize_prefix(prefix: str) -> str:
        """Remove caracteres perigosos (+, #, /) do prefixo de tópico."""
        cleaned = _PREFIX_RE.sub("", (prefix or "").strip().strip("/"))[:32]
        return cleaned or "tello"

    @property
    def auth_enabled(self) -> bool:
        return bool(self._command_token)

    def set_command_handler(
        self, handler: Callable[[str, dict[str, Any]], None]
    ) -> None:
        self._on_command = handler

    def set_rejected_handler(self, handler: Callable[[str], None] | None) -> None:
        self._on_rejected = handler

    def connect(self) -> bool:
        if not self._command_token:
            logger.warning(
                "MQTT sem command_token — QUALQUER cliente do broker pode controlar "
                "o drone. Defina MQTT_COMMAND_TOKEN no .env."
            )
        if not self.use_tls:
            logger.warning(
                "MQTT sem TLS — credenciais e comandos trafegam em claro. "
                "Ative 'mqtt.tls' (porta 8883) em produção."
            )
        try:
            import paho.mqtt.client as mqtt

            # client_id único evita que duas instâncias se derrubem do broker.
            client_id = f"tello_bridge_{socket.gethostname()}_{os.getpid()}"
            client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=client_id,
            )
            if self.username:
                client.username_pw_set(self.username, self.password or None)
            if self.use_tls:
                client.tls_set()
                if self.tls_insecure:
                    # Aceita certificado inválido/autoassinado: apenas testes locais.
                    logger.warning("MQTT TLS sem verificação de certificado (tls_insecure)")
                    client.tls_insecure_set(True)

            def on_connect(client, userdata, flags, reason_code, properties=None):  # noqa: ANN001
                # paho v2: reason_code pode ser ReasonCode
                try:
                    ok = int(reason_code) == 0
                except Exception:  # noqa: BLE001
                    ok = str(reason_code) in ("Success", "0")
                self.connected = ok
                if ok:
                    client.subscribe(f"{self.prefix}/command")
                    client.subscribe(f"{self.prefix}/ai/procedure")
                    client.subscribe(f"{self.prefix}/mode")
                    self.last_error = ""
                    logger.info("MQTT conectado em %s:%s", self.host, self.port)
                else:
                    self.last_error = f"MQTT reason={reason_code}"

            def on_disconnect(client, userdata, flags, reason_code, properties=None):  # noqa: ANN001
                self.connected = False

            def on_message(client, userdata, msg):  # noqa: ANN001
                payload = self.parse_payload(msg.payload)
                if payload is None:
                    return
                self.handle_message(msg.topic, payload)

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

    @staticmethod
    def parse_payload(raw_bytes: bytes) -> dict[str, Any] | None:
        """Decodifica e valida o payload; retorna None se deve ser descartado."""
        if len(raw_bytes) > MAX_PAYLOAD_BYTES:
            logger.warning(
                "MQTT payload grande demais (%d bytes) — descartado", len(raw_bytes)
            )
            return None
        try:
            raw = raw_bytes.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"value": raw}
        if not isinstance(payload, dict):
            payload = {"value": payload}
        return payload

    def _authorized(self, payload: dict[str, Any]) -> bool:
        """Verifica o segredo compartilhado com comparação em tempo constante."""
        if not self._command_token:
            return True
        sent = payload.get("token")
        if not isinstance(sent, str) or not sent:
            return False
        return hmac.compare_digest(
            sent.encode("utf-8"), self._command_token.encode("utf-8")
        )

    def handle_message(self, topic: str, payload: dict[str, Any]) -> None:
        """Ponto único de entrada de comandos: autentica e despacha com segurança."""
        if not self._authorized(payload):
            logger.warning(
                "Comando MQTT rejeitado (token ausente/inválido) no tópico %s", topic
            )
            if self._on_rejected:
                try:
                    self._on_rejected(topic)
                except Exception:  # noqa: BLE001
                    logger.exception("Falha no handler de comando rejeitado")
            return
        # Nunca repassa o token adiante (evita vazamento em logs/estado).
        clean = {k: v for k, v in payload.items() if k != "token"}
        cmd = topic.split("/")[-1]
        if self._on_command:
            try:
                self._on_command(cmd, clean)
            except Exception:  # noqa: BLE001
                logger.exception("Falha no handler de comando MQTT")

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
