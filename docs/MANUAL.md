# Manual completo — Tello / Tello EDU + App Python + Home Assistant

Repositório: https://github.com/avilarezende/tello-ha-bridge

Este manual cobre **tudo** que você precisa para colocar o drone no ar, o aplicativo no PC e o Home Assistant (HA) enviando ordens de investigação com IA.

---

## Sumário

1. [Visão geral da arquitetura](#1-visão-geral-da-arquitetura)
2. [O que você precisa ter](#2-o-que-você-precisa-ter)
3. [Diferença: Tello vs Tello EDU](#3-diferença-tello-vs-tello-edu)
4. [Configurar o drone](#4-configurar-o-drone)
5. [Configurar o aplicativo Python](#5-configurar-o-aplicativo-python)
6. [Configurar o Home Assistant](#6-configurar-o-home-assistant)
7. [Cenários de rede (o que mudar em cada caso)](#7-cenários-de-rede-o-que-mudar-em-cada-caso)
8. [Uso diário](#8-uso-diário)
9. [Procedimentos da IA e tópicos MQTT](#9-procedimentos-da-ia-e-tópicos-mqtt)
10. [Checklist do que deve existir no HA](#10-checklist-do-que-deve-existir-no-ha)
11. [Solução de problemas](#11-solução-de-problemas)
12. [Segurança](#12-segurança)

---

## 1. Visão geral da arquitetura

```
┌─────────────────┐     UDP SDK / vídeo      ┌──────────────────┐
│  DJI Tello /    │ ◄──────────────────────► │  App Python      │
│  Tello EDU      │                          │  (GUI + IA)      │
└─────────────────┘                          └────────┬─────────┘
                                                      │
                                    REST + MQTT       │
                                                      ▼
                                             ┌──────────────────┐
                                             │ Home Assistant   │
                                             │ + Mosquitto MQTT │
                                             └──────────────────┘
```

| Peça | Função |
|------|--------|
| **Tello / EDU** | Voa e envia câmera/telemetria |
| **App Python** | Controle manual, vídeo, piloto IA, ponte com o HA |
| **Home Assistant** | Dashboard, automações, ordens remotas (“investigar”, pousar, etc.) |
| **MQTT** | Canal em tempo quase real entre HA ↔ app |

O app é o **cérebro local**: o HA não fala UDP com o Tello; ele manda MQTT/REST para o app, que executa no drone.

---

## 2. O que você precisa ter

### Hardware

- DJI **Tello** ou **Tello EDU**
- Bateria carregada + hélice em bom estado
- PC Windows (este projeto foi testado no Windows; Linux/macOS também rodam Python)
- Rede local com Home Assistant (HAOS, Supervised, Container ou Core)

### Software

- Python **3.10+**
- Conta GitHub (para clonar o repo)
- Home Assistant com:
  - Integração **MQTT** (addon Mosquitto recomendado)
  - Token de longa duração (Long-Lived Access Token)
- (Opcional) segundo adaptador de rede no PC se usar Tello **padrão** em modo AP

---

## 3. Diferença: Tello vs Tello EDU

| | Tello (padrão) | Tello EDU |
|--|----------------|-----------|
| Wi‑Fi | Só **Access Point** (`TELLO-XXXX`) | AP **ou Station Mode** (entra na sua Wi‑Fi) |
| Mesma LAN do HA | Difícil sem 2ª placa de rede / bridge | **Ideal** — drone + PC + HA na mesma rede |
| SDK | Sim (UDP) | Sim (UDP) + mais recursos educacionais |
| Este app | Funciona | Funciona (recomendado para HA) |

**Resumo:** se o objetivo principal é Home Assistant na rede local, prefira **Tello EDU em Station Mode**.

---

## 4. Configurar o drone

### 4.1 Tello padrão (modo Access Point)

1. Ligue o Tello.
2. No PC, conecte ao Wi‑Fi `TELLO-XXXXXX` (senha padrão costuma estar na bateria/manual; muitos usam sem senha ou a impressa no equipamento).
3. IP do drone: **`192.168.10.1`** (padrão do SDK).
4. No app, mantenha:

```yaml
# config.yaml
tello:
  ip: "192.168.10.1"
```

ou no `.env`:

```env
TELLO_IP=192.168.10.1
```

**Limitação:** ao conectar no Wi‑Fi do Tello, o PC perde (ou isola) a LAN do HA. Veja [cenário A](#cenário-a--tello-padrão--pc-com-duas-redes).

### 4.2 Tello EDU — Station Mode (recomendado com HA)

Objetivo: o drone entra na **mesma Wi‑Fi** onde está o Home Assistant.

#### Passo a passo típico (SDK EDU)

1. Conecte o PC ao Wi‑Fi AP do Tello EDU (como no Tello normal).
2. Envie o comando de station mode (SSID e senha da sua rede):

```text
command
ap SEU_SSID SUA_SENHA_WIFI
```

Exemplo com `djitellopy` (script único, uma vez):

```python
from djitellopy import Tello
t = Tello()
t.connect()
t.connect_to_wifi("SEU_SSID", "SUA_SENHA_WIFI")
# O drone reinicia e sobe na sua LAN. Anote o IP no roteador/DHCP.
```

3. Descubra o **IP do Tello na LAN** (DHCP do roteador, app do fabricante, ou scanner).
4. Atualize o projeto:

```yaml
# config.yaml
tello:
  ip: "192.168.1.50"   # ← IP real do EDU na sua LAN
```

```env
TELLO_IP=192.168.1.50
```

5. PC e HA devem estar na **mesma rede** (ou com rota entre elas).

#### O que modificar no EDU

| Arquivo | O que mudar |
|---------|-------------|
| `config.yaml` → `tello.ip` | IP do drone na LAN |
| `.env` → `TELLO_IP` | Mesmo IP (sobrescreve o YAML) |
| Firewall do PC | Liberar UDP **8889**, **8890**, **11111** (comando, estado, vídeo) |

### 4.3 Voltar o EDU para modo AP

Se precisar resetar a rede do EDU, siga o procedimento do manual DJI/Ryze (botão de reset / reconfiguração). Depois disso, o IP volta a ser `192.168.10.1` até você configurar o `ap` de novo.

---

## 5. Configurar o aplicativo Python

### 5.1 Instalação

```powershell
git clone https://github.com/SEU_USUARIO/tello-ha-bridge.git
cd tello-ha-bridge
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

### 5.2 Arquivo `.env` (obrigatório para HA)

```env
HA_URL=http://homeassistant.local:8123
HA_TOKEN=cole_aqui_o_long_lived_token

MQTT_HOST=homeassistant.local
MQTT_PORT=1883
MQTT_USER=seu_usuario_mqtt
MQTT_PASSWORD=sua_senha_mqtt
MQTT_TOPIC_PREFIX=tello

TELLO_IP=192.168.10.1
```

| Variável | Quando mudar |
|----------|--------------|
| `HA_URL` | IP/hostname do HA (ex.: `http://192.168.1.10:8123`) |
| `HA_TOKEN` | Sempre — token gerado no perfil do HA |
| `MQTT_*` | Se o broker não for o Mosquitto padrão do HA |
| `TELLO_IP` | EDU em station mode ou IP diferente |

### 5.3 Arquivo `config.yaml` (comportamento de voo / IA)

| Chave | Significado | Quando alterar |
|-------|-------------|----------------|
| `tello.speed` | Velocidade RC 0–100 | Voo mais suave/agressivo |
| `tello.move_distance_cm` | Passo dos botões/procedimentos | Ambientes pequenos → 20–30 |
| `tello.investigate_height_cm` | Altura alvo na varredura | Tetos baixos → reduzir |
| `ai.step_delay_s` | Pausa entre passos da IA | Mais tempo para câmera estabilizar |
| `ai.procedure_timeout_s` | Tempo máximo de um procedimento | Missões longas |
| `home_assistant.device_name` | Prefixo das entidades REST | Se quiser outro nome no HA |
| `mqtt.topic_prefix` | Prefixo dos tópicos | Deve bater com as automações HA |

### 5.4 Gerar o token no Home Assistant

1. HA → clique no seu usuário (canto inferior esquerdo).
2. **Long-Lived Access Tokens** → **Create Token**.
3. Nome: `tello-bridge`.
4. Copie o token **uma vez** para o `.env` (`HA_TOKEN=...`).

### 5.5 Executar

```powershell
.venv\Scripts\activate
python main.py
```

Na GUI: **Conectar + câmera** → teste **Manual** → depois **IA (Home Assistant)**.

---

## 6. Configurar o Home Assistant

### 6.1 Pré-requisitos no HA

Instale e configure:

1. **Mosquitto broker** (Add-on Store → Mosquitto) **ou** outro broker MQTT.
2. Integração **MQTT** (Configurações → Dispositivos e serviços → Adicionar integração → MQTT).
3. Usuário/senha MQTT (se exigido pelo broker) — os mesmos do `.env` do app.
4. (Recomendado) `packages` habilitado.

Em `configuration.yaml`:

```yaml
homeassistant:
  packages: !include_dir_named packages
```

### 6.2 Instalar o pacote deste projeto

1. Copie `homeassistant/tello_package.yaml` para:

```text
config/packages/tello_drone.yaml
```

2. **Reinicie** o Home Assistant (ou recarregue automações + YAML conforme sua versão).

### 6.3 O que o pacote cria no HA

| Tipo | Entidade | Função |
|------|----------|--------|
| `input_select` | `input_select.tello_mode` | Alterna `manual` / `ai` |
| `input_select` | `input_select.tello_procedure` | Escolhe procedimento IA |
| `input_button` | `input_button.tello_run_procedure` | Dispara o procedimento via MQTT |
| `input_button` | `input_button.tello_land` | Ordem de pouso |
| `input_button` | `input_button.tello_takeoff` | Ordem de decolagem |
| Automações | `tello_*_mqtt` | Publicam nos tópicos `tello/...` |
| MQTT sensor | bateria, modo, status IA | Leitura (app → HA) |
| MQTT binary_sensor | conectado | Online/offline do drone |

### 6.4 Entidades que o **app** também publica via REST

Com `HA_TOKEN` válido, o app cria/atualiza (prefixo `device_name`, padrão `tello_drone`):

| Entidade | Conteúdo |
|----------|----------|
| `sensor.tello_drone_battery` | % bateria |
| `sensor.tello_drone_mode` | `manual` / `ai` |
| `binary_sensor.tello_drone_connected` | conectado |
| `sensor.tello_drone_ai_status` | mensagem/passo da IA |

Se mudar `home_assistant.device_name` no `config.yaml`, esses IDs mudam — ajuste dashboards e automações.

### 6.5 Dashboard sugerido (Lovelace)

Crie um cartão com:

- `input_select.tello_mode`
- `input_select.tello_procedure`
- `input_button.tello_run_procedure`
- `input_button.tello_land`
- sensores de bateria / conectado / status IA

Exemplo mínimo YAML de cartão:

```yaml
type: entities
title: Tello
entities:
  - input_select.tello_mode
  - input_select.tello_procedure
  - input_button.tello_run_procedure
  - input_button.tello_takeoff
  - input_button.tello_land
  - sensor.tello_drone_battery
  - sensor.tello_drone_mode
  - sensor.tello_drone_ai_status
  - binary_sensor.tello_drone_connected
```

### 6.6 Automação de exemplo (investigar quando um sensor dispara)

```yaml
automation:
  - alias: "Investigar sala quando movimento"
    trigger:
      - platform: state
        entity_id: binary_sensor.sala_movimento
        to: "on"
    action:
      - service: input_select.select_option
        target:
          entity_id: input_select.tello_mode
        data:
          option: ai
      - service: input_select.select_option
        target:
          entity_id: input_select.tello_procedure
        data:
          option: forward_investigate
      - service: input_button.press
        target:
          entity_id: input_button.tello_run_procedure
```

O app precisa estar **aberto**, no modo **IA**, com Tello conectado.

---

## 7. Cenários de rede (o que mudar em cada caso)

### Cenário A — Tello padrão + PC com duas redes

**Quando:** Tello comum (só AP) + HA na LAN.

| Item | Configuração |
|------|----------------|
| Wi‑Fi do PC | Conectado em `TELLO-XXXX` |
| Ethernet / 2ª Wi‑Fi | Ligada na LAN do HA |
| `TELLO_IP` | `192.168.10.1` |
| `HA_URL` / `MQTT_HOST` | IP do HA na LAN (ex. `192.168.1.10`) — **não** use só hostname se a DNS falhar na rede mista |
| Rota Windows | Garantir que `192.168.10.0/24` → Wi‑Fi Tello e LAN → Ethernet |

**O que modificar:** `.env` com IPs numéricos do HA; nada especial no pacote HA.

### Cenário B — Tello EDU em Station Mode (recomendado)

| Item | Configuração |
|------|----------------|
| Drone | Mesma Wi‑Fi do HA |
| PC | Mesma Wi‑Fi/LAN |
| `TELLO_IP` | IP DHCP do EDU |
| `HA_URL` / `MQTT_HOST` | `homeassistant.local` ou IP do HA |

**O que modificar:** só `TELLO_IP` após o `ap SSID SENHA`.

### Cenário C — Tudo no mesmo PC de desenvolvimento (sem voo)

| Item | Configuração |
|------|----------------|
| Tello | Desligado |
| App | Abre GUI; painel HA/MQTT ainda pode ser testado |
| Testes | `pytest` no CI (sem hardware) |

### Cenário D — Broker MQTT externo (não é o do HA)

| Item | Configuração |
|------|----------------|
| `.env` `MQTT_HOST/PORT/USER/PASSWORD` | Dados do broker |
| Integração MQTT do HA | Apontar para o **mesmo** broker |
| Prefixo | `MQTT_TOPIC_PREFIX` = mesmo valor nas automações (`tello/...`) |

---

## 8. Uso diário

1. Ligue o Tello / EDU e aguarde LEDs estáveis.
2. Garanta rede (AP ou station) conforme seu cenário.
3. Inicie o HA (se ainda não estiver).
4. Rode `python main.py`.
5. Confira no painel direito: **HA conectado** e **MQTT ok**.
6. **Conectar + câmera**.
7. Voe em **Manual** para validar.
8. Troque para **IA** e dispare um procedimento pelo app **ou** pelo HA.

### Teclado (modo Manual)

| Tecla | Ação |
|-------|------|
| W A S D | Frente / esquerda / trás / direita |
| Q E | Girar |
| R F | Subir / descer |
| T | Decolar |
| Espaço | Pousar |
| Esc | Emergência |

**Pousar** e **Emergência** funcionam também no modo IA.

---

## 9. Procedimentos da IA e tópicos MQTT

### Procedimentos embutidos

| Nome | O que faz |
|------|-----------|
| `hover_scan` | Decola, sobe e gira 360° (varredura) |
| `square_patrol` | Patrulha em quadrado |
| `forward_investigate` | Avança e olha esquerda/direita |
| `land_safe` | Pouso |

Para adicionar um novo: implemente em `tello_bridge/ai_pilot.py`, liste em `config.yaml` → `ai.procedures` e em `input_select.tello_procedure` no pacote HA.

### Tópicos MQTT

| Tópico | Direção | Payload exemplo |
|--------|---------|-----------------|
| `tello/mode` | HA → app | `{"value":"ai"}` |
| `tello/command` | HA → app | `{"value":"land"}` |
| `tello/ai/procedure` | HA → app | `{"value":"hover_scan"}` |
| `tello/state` | app → HA | JSON telemetria |
| `tello/battery` | app → HA | `85` |
| `tello/mode/state` | app → HA | `manual` / `ai` |
| `tello/connected` | app → HA | `ON` / `OFF` |
| `tello/ai/status` | app → HA | `{"message":"...","step":"..."}` |

Se mudar `MQTT_TOPIC_PREFIX` para `drone1`, altere **todas** as automações do pacote para `drone1/...`.

---

## 10. Checklist do que deve existir no HA

Antes de operar com IA remota, confira:

- [ ] Mosquitto (ou broker) **rodando**
- [ ] Integração **MQTT** conectada no HA
- [ ] Usuário MQTT = credenciais do `.env` do app
- [ ] `packages/tello_drone.yaml` carregado (sem erro de YAML)
- [ ] Entidades: `input_select.tello_mode`, `tello_procedure`, botões land/takeoff/run
- [ ] Automações `Tello — *` **ligadas**
- [ ] Token long-lived no `.env` do app
- [ ] App aberto mostra **HA: Conectado** e **MQTT: ok**
- [ ] Após conectar o drone, sensores de bateria/conectado atualizam
- [ ] Teste: mudar modo no HA → badge do app muda para IA
- [ ] Teste: `land_safe` ou botão Pousar com drone no chão (sem hélices, se possível)

---

## 11. Solução de problemas

| Sintoma | Causa provável | Ação |
|---------|----------------|------|
| Tello não conecta | Wi‑Fi errado / IP errado | Conferir `TELLO_IP`; ping `192.168.10.1` |
| Sem vídeo | Stream off / codec | Clicar Conectar + câmera; reinstalar `av` e `opencv-python` |
| HA offline no app | Token/URL | Testar `HA_URL/api/` no navegador; regenerar token |
| MQTT off | Broker/credencial | Ver logs do Mosquitto; porta 1883 |
| Ordem do HA não move o drone | Modo manual / app fechado | App aberto + modo **IA** |
| EDU some após `ap` | IP DHCP mudou | Reservar IP no roteador; atualizar `TELLO_IP` |
| Firewall | UDP bloqueado | Liberar 8889/8890/11111 |

---

## 12. Segurança

- Área livre, sem pessoas sob o drone.
- Bateria > 20% para procedimentos longos.
- Sempre saiba onde está o botão **Emergência**.
- Não exponha `HA_TOKEN` nem senha MQTT no GitHub (use só `.env` local).
- Em ambientes internos, restrinja o broker MQTT à LAN.

---

## Referências rápidas de arquivos

| Arquivo | Papel |
|---------|--------|
| `main.py` | Entrada do app |
| `config.yaml` | Ajustes de voo/IA/HA |
| `.env` / `.env.example` | Segredos e hosts |
| `tello_bridge/` | Código (Tello, HA, MQTT, IA, GUI) |
| `homeassistant/tello_package.yaml` | Pacote para o HA |
| `docs/MANUAL.md` | Este manual |
