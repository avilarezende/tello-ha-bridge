#!/usr/bin/env python3
"""Configura Tello EDU em Station Mode (entra na Wi‑Fi da LAN).

Uso (PC conectado no Wi‑Fi AP do EDU):
  python scripts/edu_station_mode.py "MEU_SSID" "MINHA_SENHA"
"""

from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) != 3:
        print("Uso: python scripts/edu_station_mode.py \"SSID\" \"SENHA\"")
        return 1
    ssid, password = sys.argv[1], sys.argv[2]
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
