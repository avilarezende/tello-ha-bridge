#!/usr/bin/env python3
"""App de controle DJI Tello com modo Manual/IA e integração Home Assistant."""

from __future__ import annotations

import logging
import sys

from tello_bridge.config_loader import load_config
from tello_bridge.controller import AppController
from tello_bridge.gui import TelloApp


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    cfg = load_config()
    controller = AppController(cfg)
    app = TelloApp(controller, cfg)
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
