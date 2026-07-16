import atexit
import json
import os
import queue
import signal
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.messagebox as messagebox
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import customtkinter as ctk
import pystray
from PIL import Image, ImageDraw

from portal_settings_dialog import PortalSettingsDialog

# Add current directory to path for shared module import
sys.path.insert(0, str(Path(__file__).resolve().parent))

import contextlib

from manager_theme import (
    BG_CARD,
    BG_INNER,
    BUTTON_WIDTH,
    FONT_BADGE,
    FONT_LOG,
    FONT_LOG_COMPACT,
    FONT_PANEL_TITLE,
    FONT_PANEL_TITLE_COMPACT,
    FONT_STATUS,
    FONT_TITLE,
    GAP_CONTROL,
    LOG_BG,
    LOG_BORDER,
    LOG_ERROR,
    LOG_INFO,
    LOG_SUCCESS,
    LOG_WARN,
    PAD_OUTER,
    PAD_PANEL,
    PAD_TIGHT,
    PILL_RUNNING_BG,
    PILL_RUNNING_TEXT,
    PILL_STOPPED_BG,
    PILL_STOPPED_TEXT,
    RADIUS_BADGE,
    RADIUS_PANEL,
    RADIUS_SMALL,
    STATUS_BAR_HEIGHT,
    STATUS_ONE_SHOT,
    STATUS_RUNNING,
    STATUS_STOPPED,
    TEXT,
    TEXT_MUTED,
    btn_danger,
    btn_ghost,
    btn_outline_primary,
    btn_primary,
    ctk_font,
    seg_style,
)
from shared import (
    API_PORT,
    BASE_DIR,
    DASHBOARD_PORT,
)
from shared.process_utils import kill_process_tree
from tools.db_watcher import DBWatcher

# ==========================================================
# Process Cleanup on Exit
# ==========================================================
_active_processes: list[subprocess.Popen] = []
_process_lock = threading.Lock()


def _cleanup_all_processes() -> None:
    """Cleanup all managed subprocesses on program exit."""
    with _process_lock:
        for proc in _active_processes:
            try:
                if proc.poll() is None:
                    kill_process_tree(proc.pid)
            except (OSError, RuntimeError, subprocess.SubprocessError, ValueError):
                pass
        _active_processes.clear()


def _register_process(proc: subprocess.Popen) -> None:
    """Register a process for cleanup on exit."""
    with _process_lock:
        _active_processes.append(proc)


def _unregister_process(proc: subprocess.Popen) -> None:
    """Unregister a process from cleanup."""
    with _process_lock, contextlib.suppress(ValueError):
        _active_processes.remove(proc)


# Register cleanup on exit
atexit.register(_cleanup_all_processes)

# ==========================================================
# Configuration & Constants
# ==========================================================
PY = sys.executable
# 헤더 서비스 상태 뱃지 갱신 주기 (ms)
STATUS_REFRESH_MS = 1500

# CustomTkinter Settings — 라이트/다크/시스템 외형은 헤더 토글로 전환한다.
# 기본값은 시스템 외형을 따라가도록(사용자 OS 설정 존중). 색 상수는 manager_theme.
ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")


# ==========================================================
# System Tray Icon
# ==========================================================
def _create_tray_icon() -> Image.Image:
    """Create tray icon image."""
    # Create a simple icon (tool/gear symbol)
    size = 64
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Outer circle (dark blue)
    draw.ellipse([8, 8, size-8, size-8], fill='#1a237e', outline='#3949ab', width=2)

    # Inner circle (white)
    draw.ellipse([20, 20, size-20, size-20], fill='#ffffff')

    # Center dot
    draw.ellipse([26, 26, size-26, size-26], fill='#1a237e')

    return image


# ==========================================================
# Service Panel Configuration
# ==========================================================
@dataclass
class ServicePanelConfig:
    """Configuration for a service panel.

    버튼 색은 개별 지정하지 않는다 — Start는 항상 btn_primary, Stop은 btn_danger,
    extra_buttons는 (text, style_kwargs, command)로 manager_theme의 btn_*() 스타일을 받는다.
    """
    title: str
    start_command: Callable[[], None]
    stop_command: Callable[[], None]
    extra_buttons: list[tuple[str, dict, Callable[[], None]]]  # (text, style, command)


# ==========================================================
# Base Service Panel Class
# ==========================================================
class ServicePanel(ctk.CTkFrame):
    """
    Base class for service panels (Web, API, Portal).

    Provides:
    - Status bar indicator
    - Title and status label
    - Start/Stop controls
    - Log textbox with color tags + 편의 기능(레벨 필터/검색/복사/지우기/자동스크롤)

    로그는 전체 원본을 self._log_lines(list[(text, level)])에 보관하고,
    표시는 활성 필터/검색에 맞춰 UI 계층에서 재렌더한다.
    큐 기반 Tk 스레드 마샬링은 유지: 워커 → ui_log_queue → append_log(메인스레드).
    """

    def __init__(
        self,
        master,
        config: ServicePanelConfig,
        grid_args: dict,
        **kwargs
    ):
        super().__init__(master, corner_radius=RADIUS_PANEL, fg_color=BG_CARD, **kwargs)

        self.config = config
        self.process: subprocess.Popen | None = None

        # 로그 상태: 원본 줄 보관 + 표시 필터
        self._log_lines: list[tuple[str, str]] = []  # (text, level)
        self._level_filter: str = "ALL"  # ALL | INFO | WARN | ERROR | SUCCESS
        self._search_text: str = ""
        self._autoscroll: bool = True

        # Grid placement
        self.grid(**grid_args)
        self.grid_rowconfigure(5, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._init_status_bar()
        self._init_header()
        self._init_controls()
        self._init_log_toolbar()
        self._init_log_textbox()

    def _init_status_bar(self):
        """상단 상태 표시 바 (실행/중지 색)."""
        self.status_bar = ctk.CTkFrame(
            self, height=STATUS_BAR_HEIGHT, fg_color=STATUS_STOPPED, corner_radius=RADIUS_SMALL
        )
        self.status_bar.grid(row=0, column=0, sticky="ew", padx=2, pady=2)

    def _init_header(self):
        """패널 제목 + 상태 라벨 (통일 타이포)."""
        content_box = ctk.CTkFrame(self, fg_color="transparent")
        content_box.grid(row=1, column=0, sticky="nsew", padx=PAD_OUTER, pady=10)

        ctk.CTkLabel(
            content_box,
            text=self.config.title,
            text_color=TEXT,
            font=ctk_font(FONT_PANEL_TITLE),
        ).pack(anchor="w")

        self.lbl_status = ctk.CTkLabel(
            content_box,
            text="Stopped",
            text_color=TEXT_MUTED,
            font=ctk_font(FONT_STATUS),
        )
        self.lbl_status.pack(anchor="w", pady=(0, PAD_TIGHT))

    def _init_controls(self):
        """Start/Stop + extra 버튼."""
        ctrl_frame = ctk.CTkFrame(self, fg_color="transparent")
        ctrl_frame.grid(row=2, column=0, sticky="ew", padx=PAD_OUTER, pady=(0, 10))

        self.btn_start = ctk.CTkButton(
            ctrl_frame,
            text="Start",
            command=self.config.start_command,
            width=BUTTON_WIDTH,
            **btn_primary(),
        )
        self.btn_start.pack(side="left", padx=(0, GAP_CONTROL))

        self.btn_stop = ctk.CTkButton(
            ctrl_frame,
            text="Stop",
            command=self.config.stop_command,
            state="disabled",
            width=BUTTON_WIDTH,
            **btn_danger(),
        )
        self.btn_stop.pack(side="left", padx=GAP_CONTROL)

        # Extra buttons (subclass-specific)
        for text, style, command in self.config.extra_buttons:
            ctk.CTkButton(
                ctrl_frame,
                text=text,
                command=command,
                width=BUTTON_WIDTH,
                **style,
            ).pack(side="left", padx=GAP_CONTROL)

    def _init_log_toolbar(self):
        """로그 편의 툴바 2단: (레벨 필터 + 자동스크롤) / (검색 + 복사 + 지우기).

        좁은 패널 폭에서도 잘리지 않도록 두 줄로 나누고, 검색창이 남는 폭을
        흡수(fill/expand)한다.
        """
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=3, column=0, sticky="ew", padx=PAD_OUTER, pady=(0, 4))

        self.level_filter = ctk.CTkSegmentedButton(
            bar,
            values=["ALL", "INFO", "WARN", "ERROR"],
            command=self._on_level_change,
            width=20,
            height=26,
            **seg_style(),
        )
        self.level_filter.set("ALL")
        self.level_filter.pack(side="left", padx=(0, GAP_CONTROL))

        self.autoscroll_switch = ctk.CTkSwitch(
            bar, text="자동스크롤", command=self._on_autoscroll_toggle, width=56,
        )
        self.autoscroll_switch.select()  # 기본 켜짐
        self.autoscroll_switch.pack(side="right", padx=(GAP_CONTROL, 0))

        bar2 = ctk.CTkFrame(self, fg_color="transparent")
        bar2.grid(row=4, column=0, sticky="ew", padx=PAD_OUTER, pady=(0, 4))

        ctk.CTkButton(
            bar2, text="지우기", width=52, height=26,
            command=self._clear_log, **btn_ghost(),
        ).pack(side="right", padx=(GAP_CONTROL, 0))
        ctk.CTkButton(
            bar2, text="복사", width=46, height=26,
            command=self._copy_log, **btn_ghost(),
        ).pack(side="right", padx=(GAP_CONTROL, 0))

        self.search_var = ctk.StringVar(value="")
        self.search_var.trace_add("write", lambda *_: self._on_search_change())
        self.search_entry = ctk.CTkEntry(
            bar2, textvariable=self.search_var, placeholder_text="검색",
            height=26, width=120,
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, GAP_CONTROL))

    def _init_log_textbox(self):
        """로그 텍스트박스 + 색 태그."""
        self.log_textbox = ctk.CTkTextbox(
            self,
            font=FONT_LOG,
            text_color=LOG_INFO,
            fg_color=LOG_BG,
            border_width=1,
            border_color=LOG_BORDER,
            corner_radius=RADIUS_SMALL,
            activate_scrollbars=True,
        )
        self.log_textbox.grid(row=5, column=0, sticky="nsew", padx=PAD_OUTER, pady=(0, PAD_OUTER))
        self.log_textbox.configure(state="disabled")

        # 색 태그 — 로그박스는 어두운 배경 기준 고정색(manager_theme.LOG_*)
        self.log_textbox.tag_config("INFO", foreground=LOG_INFO)
        self.log_textbox.tag_config("WARN", foreground=LOG_WARN)
        self.log_textbox.tag_config("ERROR", foreground=LOG_ERROR)
        self.log_textbox.tag_config("SUCCESS", foreground=LOG_SUCCESS)

    # ── 로그 편의 로직 (UI 계층 필터링) ──
    def _matches_filter(self, level: str, text: str) -> bool:
        """활성 레벨 필터와 검색어에 줄이 매칭되는지."""
        level_ok = self._level_filter == "ALL" or level == self._level_filter
        search_ok = not self._search_text or self._search_text in text
        return level_ok and search_ok

    def _rerender_log(self):
        """현재 필터/검색 기준으로 로그 텍스트박스를 다시 그린다."""
        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", tk.END)
        for text, level in self._log_lines:
            if self._matches_filter(level, text):
                self.log_textbox.insert(tk.END, text + "\n", level)
        if self._autoscroll:
            self.log_textbox.see(tk.END)
        self.log_textbox.configure(state="disabled")

    def _on_level_change(self, value: str):
        self._level_filter = value
        self._rerender_log()

    def _on_search_change(self):
        self._search_text = self.search_var.get().strip()
        self._rerender_log()

    def _on_autoscroll_toggle(self):
        self._autoscroll = bool(self.autoscroll_switch.get())
        if self._autoscroll:
            self._rerender_log()  # 켤 때 즉시 맨 끝으로

    def _copy_log(self):
        """현재 표시된(필터된) 로그를 클립보드에 복사."""
        visible = [
            text for text, level in self._log_lines
            if self._matches_filter(level, text)
        ]
        self.clipboard_clear()
        self.clipboard_append("\n".join(visible))

    def _clear_log(self):
        """원본 로그 버퍼와 표시를 모두 비운다."""
        self._log_lines.clear()
        self._rerender_log()

    def set_running(self, status_text: str = "Running"):
        """Update UI to running state."""
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.lbl_status.configure(text=status_text, text_color=STATUS_RUNNING)
        self.status_bar.configure(fg_color=STATUS_RUNNING)

    def set_stopped(self):
        """Update UI to stopped state."""
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.lbl_status.configure(text="Stopped", text_color=STATUS_STOPPED)
        self.status_bar.configure(fg_color=STATUS_STOPPED)

    def append_log(self, text: str, level: str = "INFO"):
        """원본 로그를 버퍼에 추가하고 활성 필터에 맞춰 표시 갱신(메인 스레드 전용).

        큐 기반 마샬링 유지: 백그라운드 스레드는 ui_log_queue에 넣고,
        _process_ui_log_queue가 이 메서드를 메인 스레드에서 호출한다.
        """
        self._log_lines.append((text, level))
        # 매칭되는 줄만 텍스트박스에 추가(전체 재렌더 대신 증분 — 성능).
        if self._matches_filter(level, text):
            self.log_textbox.configure(state="normal")
            self.log_textbox.insert(tk.END, text + "\n", level)
            if self._autoscroll:
                self.log_textbox.see(tk.END)
            self.log_textbox.configure(state="disabled")


# ==========================================================
# Helpers
# ==========================================================
def _get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"

def _is_port_in_use(port: int):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0

# ==========================================================
# Manager UI (v3.0 - Portal Integration)
# ==========================================================
class ServerManager(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Window Setup
        self.title("Production Data Hub Manager")
        self.geometry("1400x800")
        self.local_ip = _get_local_ip()

        # State
        self.log_queue = queue.Queue()
        # (panel, text, level) from subprocess reader threads — Tk 위젯은
        # 메인 스레드 전용이라 워커에서 append_log를 직접 부르면 안 된다.
        self.ui_log_queue: queue.Queue = queue.Queue()
        self.watcher = None

        # --- Layout (3-column: Services | Services | Automation) ---
        self.grid_columnconfigure(0, weight=2)  # Dashboard
        self.grid_columnconfigure(1, weight=2)  # API
        self.grid_columnconfigure(2, weight=1)  # Portal + DB Auto
        self.grid_rowconfigure(0, weight=0)     # Header
        self.grid_rowconfigure(1, weight=1)     # Row 1
        self.grid_rowconfigure(2, weight=1)     # Row 2

        # --- Sections ---
        self._init_header()
        self._init_web_panel()
        self._init_api_panel()
        self._init_portal_panel()
        self._init_db_panel()

        # Start Queue Listeners
        self.after(100, self._process_log_queue)
        self.after(100, self._process_ui_log_queue)

        # Auto-start Watcher
        self.toggle_watcher()

        # 주기적 서비스 상태 뱃지 갱신
        self.after(STATUS_REFRESH_MS, self._refresh_status)

        # Safety on close
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # Setup system tray
        self._setup_tray()

        # Console Ctrl+C -> schedule cleanup on main Tk thread.
        # signal.signal works only on the main thread and only when a console
        # is attached (direct `python manager.py`). VBS background launch has
        # no console -> handler registration fails silently (expected).
        with contextlib.suppress(ValueError, OSError):
            signal.signal(signal.SIGINT, self._on_sigint)

    def _init_header(self):
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, columnspan=3, sticky="ew", padx=PAD_OUTER, pady=(20, 10))

        # ── 왼쪽: 타이틀 + 서비스 상태 뱃지 ──
        left = ctk.CTkFrame(header_frame, fg_color="transparent")
        left.pack(side="left", anchor="w")

        ctk.CTkLabel(
            left,
            text="Production Data Hub",
            text_color=TEXT,
            font=ctk_font(FONT_TITLE),
        ).pack(anchor="w")

        # 서비스 상태 요약 뱃지 행 (웹/API/포털/DB 워처) — 주기 갱신(_refresh_status)
        self.status_badges: dict[str, ctk.CTkLabel] = {}
        badge_row = ctk.CTkFrame(left, fg_color="transparent")
        badge_row.pack(anchor="w", pady=(4, 0))
        self._build_status_badges(badge_row)

        # ── 오른쪽: IP 뱃지 + 전체 시작/중지 + 외형 토글 ──
        right = ctk.CTkFrame(header_frame, fg_color="transparent")
        right.pack(side="right", anchor="e")

        self.appearance_mode = ctk.CTkSegmentedButton(
            right, values=["Light", "Dark", "System"],
            command=self._set_appearance, width=20, height=28,
            **seg_style(),
        )
        self.appearance_mode.set("System")
        self.appearance_mode.pack(side="right", padx=(GAP_CONTROL, 0))

        ctk.CTkButton(
            right, text="전체 중지", width=84, height=28,
            command=self.stop_all, **btn_danger(),
        ).pack(side="right", padx=(GAP_CONTROL, 0))
        ctk.CTkButton(
            right, text="전체 시작", width=84, height=28,
            command=self.start_all, **btn_primary(),
        ).pack(side="right", padx=(GAP_CONTROL, 0))

        ip_badge = ctk.CTkButton(
            right, text=f"Host: {self.local_ip}",
            font=ctk_font(FONT_BADGE),
            fg_color=BG_INNER, hover=False, height=28, corner_radius=RADIUS_BADGE,
            text_color_disabled=TEXT_MUTED, state="disabled",
        )
        ip_badge.pack(side="right", padx=(0, GAP_CONTROL))

    def _build_status_badges(self, parent):
        """서비스 상태 뱃지(웹/API/포털/DB 워처) 생성 — 주기 갱신 대상."""
        self._badge_specs = [
            (f"web:{DASHBOARD_PORT}", "웹"),
            (f"api:{API_PORT}", "API"),
            ("portal", "포털"),
            ("dbwatcher", "DB"),
        ]
        for key, label in self._badge_specs:
            ctk.CTkLabel(parent, text=label, font=ctk_font(FONT_BADGE),
                         text_color=TEXT_MUTED).pack(side="left", padx=(0, 4))
            badge = ctk.CTkLabel(
                parent, text="중지", width=52, height=22, corner_radius=11,
                font=ctk_font(FONT_BADGE),
                fg_color=PILL_STOPPED_BG, text_color=PILL_STOPPED_TEXT,
            )
            badge.pack(side="left", padx=(0, 12))
            self.status_badges[key] = badge

    def _set_appearance(self, mode: str):
        """헤더 외형 토글: Light/Dark/System → ctk.set_appearance_mode."""
        ctk.set_appearance_mode(mode.lower())

    def start_all(self):
        """웹 + API 일괄 시작 (확인 다이얼로그 없이 즉시)."""
        self.start_web()
        self.start_api()

    def stop_all(self):
        """웹 + API 일괄 중지 (확인 다이얼로그 없이 즉시)."""
        self.stop_web()
        self.stop_api()

    def _is_panel_running(self, panel) -> bool:
        return bool(panel.process and panel.process.poll() is None)

    def _refresh_status(self):
        """헤더 서비스 상태 뱃지를 현재 실행 상태로 갱신 (주기 호출)."""
        specs = [
            (f"web:{DASHBOARD_PORT}", self._is_panel_running(self.web_panel)),
            (f"api:{API_PORT}", self._is_panel_running(self.api_panel)),
            ("portal", self._is_panel_running(self.portal_panel)),
            ("dbwatcher", bool(self.watcher and self.watcher.is_alive())),
        ]
        for key, running in specs:
            badge = self.status_badges.get(key)
            if badge is None:
                continue
            badge.configure(
                text="실행중" if running else "중지",
                fg_color=PILL_RUNNING_BG if running else PILL_STOPPED_BG,
                text_color=PILL_RUNNING_TEXT if running else PILL_STOPPED_TEXT,
            )
        self.after(STATUS_REFRESH_MS, self._refresh_status)

    def _init_web_panel(self):
        """Initialize Dashboard panel using ServicePanel base class."""
        config = ServicePanelConfig(
            title="Dashboard",
            start_command=self.start_web,
            stop_command=self.stop_web,
            extra_buttons=[
                ("Open", btn_ghost(), lambda: webbrowser.open(f"http://{self.local_ip}:{DASHBOARD_PORT}"))
            ]
        )
        self.web_panel = ServicePanel(
            self,
            config,
            grid_args={
                "row": 1, "column": 0, "rowspan": 2, "sticky": "nsew",
                "padx": (PAD_OUTER, 10), "pady": 10,
            }
        )

    def _init_api_panel(self):
        """Initialize API Gateway panel using ServicePanel base class."""
        config = ServicePanelConfig(
            title="API Gateway",
            start_command=self.start_api,
            stop_command=self.stop_api,
            extra_buttons=[
                ("Docs", btn_ghost(), lambda: webbrowser.open(f"http://{self.local_ip}:{API_PORT}/docs"))
            ]
        )
        self.api_panel = ServicePanel(
            self,
            config,
            grid_args={
                "row": 1, "column": 1, "rowspan": 2, "sticky": "nsew",
                "padx": 10, "pady": 10,
            }
        )

    def _init_portal_panel(self):
        """Initialize Portal Automation panel using ServicePanel base class."""
        config = ServicePanelConfig(
            title="Portal Automation",
            start_command=self.start_portal,
            stop_command=self.stop_portal,
            extra_buttons=[
                ("Run Now", btn_outline_primary(), self.run_portal_now),
                ("Settings", btn_ghost(), self.open_portal_settings)
            ]
        )
        self.portal_panel = ServicePanel(
            self,
            config,
            grid_args={
                "row": 1, "column": 2, "sticky": "nsew",
                "padx": (10, PAD_OUTER), "pady": (10, 5),
            }
        )

    def _init_db_panel(self):
        """Initialize DB Automation panel (compact layout for 3rd column)."""
        self.db_frame = ctk.CTkFrame(self, corner_radius=RADIUS_PANEL, fg_color=BG_CARD)
        self.db_frame.grid(row=2, column=2, sticky="nsew", padx=(10, PAD_OUTER), pady=(5, 10))
        self.db_frame.grid_rowconfigure(1, weight=1)
        self.db_frame.grid_columnconfigure(0, weight=1)

        # Status Bar
        self.db_status_bar = ctk.CTkFrame(
            self.db_frame, height=STATUS_BAR_HEIGHT,
            fg_color=STATUS_RUNNING, corner_radius=RADIUS_SMALL,
        )
        self.db_status_bar.grid(row=0, column=0, sticky="ew", padx=2, pady=2)

        # Header
        header_frame = ctk.CTkFrame(self.db_frame, fg_color="transparent")
        header_frame.grid(row=1, column=0, sticky="ew", padx=PAD_PANEL, pady=10)

        ctk.CTkLabel(header_frame, text="DB Automation", text_color=TEXT,
                     font=ctk_font(FONT_PANEL_TITLE_COMPACT)).pack(side="left")

        self.lbl_watcher_status = ctk.CTkLabel(header_frame, text="Active (1h)",
                                                text_color=STATUS_RUNNING,
                                                font=ctk.CTkFont(size=11))
        self.lbl_watcher_status.pack(side="right")

        # Compact Log Area
        self.log_db = ctk.CTkTextbox(self.db_frame, height=100, font=FONT_LOG_COMPACT,
                                      text_color=LOG_INFO, fg_color=LOG_BG,
                                      border_width=1, border_color=LOG_BORDER,
                                      corner_radius=RADIUS_SMALL,
                                      activate_scrollbars=True)
        self.log_db.grid(row=2, column=0, sticky="nsew", padx=PAD_PANEL, pady=(0, PAD_PANEL))
        self.log_db.configure(state="disabled")

        self.log_db.tag_config("INFO", foreground=LOG_INFO)
        self.log_db.tag_config("WARN", foreground=LOG_WARN)
        self.log_db.tag_config("ERROR", foreground=LOG_ERROR)
        self.log_db.tag_config("SUCCESS", foreground=LOG_SUCCESS)

        self._append_db_log(">>> DB Watcher Initialized.", "INFO")

    # --------------------------
    # Logging with Colors
    # --------------------------
    def _process_log_queue(self):
        while not self.log_queue.empty():
            try:
                level, msg = self.log_queue.get_nowait()
                timestamp = time.strftime("%H:%M:%S")
                log_msg = f"[{timestamp}] {msg}"
                self._append_db_log(log_msg, level)
            except queue.Empty:
                break
        self.after(200, self._process_log_queue)

    def _process_ui_log_queue(self):
        """Drain subprocess log lines on the MAIN thread (Tk-safe)."""
        while True:
            try:
                panel, text, level = self.ui_log_queue.get_nowait()
            except queue.Empty:
                break
            # Widget may be destroyed while lines are still queued
            with contextlib.suppress(
                AttributeError, RuntimeError, tk.TclError, ValueError
            ):
                panel.append_log(text, level)
        self.after(150, self._process_ui_log_queue)

    def _append_db_log(self, text: str, level: str = "INFO"):
        """Append log to DB panel log textbox."""
        self.log_db.configure(state="normal")
        self.log_db.insert(tk.END, text + "\n", level)
        self.log_db.see(tk.END)
        self.log_db.configure(state="disabled")

    # --------------------------
    # Logic
    # --------------------------
    def toggle_watcher(self):
        """Start DB watcher (always active, no toggle needed)."""
        if not self.watcher or not self.watcher.is_alive():
            self.watcher = DBWatcher(self.log_queue)
            self.watcher.start()
            self.lbl_watcher_status.configure(text="Active (1h)", text_color=STATUS_RUNNING)
            self.db_status_bar.configure(fg_color=STATUS_RUNNING)

    def _stream_output(self, proc: subprocess.Popen, panel: ServicePanel) -> None:
        """Stream subprocess output into ui_log_queue.

        Runs on a reader thread — it must NOT touch Tk widgets directly
        (Tkinter is main-thread-only; direct insert corrupted the Tcl
        interpreter under load). _process_ui_log_queue renders the lines.
        """
        try:
            while proc.poll() is None:
                try:
                    line = proc.stdout.readline()
                    if not line:
                        break
                    text = line.rstrip()
                    if not text:
                        continue
                    level = "INFO"
                    if "ERROR" in text.upper() or "EXCEPTION" in text.upper():
                        level = "ERROR"
                    elif "WARNING" in text.upper():
                        level = "WARN"
                    elif "SUCCESS" in text.upper() or "COMPLETE" in text.upper():
                        level = "SUCCESS"

                    self.ui_log_queue.put((panel, text, level))
                except (AttributeError, OSError, RuntimeError, ValueError):
                    break
        except (AttributeError, OSError, RuntimeError, ValueError):
            pass
        finally:
            self.ui_log_queue.put((panel, ">>> Process Exited", "WARN"))

    def _start_process(
        self, cmd: list[str], panel: ServicePanel, cwd: str | None = None
    ) -> subprocess.Popen:
        """Start subprocess and stream output to panel."""
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"

        proc = subprocess.Popen(
            cmd, cwd=cwd or str(BASE_DIR),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, encoding='utf-8', errors='replace',
            env=env
        )
        _register_process(proc)
        threading.Thread(target=self._stream_output, args=(proc, panel), daemon=True).start()
        return proc

    def start_web(self):
        if self.web_panel.process and self.web_panel.process.poll() is None:
            return
        if _is_port_in_use(DASHBOARD_PORT):
            messagebox.showerror("Error", f"Port {DASHBOARD_PORT} is in use.")
            return

        self.web_panel.set_running(f"Running ({DASHBOARD_PORT})")
        self.web_panel.append_log(">>> Starting Dashboard...", "INFO")

        cmd = [
            PY, "-m", "streamlit", "run", str(BASE_DIR / "dashboard" / "app.py"),
            "--server.address", "0.0.0.0", "--server.port", str(DASHBOARD_PORT),
            "--server.headless", "true",
        ]
        self.web_panel.process = self._start_process(cmd, self.web_panel)

    def stop_web(self):
        if self.web_panel.process:
            _unregister_process(self.web_panel.process)
            kill_process_tree(self.web_panel.process.pid)
        self.web_panel.process = None
        self.web_panel.set_stopped()
        self.web_panel.append_log(">>> Stopped.", "WARN")

    def start_api(self):
        if self.api_panel.process and self.api_panel.process.poll() is None:
            return
        if _is_port_in_use(API_PORT):
            messagebox.showerror("Error", f"Port {API_PORT} is in use.")
            return

        self.api_panel.set_running(f"Running ({API_PORT})")
        self.api_panel.append_log(">>> Starting API Server...", "INFO")

        cmd = [PY, "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", str(API_PORT)]
        self.api_panel.process = self._start_process(cmd, self.api_panel)

    def stop_api(self):
        if self.api_panel.process:
            _unregister_process(self.api_panel.process)
            kill_process_tree(self.api_panel.process.pid)
        self.api_panel.process = None
        self.api_panel.set_stopped()
        self.api_panel.append_log(">>> Stopped.", "WARN")

    def start_portal(self):
        if self.portal_panel.process and self.portal_panel.process.poll() is None:
            return

        self.portal_panel.set_running("Scheduled")
        self.portal_panel.append_log(">>> Starting Portal Scheduler...", "INFO")

        portal_dir = str(BASE_DIR / "webcloring-pdf")
        cmd = [PY, "main.py", "--schedule"]
        self.portal_panel.process = self._start_process(cmd, self.portal_panel, cwd=portal_dir)

    def stop_portal(self):
        if self.portal_panel.process:
            _unregister_process(self.portal_panel.process)
            kill_process_tree(self.portal_panel.process.pid)
        self.portal_panel.process = None
        self.portal_panel.set_stopped()
        self.portal_panel.append_log(">>> Stopped.", "WARN")

    def open_portal_settings(self):
        """Open portal settings dialog."""
        env_path = BASE_DIR / "webcloring-pdf" / ".env"
        dialog = PortalSettingsDialog(self, env_path)
        self.wait_window(dialog)
        if dialog.result:
            self.portal_panel.append_log("⚙️ Settings saved.", "SUCCESS")

    def _keywords_from_config(self) -> list[str] | None:
        """config.json(search.jobs)에서 키워드 목록. jobs 없으면 구 profiles 폴백.

        파일이 없거나 파싱 실패 시 None (호출자가 다음 폴백으로 진행).
        """
        cfg_path = BASE_DIR / "webcloring-pdf" / "src" / "config" / "config.json"
        if not cfg_path.exists():
            return None
        try:
            with open(cfg_path, encoding="utf-8") as f:
                sec = (json.load(f).get("search", {}) or {})
        except (OSError, json.JSONDecodeError):
            return None

        jobs = sec.get("jobs")
        if jobs:
            ks = [str(j.get("keyword", "")).strip()
                  for j in jobs if isinstance(j, dict)]
            ks = [k for k in ks if k]
            if ks:
                return ks
        seen: list[str] = []
        for p in (sec.get("profiles") or []):
            if isinstance(p, dict):
                k = str(p.get("keyword", "")).strip()
                if k and k not in seen:
                    seen.append(k)
        return seen or None

    def _keyword_from_env(self) -> str | None:
        """폴백: .env SEARCH_KEYWORD 값을 읽는다. 없으면 None."""
        env_path = BASE_DIR / "webcloring-pdf" / ".env"
        if not env_path.exists():
            return None
        try:
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("SEARCH_KEYWORD") and "=" in line:
                        v = line.split("=", 1)[1].strip()
                        if v:
                            return v
        except OSError:
            pass
        return None

    def _portal_job_keywords(self) -> list[str]:
        """봇 config.json(search.jobs)의 키워드 목록. 폴백: 구 profiles → .env SEARCH_KEYWORD."""
        cfg_keywords = self._keywords_from_config()
        if cfg_keywords:
            return cfg_keywords
        env_keyword = self._keyword_from_env()
        if env_keyword:
            return [env_keyword]
        return ["자재"]

    def run_portal_now(self):
        """Run portal automation once. 작업이 여럿이면 키워드를 고르게 한다."""
        if self.portal_panel.process and self.portal_panel.process.poll() is None:
            self.portal_panel.append_log("⚠️ Already running.", "WARN")
            return
        keywords = self._portal_job_keywords()
        if len(keywords) <= 1:
            self._launch_portal_auto(keywords[0] if keywords else None)
        else:
            self._pick_keyword_dialog(keywords)

    def _pick_keyword_dialog(self, keywords: list[str]):
        """수동 1회 실행할 키워드 선택 모달."""
        win = ctk.CTkToplevel(self)
        win.title("수동 실행 — 키워드 선택")
        win.geometry(f"320x{90 + len(keywords) * 44 + 60}")
        win.resizable(False, False)
        win.transient(self)
        win.grab_set()
        ctk.CTkLabel(
            win, text="어느 키워드를 1회 실행할까요?",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(pady=(16, 12))

        def choose(kw):
            win.destroy()
            self._launch_portal_auto(kw)

        for k in keywords:
            ctk.CTkButton(win, text=k, width=260, **btn_primary(),
                          command=lambda kw=k: choose(kw)).pack(pady=4)
        ctk.CTkButton(win, text="취소", width=260, **btn_ghost(),
                      command=win.destroy).pack(pady=(10, 14))

    def _launch_portal_auto(self, keyword: str | None = None):
        """`main.py --auto [--keyword K]` 1회 실행 (non-blocking)."""
        if self.portal_panel.process and self.portal_panel.process.poll() is None:
            self.portal_panel.append_log("⚠️ Already running.", "WARN")
            return

        label = keyword or "기본"
        self.portal_panel.btn_start.configure(state="disabled")
        self.portal_panel.btn_stop.configure(state="normal")
        self.portal_panel.lbl_status.configure(
            text=f"Running 1-shot ({label})", text_color=STATUS_ONE_SHOT)
        self.portal_panel.status_bar.configure(fg_color=STATUS_ONE_SHOT)
        self.portal_panel.append_log(
            f">>> Running Portal Automation (1-shot, 키워드={label})...", "INFO")

        portal_dir = str(BASE_DIR / "webcloring-pdf")
        cmd = [PY, "main.py", "--auto"]
        if keyword:
            cmd += ["--keyword", keyword]
        self.portal_panel.process = self._start_process(cmd, self.portal_panel, cwd=portal_dir)

        # Monitor for completion and reset UI (thread-safe via self.after)
        def _monitor():
            if self.portal_panel.process:
                self.portal_panel.process.wait()
            # Widget may be destroyed
            with contextlib.suppress(RuntimeError, tk.TclError):
                self.after(0, self._reset_portal_ui)
        threading.Thread(target=_monitor, daemon=True).start()

    def _reset_portal_ui(self):
        """Reset portal panel to stopped state (main thread only)."""
        self.portal_panel.set_stopped()

    # --------------------------
    # System Tray
    # --------------------------
    def _setup_tray(self) -> None:
        """Setup system tray icon (best-effort).

        If tray backend is unavailable, `self.tray_icon` stays None and
        `on_close` falls back to a confirmation dialog so the user can still
        exit cleanly instead of getting stuck with a hidden window.
        """
        self.tray_icon = None
        try:
            icon_image = _create_tray_icon()
            menu = pystray.Menu(
                pystray.MenuItem("창 보이기", self._show_window, default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("완전 종료", self._quit_app),
            )
            self.tray_icon = pystray.Icon(
                "production_hub", icon_image, "Production Hub", menu
            )
        except (AttributeError, OSError, RuntimeError, ValueError) as e:
            # Printed so it shows up in console for the dev; UI keeps working.
            print(f"[Manager] Tray init failed: {e}", flush=True)

    def _show_window(self, icon=None, item=None) -> None:
        """Show window from tray."""
        self.after(0, self._restore_window)

    def _restore_window(self) -> None:
        """Restore window (called from tray thread)."""
        self.deiconify()
        self.lift()
        self.focus_force()

    def _hide_to_tray(self) -> None:
        """Hide window to system tray."""
        self.withdraw()
        if self.tray_icon and not self.tray_icon.visible:
            # Run tray icon in separate thread
            threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _quit_app(self, icon=None, item=None) -> None:
        """Completely quit the application."""
        if self.tray_icon:
            self.tray_icon.stop()
        self.after(0, self._cleanup_and_exit)

    def _cleanup_and_exit(self) -> None:
        """Cleanup and exit (called from tray thread)."""
        if self.watcher:
            self.watcher.stop()
        self.stop_web()
        self.stop_api()
        self.stop_portal()
        self.destroy()
        sys.exit(0)

    def on_close(self) -> None:
        """Handle window close button.

        - Tray available: hide to tray (original design — user sees tray icon).
        - Tray unavailable: prompt to confirm full exit so the user is not
          stuck with a hidden window and no way to bring it back.
        """
        if self.tray_icon is not None:
            self._hide_to_tray()
            return

        if messagebox.askyesno(
            "종료 확인",
            "트레이 아이콘을 사용할 수 없습니다.\n"
            "서버를 모두 종료하고 매니저를 닫으시겠습니까?"
        ):
            self._cleanup_and_exit()

    def _on_sigint(self, signum, frame) -> None:
        """Console Ctrl+C handler — schedule graceful exit on main Tk thread."""
        self.after(0, self._cleanup_and_exit)


if __name__ == "__main__":
    app = ServerManager()
    app.mainloop()
