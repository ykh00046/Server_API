# portal_settings_dialog.py
"""
Portal Automation Settings Dialog

CustomTkinter dialog for editing webcloring-pdf/.env settings
directly from the ServerManager. No dependency on webcloring-pdf code.

Security Note:
  Passwords are obfuscated (not encrypted) before storage.
  For production use, consider using the 'keyring' library for proper encryption.
"""

import base64
import binascii
import customtkinter as ctk
from pathlib import Path
from tkinter import messagebox


# ==========================================================
# Simple Password Obfuscation (NOT encryption)
# ==========================================================
# For production: Use 'keyring' library instead
# pip install keyring
_OBFUSCATION_KEY = "PdHub2026"


def _obfuscate_password(password: str) -> str:
    """
    Simple XOR-based obfuscation for password storage.
    NOT secure encryption - just prevents plaintext storage.

    For production use, replace with keyring library:
        import keyring
        keyring.set_password("ProductionDataHub", "portal", password)
    """
    if not password:
        return ""
    # XOR each character with the key (cycling)
    result = []
    for i, char in enumerate(password):
        key_char = _OBFUSCATION_KEY[i % len(_OBFUSCATION_KEY)]
        result.append(chr(ord(char) ^ ord(key_char)))
    # Base64 encode for safe storage
    return base64.b64encode("".join(result).encode()).decode()


def _deobfuscate_password(obfuscated: str) -> str:
    """Reverse the obfuscation to retrieve password."""
    if not obfuscated:
        return ""
    try:
        # Base64 decode
        decoded = base64.b64decode(obfuscated.encode()).decode()
        # XOR reverse
        result = []
        for i, char in enumerate(decoded):
            key_char = _OBFUSCATION_KEY[i % len(_OBFUSCATION_KEY)]
            result.append(chr(ord(char) ^ ord(key_char)))
        return "".join(result)
    except (binascii.Error, ValueError, UnicodeDecodeError):
        # If deobfuscation fails, return as-is (backward compatibility)
        return obfuscated


# ==========================================================
# .env File I/O
# ==========================================================
def _read_env(env_path: Path) -> dict[str, str]:
    """Parse .env file into a dictionary."""
    result = {}
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    result[key.strip()] = value.strip()
    return result


def _write_env(env_path: Path, data: dict[str, str]):
    """Write dictionary back to .env file, preserving comments."""
    lines = []
    existing_keys = set()

    # Preserve existing comments and update known keys
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    key = stripped.split("=", 1)[0].strip()
                    if key in data:
                        lines.append(f"{key}={data[key]}\n")
                        existing_keys.add(key)
                    else:
                        lines.append(line if line.endswith("\n") else line + "\n")
                else:
                    lines.append(line if line.endswith("\n") else line + "\n")

    # Append new keys not in the original file
    for key, value in data.items():
        if key not in existing_keys:
            lines.append(f"{key}={value}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


# ==========================================================
# Settings Dialog
# ==========================================================
class PortalSettingsDialog(ctk.CTkToplevel):
    """Portal automation settings editor (reads/writes .env directly)."""

    def __init__(self, parent, env_path: Path):
        super().__init__(parent)
        self.env_path = env_path
        self.result = False

        # Window setup
        self.title("⚙️ Portal Automation Settings")
        self.geometry("480x620")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        # Load current values
        self.env_data = _read_env(self.env_path)

        # Deobfuscate password for display
        if "PORTAL_PASSWORD" in self.env_data:
            self.env_data["PORTAL_PASSWORD"] = _deobfuscate_password(self.env_data["PORTAL_PASSWORD"])

        # Build UI
        self._build_ui()

        # Center on parent
        self.after(10, self._center_on_parent)

    def _center_on_parent(self):
        self.update_idletasks()
        parent = self.master
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{px}+{py}")

    def _get(self, key: str, default: str = "") -> str:
        return self.env_data.get(key, default)

    def _build_ui(self):
        pad = {"padx": 20, "pady": (0, 5)}

        # ── Login Section ──
        self._section_label("🔐 로그인 정보")

        self.ent_username = self._labeled_entry("사용자명", self._get("PORTAL_USERNAME"))
        self.ent_password = self._labeled_entry("비밀번호", self._get("PORTAL_PASSWORD"), show="•")

        # ── Search Section ──
        self._section_label("🔍 검색 설정")

        self.ent_keyword = self._labeled_entry("검색 키워드", self._get("SEARCH_KEYWORD", "자재"))
        self.ent_start_date = self._labeled_entry("시작 날짜 (YYYY.MM.DD)", self._get("SEARCH_START_DATE", "2025.01.01"))

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(fill="x", **pad)
        self.sw_dynamic = ctk.CTkSwitch(row, text="스마트 필터링 (마지막 문서 날짜부터 자동)")
        self.sw_dynamic.pack(side="left", padx=(20, 0))
        if self._get("DYNAMIC_FILTERING", "True").lower() == "true":
            self.sw_dynamic.select()

        row2 = ctk.CTkFrame(self, fg_color="transparent")
        row2.pack(fill="x", **pad)
        ctk.CTkLabel(row2, text="여분 검색 일수:", font=ctk.CTkFont(size=13)).pack(side="left", padx=(20, 10))
        self.ent_days_back = ctk.CTkEntry(row2, width=60, placeholder_text="0")
        self.ent_days_back.pack(side="left")
        self.ent_days_back.insert(0, self._get("DAYS_BACK", "0"))

        # ── Schedule Section ──
        self._section_label("⏰ 스케줄 설정")

        sched_row = ctk.CTkFrame(self, fg_color="transparent")
        sched_row.pack(fill="x", **pad)
        ctk.CTkLabel(sched_row, text="실행 시간:", font=ctk.CTkFont(size=13)).pack(side="left", padx=(20, 10))
        self.ent_schedule = ctk.CTkEntry(sched_row, width=80, placeholder_text="09:00")
        self.ent_schedule.pack(side="left")
        self.ent_schedule.insert(0, self._get("SCHEDULE_TIME", "09:00"))

        switch_frame = ctk.CTkFrame(self, fg_color="transparent")
        switch_frame.pack(fill="x", **pad)

        self.sw_auto = ctk.CTkSwitch(switch_frame, text="자동 실행")
        self.sw_auto.pack(side="left", padx=(20, 20))
        if self._get("AUTO_ENABLED", "True").lower() == "true":
            self.sw_auto.select()

        self.sw_weekdays = ctk.CTkSwitch(switch_frame, text="평일만")
        self.sw_weekdays.pack(side="left", padx=(0, 20))
        if self._get("WEEKDAYS_ONLY", "False").lower() == "true":
            self.sw_weekdays.select()

        switch_frame2 = ctk.CTkFrame(self, fg_color="transparent")
        switch_frame2.pack(fill="x", **pad)
        self.sw_headless = ctk.CTkSwitch(switch_frame2, text="헤드리스 모드 (백그라운드 실행)")
        self.sw_headless.pack(side="left", padx=(20, 0))
        if self._get("HEADLESS_MODE", "False").lower() == "true":
            self.sw_headless.select()

        # ── Buttons ──
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(20, 20))

        ctk.CTkButton(btn_frame, text="💾 저장", command=self._save, fg_color="#2e7d32",
                       hover_color="#388e3c", width=120).pack(side="right", padx=(10, 0))
        ctk.CTkButton(btn_frame, text="취소", command=self.destroy, fg_color="#546e7a",
                       width=80).pack(side="right")

    # ── Helpers ──
    def _section_label(self, text: str):
        ctk.CTkLabel(self, text=text, font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="#ffffff").pack(anchor="w", padx=20, pady=(15, 5))

    def _labeled_entry(self, label: str, value: str, show: str = "") -> ctk.CTkEntry:
        ctk.CTkLabel(self, text=label, font=ctk.CTkFont(size=13)).pack(anchor="w", padx=20, pady=(2, 0))
        entry = ctk.CTkEntry(self, width=420, show=show) if show else ctk.CTkEntry(self, width=420)
        entry.pack(padx=20, pady=(0, 5))
        entry.insert(0, value)
        return entry

    def _save(self):
        """Collect values and write to .env."""
        # --- Input validation ---
        username = self.ent_username.get().strip()
        password = self.ent_password.get().strip()
        if not username:
            messagebox.showwarning("경고", "사용자명을 입력해주세요.", parent=self)
            self.ent_username.focus()
            return
        if not password:
            messagebox.showwarning("경고", "비밀번호를 입력해주세요.", parent=self)
            self.ent_password.focus()
            return

        date_str = self.ent_start_date.get().strip()
        if date_str:
            parts = date_str.split(".")
            if len(parts) != 3 or not all(p.isdigit() for p in parts):
                messagebox.showwarning("경고", "시작 날짜 형식이 올바르지 않습니다. (YYYY.MM.DD)", parent=self)
                self.ent_start_date.focus()
                return

        # --- Collect and save ---
        updated = dict(self.env_data)  # preserve existing keys

        updated["PORTAL_USERNAME"] = username
        updated["PORTAL_PASSWORD"] = _obfuscate_password(password)  # Obfuscate before storage
        updated["SEARCH_KEYWORD"] = self.ent_keyword.get().strip() or "자재"
        updated["SEARCH_START_DATE"] = date_str or "2025.01.01"
        updated["DYNAMIC_FILTERING"] = str(bool(self.sw_dynamic.get()))
        updated["DAYS_BACK"] = self.ent_days_back.get().strip() or "0"
        updated["SCHEDULE_TIME"] = self.ent_schedule.get().strip() or "09:00"
        updated["AUTO_ENABLED"] = str(bool(self.sw_auto.get()))
        updated["WEEKDAYS_ONLY"] = str(bool(self.sw_weekdays.get()))
        updated["HEADLESS_MODE"] = str(bool(self.sw_headless.get()))

        _write_env(self.env_path, updated)
        self.result = True
        self.destroy()
