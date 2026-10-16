# Tello HA Bridge

App em Python para controlar o **DJI Tello / Tello EDU**, com **câmera em tempo real**, troca **Manual ↔ IA** e integração com **Home Assistant** (REST + MQTT) para procedimentos automáticos de investigação.

[![CI](https://github.com/avilarezende/tello-ha-bridge/actions/workflows/ci.yml/badge.svg)](https://github.com/avilarezende/tello-ha-bridge/actions/workflows/ci.yml)

## Manual completo

**Leia o guia passo a passo:** [docs/MANUAL.md](docs/MANUAL.md)

Inclui:

- Tello padrão vs **Tello EDU (Station Mode)**
- O que alterar em `.env` / `config.yaml` em cada cenário de rede
- Checklist do que precisa existir no Home Assistant
- Pacote YAML, tópicos MQTT e automações de exemplo

## Início rápido

```powershell
git clone https://github.com/avilarezende/tello-ha-bridge.git
cd tello-ha-bridge
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# edite HA_URL, HA_TOKEN, MQTT_* e TELLO_IP
python main.py
```

## Home Assistant

1. Mosquitto + integração MQTT
2. Copie `homeassistant/tello_package.yaml` → `config/packages/tello_drone.yaml`
3. Habilite packages no `configuration.yaml` (veja o manual)

## Desenvolvimento / CI

```powershell
pip install -r requirements-dev.txt
pytest -q
ruff check tello_bridge tests main.py
```

O workflow está em `.github/workflows/ci.yml` (cópia também em `.github-ci-pending/` se o push do Actions ainda precisar do escopo OAuth `workflow`).

Para ativar o Actions no GitHub (uma vez):

```powershell
gh auth refresh -h github.com -s workflow
git add .github/workflows/ci.yml
git commit -m "ci: enable GitHub Actions"
git push
```

O pipeline roda lint + testes em Python 3.10–3.12 e valida o YAML do HA.

## Estrutura

```
main.py
config.yaml
docs/MANUAL.md
tello_bridge/          # app (GUI, Tello, HA, MQTT, IA)
homeassistant/         # pacote para o HA
tests/                 # pytest
.github/workflows/ci.yml
```

## Licença

MIT — veja [LICENSE](LICENSE).
