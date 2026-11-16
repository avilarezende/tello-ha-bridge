# Segurança — Tello HA Bridge

Guia de ameaças e hardening alinhado ao **OWASP ASVS** / **Top 10** aplicáveis a um bridge IoT (drone + Home Assistant).

## Modelo de ameaça (resumo)

| Ativo | Ameaça | Impacto |
|-------|--------|---------|
| Drone em voo | Comando MQTT/HA não autorizado (takeoff, move) | Colisão / perda de controle |
| `HA_TOKEN` / senha MQTT | Vazamento em git, logs, processo | Acesso total ao HA / broker |
| Broker MQTT aberto | Qualquer host na LAN publica em `tello/#` | Controle remoto do drone |
| HTTP / MQTT sem TLS | MITM na LAN | Roubo de token / injeção de comando |
| Procedimento IA | Loop/erro sem pouso | Drone fica no ar sem piloto |

**Confiança padrão:** o app assume que a LAN + Mosquitto + HA são um perímetro confiável. Em Wi‑Fi compartilhado ou IoT exposta, endureça conforme abaixo.

## Controles já implementados no código

- Secrets via `.env` (`.gitignore`); aviso se token estiver no YAML
- `yaml.safe_load` (sem desserialização insegura)
- Allowlist de comandos e procedimentos MQTT/IA
- Rate limit MQTT (land/emergency isentos)
- `MQTT_COMMAND_SECRET` opcional nos payloads
- Redação de secrets em logs
- Sanitização de `device_name` / `entity_id`
- Validação de `cm`/`degrees` com clamp
- TLS opcional MQTT (`MQTT_TLS`) e `HA_VERIFY_TLS`
- Failsafe: land/emergency sempre; pouso em erro da IA; bateria baixa; disconnect/shutdown voando
- Senha Wi‑Fi do script EDU via prompt/`TELLO_WIFI_PASSWORD` (não só argv)

## Hardening recomendado (prioridade OWASP)

### P1 — Autenticação e autorização (A07 / ASVS V2–V4)

1. **Mosquitto com usuário/senha** e ACL:
   - app: `readwrite tello/#` (ou publish state + subscribe command)
   - HA: publish só em `tello/command`, `tello/mode`, `tello/ai/procedure`
   - negar `#` anônimo
2. Definir `MQTT_USER` / `MQTT_PASSWORD` no `.env`.
3. Ativar `MQTT_COMMAND_SECRET` e incluir `"secret":"..."` nos `mqtt.publish` do HA.
4. Em ambientes sensíveis: `allow_remote_mode_switch: false` e trocar modo só na GUI.

### P2 — Comunicação (A02 Cryptographic Failures)

1. HA via **HTTPS** (`HA_URL=https://...`) com `HA_VERIFY_TLS=true`.
2. MQTT **TLS** porta **8883** (`MQTT_TLS=true`, `MQTT_PORT=8883`).
3. Evitar `MQTT_TLS_INSECURE` / `HA_VERIFY_TLS=false` fora de lab.

### P3 — Secrets management (A02 / A05)

1. Nunca commitar `.env` ou tokens no `config.yaml`.
2. Rotacionar `HA_TOKEN` se vazou.
3. Preferir secret manager / variáveis do systemd em produção (`EnvironmentFile=`).

### P4 — Validação e rate limiting (A03 / A04)

1. Manter allowlists (já no código); não aceitar RC cru via MQTT.
2. Ajustar `rate_limit_max` / `rate_limit_window_s` se necessário.
3. No HA, restringir quem pode acionar `input_button.tello_*` (usuários / áreas).

### P5 — Failsafe do drone (integridade operacional)

1. Manter `security.land_on_ai_error` e `battery_land_percent`.
2. Sempre ter caminho físico/manual para emergency (Esc na GUI).
3. Testar pouso MQTT (`tello/command` → `land`) sem depender do modo IA.

### P6 — Dependências (A06)

1. Rodar periodicamente `pip-audit` / Dependabot.
2. Preferir pin de versões em deploy (`pip freeze` / lockfile).

### P7 — Logging e monitoramento (A09)

1. Não logar tokens; revisar nível INFO em produção.
2. Alertar no HA se `binary_sensor.tello_connected` cair em voo.

## Checklist rápido pré-voo

- [ ] `.env` local, não versionado
- [ ] MQTT com auth (+ TLS se LAN não isolada)
- [ ] ACL Mosquitto limitada a `tello/#`
- [ ] `command_secret` se o broker for compartilhado
- [ ] Teste de land/emergency pela GUI e pelo HA
- [ ] Bateria > margem de failsafe

## Relatório de auditoria

Achados corrigidos e pendências de infra estão no PR de segurança desta branch. Para threat modeling formal (STRIDE), trate o broker MQTT como fronteira de confiança principal.
