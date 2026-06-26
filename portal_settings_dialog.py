# portal_settings_dialog.py
"""
Portal Automation Settings Dialog

CustomTkinter dialog for editing webcloring-pdf/.env settings
directly from the ServerManager. No dependency on webcloring-pdf code.

Security Note:
  PORTAL_PASSWORD is stored in plaintext in webcloring-pdf/.env, because the
  bot (webcloring-pdf settings.py) reads PORTAL_PASSWORD verbatim. The .env is
  gitignored and never leaves the machine. Any obfuscation here would have to be
  mirrored by the bot's reader, so the two MUST agree — previously they did not,
  which silently corrupted the saved password. For real secret protection use
  the 'keyring' library on BOTH sides.
"""

import json
import re
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk


# ==========================================================
# .env File I/O
# ==========================================================
def _read_env(env_path: Path) -> dict[str, str]:
    """Parse .env file into a dictionary."""
    result = {}
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
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
        with open(env_path, encoding="utf-8") as f:
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
        self.geometry("500x820")
        self.resizable(False, True)
        self.transient(parent)
        self.grab_set()

        # Load current values (PORTAL_PASSWORD is stored/read as plaintext)
        self.env_data = _read_env(self.env_path)

        # 검색 프로필(시간대별 멀티 키워드)은 봇 config.json에 저장된다.
        # env_path = webcloring-pdf/.env → config.json = webcloring-pdf/src/config/config.json
        self.config_path = self.env_path.parent / "src" / "config" / "config.json"
        self.profiles = self._read_profiles()

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

        # ── Search Profiles Section (시간대별 멀티 키워드) ──
        self._section_label("🗂️ 검색 프로필 (시간대별 멀티 키워드)")
        ctk.CTkLabel(
            self,
            text="시간마다 다른 키워드를 같은 방식으로 수집합니다. 비우면 위 '검색 키워드' 단일 실행.\n"
                 "예: 09:00 자재 · 13:00 PBHAv1.0",
            font=ctk.CTkFont(size=11), text_color="#9e9e9e", justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 4))

        self.profile_list_frame = ctk.CTkScrollableFrame(self, height=100, fg_color="#1e1e1e")
        self.profile_list_frame.pack(fill="x", padx=20, pady=(0, 5))

        add_row = ctk.CTkFrame(self, fg_color="transparent")
        add_row.pack(fill="x", padx=20, pady=(0, 5))
        self.ent_profile_time = ctk.CTkEntry(add_row, width=70, placeholder_text="13:00")
        self.ent_profile_time.pack(side="left")
        self.ent_profile_keyword = ctk.CTkEntry(add_row, width=220, placeholder_text="키워드 (예: PBHAv1.0)")
        self.ent_profile_keyword.pack(side="left", padx=(8, 8))
        ctk.CTkButton(add_row, text="추가", width=60, command=self._add_profile).pack(side="left")
        self._refresh_profile_list()

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

    # ── Search profiles (config.json) ──
    def _read_profiles(self) -> list[dict]:
        """봇 config.json의 search.profiles 로드 (없으면 빈 리스트)."""
        try:
            if self.config_path.exists():
                with open(self.config_path, encoding="utf-8") as f:
                    cfg = json.load(f)
                raw = (cfg.get("search", {}) or {}).get("profiles") or []
                return [
                    {"time": str(p.get("time", "")).strip(),
                     "keyword": str(p.get("keyword", "")).strip()}
                    for p in raw
                    if isinstance(p, dict) and p.get("time") and p.get("keyword")
                ]
        except (OSError, json.JSONDecodeError):
            pass
        return []

    def _write_profiles(self) -> bool:
        """현재 프로필을 config.json의 search.profiles에 저장(다른 키 보존)."""
        try:
            cfg = {}
            if self.config_path.exists():
                with open(self.config_path, encoding="utf-8") as f:
                    cfg = json.load(f)
            cfg.setdefault("search", {})["profiles"] = self.profiles
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            return True
        except (OSError, json.JSONDecodeError) as e:
            messagebox.showwarning("경고", f"프로필 저장 실패: {e}", parent=self)
            return False

    def _refresh_profile_list(self):
        """프로필 리스트 UI를 현재 self.profiles로 다시 그린다."""
        for w in self.profile_list_frame.winfo_children():
            w.destroy()
        if not self.profiles:
            ctk.CTkLabel(
                self.profile_list_frame,
                text="(등록된 프로필 없음 — 단일 '검색 키워드'로 동작)",
                font=ctk.CTkFont(size=11), text_color="#757575",
            ).pack(anchor="w", padx=6, pady=4)
            return
        for p in sorted(self.profiles, key=lambda x: x["time"]):
            row = ctk.CTkFrame(self.profile_list_frame, fg_color="transparent")
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(row, text=p["time"], width=56,
                         font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
            ctk.CTkLabel(row, text=p["keyword"],
                         font=ctk.CTkFont(size=12)).pack(side="left", padx=(8, 0))
            ctk.CTkButton(row, text="✕", width=28, fg_color="#7f3b3b",
                          hover_color="#a04444",
                          command=lambda k=p: self._remove_profile(k)).pack(side="right")

    def _add_profile(self):
        t = self.ent_profile_time.get().strip()
        k = self.ent_profile_keyword.get().strip()
        if not re.match(r"^\d{1,2}:\d{2}$", t):
            messagebox.showwarning("경고", "시간 형식은 HH:MM (예: 13:00)", parent=self)
            return
        hh, mm = (int(x) for x in t.split(":"))
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            messagebox.showwarning("경고", "시간 범위 오류 (00:00~23:59)", parent=self)
            return
        t = f"{hh:02d}:{mm:02d}"
        if not k:
            messagebox.showwarning("경고", "키워드를 입력하세요.", parent=self)
            self.ent_profile_keyword.focus()
            return
        if any(p["time"] == t for p in self.profiles):
            messagebox.showwarning("경고", f"{t} 시간 프로필이 이미 있습니다.", parent=self)
            return
        self.profiles.append({"time": t, "keyword": k})
        self.ent_profile_keyword.delete(0, "end")
        self._refresh_profile_list()

    def _remove_profile(self, target: dict):
        self.profiles = [
            p for p in self.profiles
            if not (p["time"] == target["time"] and p["keyword"] == target["keyword"])
        ]
        self._refresh_profile_list()

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
        updated["PORTAL_PASSWORD"] = password  # plaintext — bot reads PORTAL_PASSWORD verbatim
        updated["SEARCH_KEYWORD"] = self.ent_keyword.get().strip() or "자재"
        updated["SEARCH_START_DATE"] = date_str or "2025.01.01"
        updated["DYNAMIC_FILTERING"] = str(bool(self.sw_dynamic.get()))
        updated["DAYS_BACK"] = self.ent_days_back.get().strip() or "0"
        updated["SCHEDULE_TIME"] = self.ent_schedule.get().strip() or "09:00"
        updated["AUTO_ENABLED"] = str(bool(self.sw_auto.get()))
        updated["WEEKDAYS_ONLY"] = str(bool(self.sw_weekdays.get()))
        updated["HEADLESS_MODE"] = str(bool(self.sw_headless.get()))

        _write_env(self.env_path, updated)
        self._write_profiles()  # 검색 프로필 → config.json
        self.result = True
        self.destroy()
