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

from manager_theme import (
    BG_INNER,
    TEXT,
    TEXT_MUTED,
    btn_danger,
    btn_ghost,
    btn_outline_primary,
    btn_primary,
    ctk_font,
)


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

        # 수집 작업(키워드 단위 대칭 모델)은 봇 config.json에 저장된다.
        # env_path = webcloring-pdf/.env → config.json = webcloring-pdf/src/config/config.json
        self.config_path = self.env_path.parent / "src" / "config" / "config.json"
        self.jobs = self._read_jobs()

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

        # ── Search Section ── (키워드는 아래 '수집 작업'에서 작업별로 지정)
        self._section_label("🔍 검색 설정 (공통)")

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

        # ── Collection Jobs Section (키워드 단위 대칭 작업) ──
        self._section_label("🗂️ 수집 작업 (키워드별)")
        ctk.CTkLabel(
            self,
            text="키워드마다 독립된 수집 작업입니다(자재·PBHAv1.0 등 동등). 시각은 쉼표로\n"
                 "여러 개, 비우면 수동 전용. 예: 자재 → 09:00 / PBHAv1.0 → 13:00,17:00\n"
                 "추가/삭제는 즉시 저장되며, 실행 중인 스케줄에는 봇 재시작 후 적용됩니다.",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED, justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 4))

        self.job_list_frame = ctk.CTkScrollableFrame(self, height=110, fg_color=BG_INNER)
        self.job_list_frame.pack(fill="x", padx=20, pady=(0, 5))

        add_row = ctk.CTkFrame(self, fg_color="transparent")
        add_row.pack(fill="x", padx=20, pady=(0, 5))
        self.ent_job_keyword = ctk.CTkEntry(add_row, width=150, placeholder_text="키워드 (예: PBHAv1.0)")
        self.ent_job_keyword.pack(side="left")
        self.ent_job_times = ctk.CTkEntry(add_row, width=150, placeholder_text="시각 09:00,13:00 (비우면 수동)")
        self.ent_job_times.pack(side="left", padx=(8, 8))
        ctk.CTkButton(add_row, text="추가", width=60, command=self._add_job,
                      **btn_outline_primary()).pack(side="left")
        self._refresh_job_list()

        # ── Run Options Section ── (시각은 위 '수집 작업'에서 작업별로 지정)
        self._section_label("⏰ 실행 옵션")

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

        ctk.CTkButton(btn_frame, text="저장", command=self._save, width=120,
                       **btn_primary()).pack(side="right", padx=(10, 0))
        ctk.CTkButton(btn_frame, text="취소", command=self.destroy, width=80,
                       **btn_ghost()).pack(side="right")

    # ── Helpers ──
    def _section_label(self, text: str):
        ctk.CTkLabel(self, text=text, font=ctk_font({"family": "Segoe UI", "size": 15, "weight": "bold"}),
                     text_color=TEXT).pack(anchor="w", padx=20, pady=(15, 5))

    def _labeled_entry(self, label: str, value: str, show: str = "") -> ctk.CTkEntry:
        ctk.CTkLabel(self, text=label, font=ctk.CTkFont(size=13)).pack(anchor="w", padx=20, pady=(2, 0))
        entry = ctk.CTkEntry(self, width=420, show=show) if show else ctk.CTkEntry(self, width=420)
        entry.pack(padx=20, pady=(0, 5))
        entry.insert(0, value)
        return entry

    # ── Collection jobs (config.json: search.jobs) ──
    def _read_jobs(self) -> list[dict]:
        """봇 config.json의 search.jobs 로드. 없으면 구 profiles에서 마이그레이션."""
        try:
            if self.config_path.exists():
                with open(self.config_path, encoding="utf-8") as f:
                    cfg = json.load(f)
                sec = cfg.get("search", {}) or {}
                raw = sec.get("jobs")
                if raw:
                    return [
                        {"keyword": str(j.get("keyword", "")).strip(),
                         "times": [str(t).strip() for t in (j.get("times") or []) if str(t).strip()]}
                        for j in raw
                        if isinstance(j, dict) and str(j.get("keyword", "")).strip()
                    ]
                # 구 profiles({time,keyword}) → 키워드별 그룹
                grouped: dict[str, list] = {}
                for p in (sec.get("profiles") or []):
                    if not isinstance(p, dict):
                        continue
                    kw = str(p.get("keyword", "")).strip()
                    t = str(p.get("time", "")).strip()
                    if kw and t and t not in grouped.setdefault(kw, []):
                        grouped[kw].append(t)
                if grouped:
                    return [{"keyword": k, "times": sorted(v)} for k, v in grouped.items()]
        except (OSError, json.JSONDecodeError):
            pass
        return []

    def _write_jobs(self) -> bool:
        """현재 작업을 config.json의 search.jobs에 저장(다른 키 보존, profiles 비움)."""
        try:
            cfg = {}
            if self.config_path.exists():
                with open(self.config_path, encoding="utf-8") as f:
                    cfg = json.load(f)
            sec = cfg.setdefault("search", {})
            sec["jobs"] = self.jobs
            sec["profiles"] = []  # 레거시 일원화
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            return True
        except (OSError, json.JSONDecodeError) as e:
            messagebox.showwarning("경고", f"작업 저장 실패: {e}", parent=self)
            return False

    def _refresh_job_list(self):
        """작업 리스트 UI를 현재 self.jobs로 다시 그린다."""
        for w in self.job_list_frame.winfo_children():
            w.destroy()
        if not self.jobs:
            ctk.CTkLabel(
                self.job_list_frame,
                text="(작업 없음 — 키워드를 추가하세요. 예: 자재 09:00)",
                font=ctk.CTkFont(size=11), text_color=TEXT_MUTED,
            ).pack(anchor="w", padx=6, pady=4)
            return
        for j in sorted(self.jobs, key=lambda x: x["keyword"]):
            row = ctk.CTkFrame(self.job_list_frame, fg_color="transparent")
            row.pack(fill="x", pady=1)
            ctk.CTkLabel(row, text=j["keyword"], width=120, anchor="w",
                         font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
            times_txt = ", ".join(j["times"]) if j["times"] else "(수동 전용)"
            ctk.CTkLabel(row, text=times_txt,
                         font=ctk.CTkFont(size=12)).pack(side="left", padx=(8, 0))
            ctk.CTkButton(row, text="✕", width=28, **btn_danger(),
                          command=lambda k=j: self._remove_job(k)).pack(side="right")

    def _add_job(self):
        k = self.ent_job_keyword.get().strip()
        raw_times = self.ent_job_times.get().strip()
        if not k:
            messagebox.showwarning("경고", "키워드를 입력하세요.", parent=self)
            self.ent_job_keyword.focus()
            return
        # 시각 파싱 (쉼표 구분, 비우면 수동 전용)
        times = []
        for part in raw_times.replace(" ", "").split(","):
            if not part:
                continue
            if not re.match(r"^\d{1,2}:\d{2}$", part):
                messagebox.showwarning("경고", f"시각 형식 오류: '{part}' (HH:MM, 쉼표 구분)", parent=self)
                return
            hh, mm = (int(x) for x in part.split(":"))
            if not (0 <= hh <= 23 and 0 <= mm <= 59):
                messagebox.showwarning("경고", f"시각 범위 오류: '{part}'", parent=self)
                return
            t = f"{hh:02d}:{mm:02d}"
            if t not in times:
                times.append(t)
        if any(j["keyword"] == k for j in self.jobs):
            messagebox.showwarning("경고", f"'{k}' 작업이 이미 있습니다. 삭제 후 다시 추가하세요.", parent=self)
            return
        self.jobs.append({"keyword": k, "times": sorted(times)})
        self.ent_job_keyword.delete(0, "end")
        self.ent_job_times.delete(0, "end")
        self._persist_jobs()

    def _remove_job(self, target: dict):
        self.jobs = [j for j in self.jobs if j["keyword"] != target["keyword"]]
        self._persist_jobs()

    def _persist_jobs(self):
        """추가/삭제 즉시 config.json에 저장한다.

        하단 '저장' 버튼은 .env 검증(로그인 정보 필수)에 묶여 있어, 작업만
        고치고 창을 닫으면 변경이 버려지는 함정이 있었다(창을 다시 열면
        삭제한 키워드가 부활). 실패 시엔 config.json 기준으로 되돌린다.
        """
        if not self._write_jobs():
            self.jobs = self._read_jobs()
        self._refresh_job_list()

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
        updated["SEARCH_START_DATE"] = date_str or "2025.01.01"
        updated["DYNAMIC_FILTERING"] = str(bool(self.sw_dynamic.get()))
        updated["DAYS_BACK"] = self.ent_days_back.get().strip() or "0"
        updated["AUTO_ENABLED"] = str(bool(self.sw_auto.get()))
        updated["WEEKDAYS_ONLY"] = str(bool(self.sw_weekdays.get()))
        updated["HEADLESS_MODE"] = str(bool(self.sw_headless.get()))
        # SEARCH_KEYWORD/SCHEDULE_TIME은 더 이상 UI에서 안 다룬다(작업 목록으로 일원화).
        # 기존 .env 값은 보존(레거시 폴백 앵커) — updated가 env_data 복사본이라 유지됨.

        _write_env(self.env_path, updated)
        self._write_jobs()  # 수집 작업 → config.json (search.jobs)
        self.result = True
        self.destroy()
