import os
import sys
import atexit
import threading
import subprocess
import socket
import webbrowser
import time
import queue
from abc import ABC, abstractmethod
from pathlib import Path
from dataclasses import dataclass
from typing import Callable, Optional
import tkinter as tk
import tkinter.messagebox as messagebox
import customtkinter as ctk
import pystray
from PIL import Image, ImageDraw

from portal_settings_dialog import PortalSettingsDialog

# Add current directory to path for shared module import
sys.path.insert(0, str(Path(__file__).resolve().parent))

from shared import (
    BASE_DIR,
    DB_FILE,
    ARCHIVE_DB_FILE,
    DASHBOARD_PORT,
    API_PORT,
    DB_TIMEOUT,
)
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
                    _taskkill_tree(proc.pid)
            except Exception:
                pass
        _active_processes.clear()


def _register_process(proc: subprocess.Popen) -> None:
    """Register a process for cleanup on exit."""
    with _process_lock:
        _active_processes.append(proc)


def _unregister_process(proc: subprocess.Popen) -> None:
    """Unregister a process from cleanup."""
    with _process_lock:
        try:
            _active_processes.remove(proc)
        except ValueError:
            pass


# Register cleanup on exit
atexit.register(_cleanup_all_processes)

# ==========================================================
# Configuration & Constants
# ==========================================================
PY = sys.executable

# CustomTkinter Settings
ctk.set_appearance_mode("Dark") # Force Dark mode for better contrast
ctk.set_default_color_theme("blue")

# Colors
COLOR_SUCCESS = "#4caf50" # Green
COLOR_ERROR = "#ef5350"   # Red
COLOR_WARN = "#ffb74d"    # Orange
COLOR_INFO = "#e0e0e0"    # Light Gray
COLOR_MUTED = "#757575"   # Dark Gray
COLOR_BG_CARD = "#2b2b2b" # Card Background


# ==========================================================
# System Tray Icon
# ==========================================================
def _create_tray_icon() -> Image.Image:
    """Create tray icon image."""
    # Create a simple icon (tool/gear symbol)
    size = 64
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Draw a simple gear-like circle
    center = size // 2
    radius = size // 2 - 4

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
    """Configuration for a service panel."""
    title: str
    start_color: str
    start_command: Callable[[], None]
    stop_command: Callable[[], None]
    extra_buttons: list[tuple[str, str, Callable[[], None]]]  # (text, color, command)


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
    - Log textbox with color tags
    """

    def __init__(
        self,
        master,
        config: ServicePanelConfig,
        grid_args: dict,
        **kwargs
    ):
        super().__init__(master, corner_radius=15, fg_color=COLOR_BG_CARD, **kwargs)

        self.config = config
        self.process: Optional[subprocess.Popen] = None

        # Grid placement
        self.grid(**grid_args)
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._init_ui()

    def _init_ui(self):
        """Initialize panel UI components."""
        # Status Bar (Visual Indicator)
        self.status_bar = ctk.CTkFrame(self, height=4, fg_color=COLOR_MUTED, corner_radius=2)
        self.status_bar.grid(row=0, column=0, sticky="ew", padx=2, pady=2)

        # Content
        content_box = ctk.CTkFrame(self, fg_color="transparent")
        content_box.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)

        ctk.CTkLabel(
            content_box,
            text=self.config.title,
            text_color="#ffffff",
            font=ctk.CTkFont(size=18, weight="bold")
        ).pack(anchor="w")

        self.lbl_status = ctk.CTkLabel(
            content_box,
            text="Stopped",
            text_color=COLOR_MUTED,
            font=ctk.CTkFont(size=14)
        )
        self.lbl_status.pack(anchor="w", pady=(0, 10))

        # Controls
        ctrl_frame = ctk.CTkFrame(self, fg_color="transparent")
        ctrl_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 10))

        self.btn_start = ctk.CTkButton(
            ctrl_frame,
            text="▶ Start",
            command=self.config.start_command,
            fg_color=self.config.start_color,
            width=80
        )
        self.btn_start.pack(side="left", padx=(0, 5))

        self.btn_stop = ctk.CTkButton(
            ctrl_frame,
            text="■ Stop",
            command=self.config.stop_command,
            fg_color="#c62828",
            state="disabled",
            width=80
        )
        self.btn_stop.pack(side="left", padx=5)

        # Extra buttons (subclass-specific)
        for text, color, command in self.config.extra_buttons:
            ctk.CTkButton(
                ctrl_frame,
                text=text,
                command=command,
                fg_color=color,
                width=80
            ).pack(side="left", padx=5)

        # Log Textbox
        self.log_textbox = ctk.CTkTextbox(
            self,
            font=("Consolas", 12),
            text_color="#eeeeee",
            activate_scrollbars=True
        )
        self.log_textbox.grid(row=3, column=0, sticky="nsew", padx=20, pady=20)
        self.log_textbox.configure(state="disabled")

        # Color tags
        self.log_textbox.tag_config("INFO", foreground=COLOR_INFO)
        self.log_textbox.tag_config("WARN", foreground=COLOR_WARN)
        self.log_textbox.tag_config("ERROR", foreground=COLOR_ERROR)
        self.log_textbox.tag_config("SUCCESS", foreground=COLOR_SUCCESS)

    def set_running(self, status_text: str = "Running"):
        """Update UI to running state."""
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.lbl_status.configure(text=status_text, text_color=COLOR_SUCCESS)
        self.status_bar.configure(fg_color=COLOR_SUCCESS)

    def set_stopped(self):
        """Update UI to stopped state."""
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.lbl_status.configure(text="Stopped", text_color=COLOR_MUTED)
        self.status_bar.configure(fg_color=COLOR_MUTED)

    def append_log(self, text: str, level: str = "INFO"):
        """Append log message with color."""
        self.log_textbox.configure(state="normal")
        self.log_textbox.insert(tk.END, text + "\n", level)
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
    except Exception:
        return "127.0.0.1"

def _is_port_in_use(port: int):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("localhost", port)) == 0

def _taskkill_tree(pid: int):
    try:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], 
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    except Exception:
        pass


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

        # Start Queue Listener
        self.after(100, self._process_log_queue)
        
        # Auto-start Watcher
        self.toggle_watcher()

        # Safety on close
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # Setup system tray
        self._setup_tray()

    def _init_header(self):
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, columnspan=3, sticky="ew", padx=20, pady=(20, 10))

        title_label = ctk.CTkLabel(
            header_frame,
            text="Production Data Hub",
            text_color="#ffffff",
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold")
        )
        title_label.pack(side="left")

        # Status indicators
        status_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        status_frame.pack(side="right")

        ip_badge = ctk.CTkButton(
            status_frame, text=f"Host: {self.local_ip}",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#424242", hover=False, height=28, corner_radius=14,
            text_color_disabled="#E0E0E0", state="disabled"
        )
        ip_badge.pack(side="right")

    def _init_web_panel(self):
        """Initialize Dashboard panel using ServicePanel base class."""
        config = ServicePanelConfig(
            title="📊 Dashboard",
            start_color="#1f6aa5",
            start_command=self.start_web,
            stop_command=self.stop_web,
            extra_buttons=[
                ("🔗 Open", "#424242", lambda: webbrowser.open(f"http://{self.local_ip}:{DASHBOARD_PORT}"))
            ]
        )
        self.web_panel = ServicePanel(
            self,
            config,
            grid_args={"row": 1, "column": 0, "rowspan": 2, "sticky": "nsew", "padx": (20, 10), "pady": 10}
        )

    def _init_api_panel(self):
        """Initialize API Gateway panel using ServicePanel base class."""
        config = ServicePanelConfig(
            title="⚡ API Gateway",
            start_color="#2e7d32",
            start_command=self.start_api,
            stop_command=self.stop_api,
            extra_buttons=[
                ("🔗 Docs", "#424242", lambda: webbrowser.open(f"http://{self.local_ip}:{API_PORT}/docs"))
            ]
        )
        self.api_panel = ServicePanel(
            self,
            config,
            grid_args={"row": 1, "column": 1, "rowspan": 2, "sticky": "nsew", "padx": 10, "pady": 10}
        )

    def _init_portal_panel(self):
        """Initialize Portal Automation panel using ServicePanel base class."""
        config = ServicePanelConfig(
            title="🤖 Portal Automation",
            start_color="#6a1b9a",
            start_command=self.start_portal,
            stop_command=self.stop_portal,
            extra_buttons=[
                ("🚀 Run Now", "#e65100", self.run_portal_now),
                ("⚙️ Settings", "#37474f", self.open_portal_settings)
            ]
        )
        self.portal_panel = ServicePanel(
            self,
            config,
            grid_args={"row": 1, "column": 2, "sticky": "nsew", "padx": (10, 20), "pady": (10, 5)}
        )

    def _init_db_panel(self):
        """Initialize DB Automation panel (compact layout for 3rd column)."""
        self.db_frame = ctk.CTkFrame(self, corner_radius=15, fg_color=COLOR_BG_CARD)
        self.db_frame.grid(row=2, column=2, sticky="nsew", padx=(10, 20), pady=(5, 10))
        self.db_frame.grid_rowconfigure(1, weight=1)
        self.db_frame.grid_columnconfigure(0, weight=1)

        # Status Bar
        self.db_status_bar = ctk.CTkFrame(self.db_frame, height=4, fg_color=COLOR_SUCCESS, corner_radius=2)
        self.db_status_bar.grid(row=0, column=0, sticky="ew", padx=2, pady=2)

        # Header
        header_frame = ctk.CTkFrame(self.db_frame, fg_color="transparent")
        header_frame.grid(row=1, column=0, sticky="ew", padx=15, pady=10)

        ctk.CTkLabel(header_frame, text="🔧 DB Automation", text_color="#ffffff",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(side="left")

        self.lbl_watcher_status = ctk.CTkLabel(header_frame, text="Active (1h)",
                                                text_color=COLOR_SUCCESS, font=ctk.CTkFont(size=11))
        self.lbl_watcher_status.pack(side="right")

        # Compact Log Area
        self.log_db = ctk.CTkTextbox(self.db_frame, height=100, font=("Consolas", 10),
                                      text_color="#eeeeee", activate_scrollbars=True)
        self.log_db.grid(row=2, column=0, sticky="nsew", padx=15, pady=(0, 15))
        self.log_db.configure(state="disabled")

        self.log_db.tag_config("INFO", foreground=COLOR_INFO)
        self.log_db.tag_config("WARN", foreground=COLOR_WARN)
        self.log_db.tag_config("ERROR", foreground=COLOR_ERROR)
        self.log_db.tag_config("SUCCESS", foreground=COLOR_SUCCESS)

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
            self.lbl_watcher_status.configure(text="Active (1h)", text_color=COLOR_SUCCESS)
            self.db_status_bar.configure(fg_color=COLOR_SUCCESS)

    def manual_db_check(self):
        """Trigger manual DB check (auto-start watcher if not running)."""
        if not self.watcher or not self.watcher.is_alive():
            self.toggle_watcher()
        if self.watcher:
            self.log_queue.put(("INFO", "🛠️ Manual Check Triggered..."))
            self.watcher.manual_trigger()
        else:
            self.log_queue.put(("WARN", "Watcher is paused."))

    def _stream_output(self, proc: subprocess.Popen, panel: ServicePanel) -> None:
        """Stream subprocess output to panel log with timeout protection."""
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

                    panel.append_log(text, level)
                except Exception:
                    break
        except Exception:
            pass
        finally:
            try:
                panel.append_log(">>> Process Exited", "WARN")
            except Exception:
                pass  # Widget may be destroyed

    def _start_process(self, cmd: list[str], panel: ServicePanel, cwd: str | None = None) -> subprocess.Popen:
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

        cmd = [PY, "-m", "streamlit", "run", str(BASE_DIR / "dashboard" / "app.py"), "--server.address", "0.0.0.0", "--server.port", str(DASHBOARD_PORT), "--server.headless", "true"]
        self.web_panel.process = self._start_process(cmd, self.web_panel)

    def stop_web(self):
        if self.web_panel.process:
            _unregister_process(self.web_panel.process)
            _taskkill_tree(self.web_panel.process.pid)
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
            _taskkill_tree(self.api_panel.process.pid)
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
            _taskkill_tree(self.portal_panel.process.pid)
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

    def run_portal_now(self):
        """Run portal automation once (non-blocking)."""
        if self.portal_panel.process and self.portal_panel.process.poll() is None:
            self.portal_panel.append_log("⚠️ Already running.", "WARN")
            return

        # Custom status for one-shot mode
        self.portal_panel.btn_start.configure(state="disabled")
        self.portal_panel.btn_stop.configure(state="normal")
        self.portal_panel.lbl_status.configure(text="Running (1-shot)", text_color="#ffb74d")
        self.portal_panel.status_bar.configure(fg_color="#ffb74d")
        self.portal_panel.append_log(">>> Running Portal Automation (1-shot)...", "INFO")

        portal_dir = str(BASE_DIR / "webcloring-pdf")
        cmd = [PY, "main.py", "--auto"]
        self.portal_panel.process = self._start_process(cmd, self.portal_panel, cwd=portal_dir)

        # Monitor for completion and reset UI (thread-safe via self.after)
        def _monitor():
            if self.portal_panel.process:
                self.portal_panel.process.wait()
            try:
                self.after(0, self._reset_portal_ui)
            except Exception:
                pass  # Widget may be destroyed
        threading.Thread(target=_monitor, daemon=True).start()

    def _reset_portal_ui(self):
        """Reset portal panel to stopped state (main thread only)."""
        self.portal_panel.set_stopped()

    # --------------------------
    # System Tray
    # --------------------------
    def _setup_tray(self) -> None:
        """Setup system tray icon."""
        icon_image = _create_tray_icon()

        menu = pystray.Menu(
            pystray.MenuItem("창 보이기", self._show_window, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("완전 종료", self._quit_app),
        )

        self.tray_icon = pystray.Icon("production_hub", icon_image, "Production Hub", menu)

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
        """Handle window close button - hide to tray instead of quitting."""
        self._hide_to_tray()


if __name__ == "__main__":
    app = ServerManager()
    app.mainloop()