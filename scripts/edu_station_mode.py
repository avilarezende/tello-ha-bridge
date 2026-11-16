#!/usr/bin/env python3
"""Configura Tello EDU em Station Mode (entra na Wi‑Fi da LAN).

Uso (PC conectado no Wi‑Fi AP do EDU):
  python scripts/edu_station_mode.py "MEU_SSID"
  # senha pedida via prompt (não fica no histórico do shell)

  # ou via ambiente (evita argv / process list):
  TELLO_WIFI_PASSWORD='...' python scripts/edu_station_mode.py "MEU_SSID"
"""

from __future__ import annotations

import getpass
import os
import sys


def main() -> int:
    if len(sys.argv) not in (2, 3):
        print(
            'Uso: python scripts/edu_station_mode.py "SSID"\n'
            "  Senha: prompt interativo, ou TELLO_WIFI_PASSWORD no ambiente.\n"
            "  (argv com senha ainda aceito, mas desencorajado — fica no histórico.)"
        )
        return 1
    ssid = sys.argv[1]
    if len(sys.argv) == 3:
        password = sys.argv[2]
        print(
            "Aviso: senha via argv aparece no histórico do shell e em `ps`. "
            "Prefira prompt ou TELLO_WIFI_PASSWORD.",
            file=sys.stderr,
        )
    else:
        password = os.getenv("TELLO_WIFI_PASSWORD") or getpass.getpass(
            f"Senha Wi‑Fi para '{ssid}': "
        )
    if not password:
        print("Senha vazia — abortado.", file=sys.stderr)
        return 1

    from djitellopy import Tello

    tello = Tello()
    print("Conectando ao Tello EDU (AP)…")
    tello.connect()
    print(f"Bateria: {tello.get_battery()}%")
    print(f"Enviando para Wi‑Fi '{ssid}'… o drone vai reiniciar.")
    tello.connect_to_wifi(ssid, password)
    print("Comando enviado. Descubra o novo IP no roteador e atualize TELLO_IP.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
