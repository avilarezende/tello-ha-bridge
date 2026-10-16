from __future__ import annotations

import logging
import tkinter as tk
from typing import Any

import customtkinter as ctk
import numpy as np
from PIL import Image, ImageTk

from tello_bridge.controller import AppController, ControlMode

logger = logging.getLogger(__name__)

# Paleta simples e legível (sem roxo genérico)
COLORS = {
    "bg": "#0f1419",
    "panel": "#1a222c",
    "panel2": "#243040",
    "accent": "#2dd4a8",
    "accent_dim": "#1a9e7a",
    "warn": "#f5a524",
    "danger": "#ef4444",
    "text": "#e8eef4",
    "muted": "#8b9aab",
    "manual": "#3b82f6",
    "ai": "#2dd4a8",
}


class TelloApp(ctk.CTk):
    def __init__(self, controller: AppController, cfg: dict[str, Any]) -> None:
        super().__init__()
        self.ctrl = controller
        self.cfg = cfg
        app_cfg = cfg.get("app", {})

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.title(app_cfg.get("window_title", "Tello Control"))
        self.geometry("1180x720")
        self.minsize(980, 640)
        self.configure(fg_color=COLORS["bg"])

        self._photo: ImageTk.PhotoImage | None = None
        self._rc = {"lr": 0, "fb": 0, "ud": 0, "yaw": 0}
        self._speed = int(cfg.get("tello", {}).get("speed", 50))
        self._keys_down: set[str] = set()
        self._refresh_ms = int(app_cfg.get("refresh_ms", 500))

        self._build_ui()
        self.ctrl.add_listener(self._schedule_status_refresh)
        self.ctrl.start_services()

        self.bind("<KeyPress>", self._on_key_press)
        self.bind("<KeyRelease>", self._on_key_release)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.after(40, self._video_tick)
        self.after(self._refresh_ms, self._status_tick)
        self.after(80, self._rc_tick)

    # ---------- UI ----------
    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(1, weight=1)

        # Header
        header = ctk.CTkFrame(self, fg_color=COLORS["panel"], corner_radius=0, height=64)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header,
            text="Tello",
            font=ctk.CTkFont(family="Segoe UI", size=26, weight="bold"),
            text_color=COLORS["accent"],
        ).grid(row=0, column=0, padx=(20, 8), pady=14)

        ctk.CTkLabel(
            header,
            text="controle manual · IA · Home Assistant",
            font=ctk.CTkFont(size=13),
            text_color=COLORS["muted"],
        ).grid(row=0, column=1, sticky="w", pady=14)

        self.mode_badge = ctk.CTkLabel(
            header,
            text="  MANUAL  ",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=COLORS["manual"],
            corner_radius=8,
            text_color="#fff",
        )
        self.mode_badge.grid(row=0, column=2, padx=20, pady=14)

        # --- Coluna esquerda: câmera ---
        left = ctk.CTkFrame(self, fg_color=COLORS["bg"])
        left.grid(row=1, column=0, sticky="nsew", padx=(16, 8), pady=(12, 16))
        left.grid_rowconfigure(0, weight=1)
        left.grid_columnconfigure(0, weight=1)

        cam_frame = ctk.CTkFrame(left, fg_color=COLORS["panel"], corner_radius=16)
        cam_frame.grid(row=0, column=0, sticky="nsew")
        cam_frame.grid_rowconfigure(0, weight=1)
        cam_frame.grid_columnconfigure(0, weight=1)

        self.video_label = ctk.CTkLabel(
            cam_frame,
            text="Câmera desligada\n\nConecte o Tello para ver o vídeo",
            font=ctk.CTkFont(size=16),
            text_color=COLORS["muted"],
            fg_color="#0a0e12",
            corner_radius=12,
        )
        self.video_label.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        hint = ctk.CTkLabel(
            left,
            text="Teclado: WASD mover · Q/E girar · R/F subir/descer · Espaço pousar · Esc emergência",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["muted"],
        )
        hint.grid(row=1, column=0, sticky="w", pady=(8, 0))

        # --- Coluna direita: painéis ---
        right = ctk.CTkScrollableFrame(self, fg_color=COLORS["bg"])
        right.grid(row=1, column=1, sticky="nsew", padx=(8, 16), pady=(12, 16))
        right.grid_columnconfigure(0, weight=1)

        self._build_connection_panel(right)
        self._build_mode_panel(right)
        self._build_flight_panel(right)
        self._build_ha_panel(right)
        self._build_ai_panel(right)

    def _card(self, parent: ctk.CTkScrollableFrame, title: str) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, fg_color=COLORS["panel"], corner_radius=14)
        card.grid(sticky="ew", pady=(0, 12))
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            card,
            text=title,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLORS["text"],
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 6))
        body = ctk.CTkFrame(card, fg_color="transparent")
        body.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 14))
        body.grid_columnconfigure(0, weight=1)
        return body

    def _build_connection_panel(self, parent: ctk.CTkScrollableFrame) -> None:
        body = self._card(parent, "Conexão do drone")
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.grid(sticky="ew")
        row.grid_columnconfigure((0, 1), weight=1)

        self.btn_connect = ctk.CTkButton(
            row,
            text="Conectar + câmera",
            fg_color=COLORS["accent_dim"],
            hover_color=COLORS["accent"],
            command=self._connect_tello,
            height=36,
        )
        self.btn_connect.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.btn_disconnect = ctk.CTkButton(
            row,
            text="Desconectar",
            fg_color=COLORS["panel2"],
            hover_color="#334155",
            command=self._disconnect_tello,
            height=36,
        )
        self.btn_disconnect.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self.lbl_tello_status = ctk.CTkLabel(
            body,
            text="Tello: offline",
            font=ctk.CTkFont(size=13),
            text_color=COLORS["muted"],
            anchor="w",
        )
        self.lbl_tello_status.grid(sticky="ew", pady=(10, 0))

        self.lbl_telemetry = ctk.CTkLabel(
            body,
            text="Bateria — · Altura — · Temp —",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text"],
            anchor="w",
        )
        self.lbl_telemetry.grid(sticky="ew", pady=(4, 0))

    def _build_mode_panel(self, parent: ctk.CTkScrollableFrame) -> None:
        body = self._card(parent, "Modo de controle")
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.grid(sticky="ew")
        row.grid_columnconfigure((0, 1), weight=1)

        self.btn_manual = ctk.CTkButton(
            row,
            text="Manual",
            fg_color=COLORS["manual"],
            hover_color="#2563eb",
            command=lambda: self.ctrl.set_mode(ControlMode.MANUAL),
            height=40,
        )
        self.btn_manual.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.btn_ai = ctk.CTkButton(
            row,
            text="IA (Home Assistant)",
            fg_color=COLORS["panel2"],
            hover_color=COLORS["accent_dim"],
            command=lambda: self.ctrl.set_mode(ControlMode.AI),
            height=40,
        )
        self.btn_ai.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self.lbl_mode_help = ctk.CTkLabel(
            body,
            text="No modo IA, o drone segue ordens e procedimentos do Home Assistant.",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["muted"],
            wraplength=360,
            justify="left",
            anchor="w",
        )
        self.lbl_mode_help.grid(sticky="ew", pady=(10, 0))

    def _build_flight_panel(self, parent: ctk.CTkScrollableFrame) -> None:
        body = self._card(parent, "Voo")
        top = ctk.CTkFrame(body, fg_color="transparent")
        top.grid(sticky="ew")
        top.grid_columnconfigure((0, 1, 2), weight=1)

        ctk.CTkButton(
            top, text="Decolar", height=38, fg_color=COLORS["accent_dim"],
            hover_color=COLORS["accent"], command=self.ctrl.takeoff,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkButton(
            top, text="Pousar", height=38, fg_color=COLORS["warn"],
            hover_color="#d97706", text_color="#111", command=self.ctrl.land,
        ).grid(row=0, column=1, sticky="ew", padx=4)
        ctk.CTkButton(
            top, text="Emergência", height=38, fg_color=COLORS["danger"],
            hover_color="#dc2626", command=self.ctrl.emergency,
        ).grid(row=0, column=2, sticky="ew", padx=(4, 0))

        pad = ctk.CTkFrame(body, fg_color="transparent")
        pad.grid(sticky="ew", pady=(12, 0))
        for i in range(3):
            pad.grid_columnconfigure(i, weight=1)

        def mb(r, c, text, direction):
            ctk.CTkButton(
                pad,
                text=text,
                width=70,
                height=36,
                fg_color=COLORS["panel2"],
                hover_color="#334155",
                command=lambda d=direction: self.ctrl.move(d),
            ).grid(row=r, column=c, padx=3, pady=3)

        mb(0, 1, "↑", "forward")
        mb(1, 0, "←", "left")
        mb(1, 1, "↓", "back")
        mb(1, 2, "→", "right")
        mb(2, 0, "⬆", "up")
        mb(2, 2, "⬇", "down")

        rot = ctk.CTkFrame(body, fg_color="transparent")
        rot.grid(sticky="ew", pady=(8, 0))
        rot.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(
            rot, text="Girar ⟲ 45°", height=34, fg_color=COLORS["panel2"],
            hover_color="#334155",
            command=lambda: self.ctrl.tello.rotate_ccw(45) if self.ctrl.manual_allowed() else None,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkButton(
            rot, text="Girar ⟳ 45°", height=34, fg_color=COLORS["panel2"],
            hover_color="#334155",
            command=lambda: self.ctrl.tello.rotate_cw(45) if self.ctrl.manual_allowed() else None,
        ).grid(row=0, column=1, sticky="ew", padx=(4, 0))

    def _build_ha_panel(self, parent: ctk.CTkScrollableFrame) -> None:
        body = self._card(parent, "Home Assistant")
        self.lbl_ha = ctk.CTkLabel(
            body,
            text="Verificando…",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["muted"],
            justify="left",
            anchor="w",
        )
        self.lbl_ha.grid(sticky="ew")

        self.lbl_ha_entities = ctk.CTkLabel(
            body,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["text"],
            justify="left",
            anchor="w",
        )
        self.lbl_ha_entities.grid(sticky="ew", pady=(6, 0))

        row = ctk.CTkFrame(body, fg_color="transparent")
        row.grid(sticky="ew", pady=(10, 0))
        row.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(
            row,
            text="Testar HA",
            height=34,
            fg_color=COLORS["panel2"],
            hover_color="#334155",
            command=self.ctrl.refresh_ha,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.lbl_mqtt = ctk.CTkLabel(
            row,
            text="MQTT: —",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["muted"],
            anchor="w",
        )
        self.lbl_mqtt.grid(row=0, column=1, sticky="w", padx=(8, 0))

    def _build_ai_panel(self, parent: ctk.CTkScrollableFrame) -> None:
        body = self._card(parent, "Procedimentos da IA")
        self.lbl_ai = ctk.CTkLabel(
            body,
            text="IA em espera",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text"],
            wraplength=360,
            justify="left",
            anchor="w",
        )
        self.lbl_ai.grid(sticky="ew")

        procs = self.cfg.get("ai", {}).get(
            "procedures",
            ["hover_scan", "square_patrol", "forward_investigate", "land_safe"],
        )
        labels = {
            "hover_scan": "Varredura (girar 360°)",
            "square_patrol": "Patrulha em quadrado",
            "forward_investigate": "Investigar à frente",
            "land_safe": "Pouso seguro",
        }
        for name in procs:
            ctk.CTkButton(
                body,
                text=labels.get(name, name),
                height=34,
                fg_color=COLORS["panel2"],
                hover_color=COLORS["accent_dim"],
                command=lambda n=name: self.ctrl.start_ai_procedure(n),
            ).grid(sticky="ew", pady=(6, 0))

        ctk.CTkButton(
            body,
            text="Cancelar procedimento",
            height=34,
            fg_color="#7f1d1d",
            hover_color=COLORS["danger"],
            command=self.ctrl.ai.cancel,
        ).grid(sticky="ew", pady=(10, 0))

        self.lbl_ai_log = ctk.CTkLabel(
            body,
            text="",
            font=ctk.CTkFont(size=11),
            text_color=COLORS["muted"],
            justify="left",
            anchor="w",
        )
        self.lbl_ai_log.grid(sticky="ew", pady=(8, 0))

    # ---------- ações ----------
    def _connect_tello(self) -> None:
        self.btn_connect.configure(state="disabled", text="Conectando…")
        self.after(50, self._connect_tello_do)

    def _connect_tello_do(self) -> None:
        ok = self.ctrl.connect_tello(with_video=True)
        self.btn_connect.configure(state="normal", text="Conectar + câmera")
        if not ok:
            self.lbl_tello_status.configure(
                text=f"Falha: {self.ctrl.tello.telemetry.last_error or 'sem resposta'}",
                text_color=COLORS["danger"],
            )

    def _disconnect_tello(self) -> None:
        self.ctrl.disconnect_tello()
        self.video_label.configure(image=None, text="Câmera desligada")
        self._photo = None

    # ---------- loops UI ----------
    def _video_tick(self) -> None:
        try:
            frame = self.ctrl.tello.get_latest_frame()
            if frame is not None:
                self._show_frame(frame)
        except Exception:  # noqa: BLE001
            logger.exception("video tick")
        self.after(33, self._video_tick)

    def _show_frame(self, frame: np.ndarray) -> None:
        # Ajusta ao tamanho do label
        w = max(self.video_label.winfo_width(), 640)
        h = max(self.video_label.winfo_height(), 360)
        img = Image.fromarray(frame)
        img = self._fit_image(img, w - 20, h - 20)
        self._photo = ImageTk.PhotoImage(img)
        self.video_label.configure(image=self._photo, text="")

    @staticmethod
    def _fit_image(img: Image.Image, max_w: int, max_h: int) -> Image.Image:
        if max_w < 50 or max_h < 50:
            return img
        ratio = min(max_w / img.width, max_h / img.height)
        nw, nh = max(1, int(img.width * ratio)), max(1, int(img.height * ratio))
        return img.resize((nw, nh), Image.Resampling.BILINEAR)

    def _schedule_status_refresh(self) -> None:
        self.after(0, self._refresh_status)

    def _status_tick(self) -> None:
        self._refresh_status()
        self.after(self._refresh_ms, self._status_tick)

    def _refresh_status(self) -> None:
        t = self.ctrl.tello.telemetry
        if t.connected:
            self.lbl_tello_status.configure(
                text=f"Tello: online · vídeo {'ligado' if t.video_on else 'off'}",
                text_color=COLORS["accent"],
            )
        else:
            self.lbl_tello_status.configure(text="Tello: offline", text_color=COLORS["muted"])

        self.lbl_telemetry.configure(
            text=(
                f"Bateria {t.battery}%  ·  Altura {t.height_cm} cm  ·  "
                f"Temp {t.temperature:.0f}°C  ·  Yaw {t.yaw}°"
            )
        )

        if self.ctrl.mode == ControlMode.MANUAL:
            self.mode_badge.configure(text="  MANUAL  ", fg_color=COLORS["manual"])
            self.btn_manual.configure(fg_color=COLORS["manual"])
            self.btn_ai.configure(fg_color=COLORS["panel2"])
        else:
            self.mode_badge.configure(text="  IA / HA  ", fg_color=COLORS["ai"])
            self.btn_ai.configure(fg_color=COLORS["accent_dim"])
            self.btn_manual.configure(fg_color=COLORS["panel2"])

        ha = self.ctrl.ha.status
        if ha.connected:
            ha_txt = (
                f"Conectado · {ha.latency_ms:.0f} ms\n"
                f"{ha.url}\n{ha.location_name}"
                + (f" · v{ha.version}" if ha.version else "")
            )
            color = COLORS["accent"]
        else:
            ha_txt = f"Offline\n{ha.url}\n{ha.last_error or 'sem token ou rede'}"
            color = COLORS["warn"]
        self.lbl_ha.configure(text=ha_txt, text_color=color)

        if ha.states_sample:
            lines = [f"{k.split('.')[-1]}: {v}" for k, v in ha.states_sample.items()]
            self.lbl_ha_entities.configure(text="\n".join(lines))
        else:
            self.lbl_ha_entities.configure(text="Entidades Tello ainda não publicadas")

        mqtt_ok = self.ctrl.mqtt.connected
        self.lbl_mqtt.configure(
            text=f"MQTT: {'ok' if mqtt_ok else 'off'}"
            + (f" ({self.ctrl.mqtt.last_error})" if self.ctrl.mqtt.last_error and not mqtt_ok else ""),
            text_color=COLORS["accent"] if mqtt_ok else COLORS["warn"],
        )

        ai = self.ctrl.ai.status
        self.lbl_ai.configure(
            text=f"{'● Ativa' if ai.active else '○ Inativa'} — {ai.message}"
            + (f"\nPasso: {ai.step}" if ai.procedure else "")
        )
        if ai.history:
            self.lbl_ai_log.configure(text="\n".join(ai.history[-5:]))

    def _rc_tick(self) -> None:
        if self.ctrl.manual_allowed() and self.ctrl.tello.telemetry.connected:
            r = self._rc
            if any(v != 0 for v in r.values()):
                self.ctrl.send_rc(r["lr"], r["fb"], r["ud"], r["yaw"])
            elif self._keys_down:
                # teclas soltas mas ainda zerando
                self.ctrl.send_rc(0, 0, 0, 0)
        self.after(50, self._rc_tick)

    # ---------- teclado ----------
    def _on_key_press(self, event: tk.Event) -> None:
        key = (event.keysym or "").lower()
        if key in self._keys_down:
            return
        self._keys_down.add(key)
        s = self._speed
        mapping = {
            "w": ("fb", s),
            "s": ("fb", -s),
            "a": ("lr", -s),
            "d": ("lr", s),
            "q": ("yaw", -s),
            "e": ("yaw", s),
            "r": ("ud", s),
            "f": ("ud", -s),
        }
        if key in mapping and self.ctrl.manual_allowed():
            axis, val = mapping[key]
            self._rc[axis] = val
        elif key == "space":
            self.ctrl.land()
        elif key == "escape":
            self.ctrl.emergency()
        elif key == "t":
            self.ctrl.takeoff()

    def _on_key_release(self, event: tk.Event) -> None:
        key = (event.keysym or "").lower()
        self._keys_down.discard(key)
        mapping = {
            "w": "fb",
            "s": "fb",
            "a": "lr",
            "d": "lr",
            "q": "yaw",
            "e": "yaw",
            "r": "ud",
            "f": "ud",
        }
        if key in mapping:
            axis = mapping[key]
            # se a tecla oposta ainda está pressionada, manter
            opposites = {
                "fb": ("w", "s", self._speed, -self._speed),
                "lr": ("a", "d", -self._speed, self._speed),
                "yaw": ("q", "e", -self._speed, self._speed),
                "ud": ("r", "f", self._speed, -self._speed),
            }
            pos_key, neg_key, pos_v, neg_v = (
                opposites[axis][0],
                opposites[axis][1],
                opposites[axis][2],
                opposites[axis][3],
            )
            if pos_key in self._keys_down:
                self._rc[axis] = pos_v
            elif neg_key in self._keys_down:
                self._rc[axis] = neg_v
            else:
                self._rc[axis] = 0

    def _on_close(self) -> None:
        try:
            self.ctrl.shutdown()
        finally:
            self.destroy()
