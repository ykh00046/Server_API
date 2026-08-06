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
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

import portal_jobs_logic as jobs_logic
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
            text="추가/편집/일시정지는 즉시 저장되며, 실행 중인 스케줄에는 봇 재시작 후 적용됩니다.",
            font=ctk.CTkFont(size=11), text_color=TEXT_MUTED, justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 4))

        self.job_list_frame = ctk.CTkScrollableFrame(self, height=140, fg_color=BG_INNER)
        self.job_list_frame.pack(fill="x", padx=20, pady=(0, 5))

        add_row = ctk.CTkFrame(self, fg_color="transparent")
        add_row.pack(fill="x", padx=20, pady=(0, 5))
        ctk.CTkButton(add_row, text="[+ 작업 추가]", command=self._open_add_modal,
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
        """봇 config.json의 search.jobs 로드. 없으면 구 profiles에서 마이그레이션.

        enabled 를 보존한다(부재 시 True) — design §4 'enabled 하위 호환'.
        """
        try:
            if self.config_path.exists():
                with open(self.config_path, encoding="utf-8") as f:
                    cfg = json.load(f)
                sec = cfg.get("search", {}) or {}
                raw = sec.get("jobs")
                if raw:
                    return jobs_logic.normalize_jobs(raw)
                # 구 profiles({time,keyword}) → 키워드별 그룹 (enabled 개념 없음→True)
                grouped: dict[str, list] = {}
                for p in (sec.get("profiles") or []):
                    if not isinstance(p, dict):
                        continue
                    kw = str(p.get("keyword", "")).strip()
                    t = str(p.get("time", "")).strip()
                    if kw and t and t not in grouped.setdefault(kw, []):
                        grouped[kw].append(t)
                if grouped:
                    return [
                        {"keyword": k, "times": sorted(v), "enabled": True}
                        for k, v in grouped.items()
                    ]
        except (OSError, json.JSONDecodeError):
            pass
        return []

    def _write_jobs(self) -> bool:
        """현재 작업을 config.json의 search.jobs에 저장(다른 키 보존, profiles 비움).

        jobs 항목은 {keyword, times, enabled} 를 모두 기록한다.
        """
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

    def _collectors(self) -> dict:
        """config.json 의 search.collectors 를 읽는다(배지 해석용)."""
        try:
            if self.config_path.exists():
                with open(self.config_path, encoding="utf-8") as f:
                    return (json.load(f).get("search", {}) or {}).get("collectors", {}) or {}
        except (OSError, json.JSONDecodeError):
            pass
        return {}

    def _dataset_route(self, keyword: str) -> str:
        """config.json 의 api_backup.dataset_routes[키워드] 를 읽는다(없으면 /materials)."""
        try:
            if self.config_path.exists():
                with open(self.config_path, encoding="utf-8") as f:
                    routes = (json.load(f).get("api_backup", {}) or {}).get("dataset_routes", {}) or {}
                    return routes.get(keyword, "/materials") or "/materials"
        except (OSError, json.JSONDecodeError):
            pass
        return "/materials"

    def _refresh_job_list(self):
        """작업 리스트 UI를 현재 self.jobs로 다시 그린다 (design §3.1)."""
        for w in self.job_list_frame.winfo_children():
            w.destroy()
        if not self.jobs:
            ctk.CTkLabel(
                self.job_list_frame,
                text="(작업 없음 — [+ 작업 추가]로 등록하세요. 예: 자재 09:00)",
                font=ctk.CTkFont(size=11), text_color=TEXT_MUTED,
            ).pack(anchor="w", padx=6, pady=4)
            return
        collectors = self._collectors()
        for j in sorted(self.jobs, key=lambda x: x["keyword"]):
            self._build_job_row(j, collectors)

    def _build_job_row(self, job: dict, collectors: dict):
        """단일 작업 행을 구성: enabled 스위치 + bold 키워드 + 배지 + 시각 + ✏️/✕."""
        kw = job["keyword"]
        enabled = job.get("enabled", True)
        badge, is_fallback = jobs_logic.resolve_badge(collectors, kw)
        muted = not enabled

        row = ctk.CTkFrame(self.job_list_frame, fg_color="transparent")
        row.pack(fill="x", pady=1)

        sw = ctk.CTkSwitch(row, text="", width=40,
                           command=lambda k=kw: self._toggle_enabled(k))
        sw.pack(side="left", padx=(4, 4))
        if enabled:
            sw.select()
        label_color = TEXT_MUTED if muted else TEXT
        badge_color = TEXT_MUTED if (muted or is_fallback) else TEXT
        ctk.CTkLabel(row, text=kw, width=120, anchor="w",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=label_color).pack(side="left")
        ctk.CTkLabel(row, text=f"[{badge}]", width=120, anchor="w",
                     font=ctk.CTkFont(size=11),
                     text_color=badge_color).pack(side="left")
        times_txt = ", ".join(job["times"]) if job["times"] else "(수동 전용)"
        ctk.CTkLabel(row, text=times_txt,
                     font=ctk.CTkFont(size=12),
                     text_color=label_color).pack(side="left", padx=(8, 0))
        ctk.CTkButton(row, text="✏️", width=32, **btn_ghost(),
                      command=lambda k=kw: self._open_edit_modal(k)).pack(side="right")
        ctk.CTkButton(row, text="✕", width=28, **btn_danger(),
                      command=lambda k=kw: self._confirm_remove(k)).pack(side="right")

    def _toggle_enabled(self, keyword: str):
        """enabled 스위치 토글 즉시 저장(일시정지). design §3.1."""
        for j in self.jobs:
            if j["keyword"] == keyword:
                j["enabled"] = not j.get("enabled", True)
                break
        self._persist_jobs()

    def _confirm_remove(self, keyword: str):
        """✕: jobs 에서만 제거. collectors·dataset_routes 스펙은 보존 (design §3.1)."""
        ok = messagebox.askokcancel(
            "작업 삭제",
            f"'{keyword}' 수집 작업을 삭제할까요?\n\n"
            "수집 패턴 설정은 남겨둡니다 — 같은 키워드로 재등록하면 다시 연결됩니다.",
            parent=self,
        )
        if not ok:
            return
        self.jobs = [j for j in self.jobs if j["keyword"] != keyword]
        self._persist_jobs()

    def _persist_jobs(self):
        """추가/편집/일시정지 즉시 config.json에 저장한다.

        하단 '저장' 버튼은 .env 검증(로그인 정보 필수)에 묶여 있어, 작업만
        고치고 창을 닫으면 변경이 버려지는 함정이 있었다(창을 다시 열면
        삭제한 키워드가 부활). 실패 시엔 config.json 기준으로 되돌린다.
        """
        if not self._write_jobs():
            self.jobs = self._read_jobs()
        self._refresh_job_list()

    def _open_add_modal(self):
        """'작업 추가' 모달을 빈 값으로 연다 (design §3.2)."""
        JobEditModal(self, self.config_path, self, original_keyword=None)

    def _open_edit_modal(self, keyword: str):
        """'작업 편집' 모달을 해당 작업 값으로 프리필해 연다 (design §3.2)."""
        JobEditModal(self, self.config_path, self, original_keyword=keyword)

    def on_modal_saved(self):
        """모달 저장 성공 후: jobs 재로드 + 리스트 갱신 (config.json 이 단일 출처)."""
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
        updated["HEADLESS_MODE"] = str(bool(self.sw_headless.get()))
        # WEEKDAYS_ONLY(죽은 전역 설정)는 design §3.3 에서 제거 — 주중 제약은
        # collectors[키워드].weekdays 로 작업별 지정. .env 잔류 키는 무해하므로
        # (봇 settings.weekdays_only 호출부 없음) 마이그레이션하지 않고 여기서
        # 더 이상 기록하지도 않는다.
        # SEARCH_KEYWORD/SCHEDULE_TIME은 더 이상 UI에서 안 다룬다(작업 목록으로 일원화).
        # 기존 .env 값은 보존(레거시 폴백 앵커) — updated가 env_data 복사본이라 유지됨.

        _write_env(self.env_path, updated)
        self._write_jobs()  # 수집 작업 → config.json (search.jobs)
        self.result = True
        self.destroy()


# ==========================================================
# 작업 추가/편집 모달 (design §3.2)
# ==========================================================
# 데이터셋 드롭다운 정적 리스트 — 서버 api/materials/datasets.py registry 와
# 일치해야 한다(코드 주석으로 동기화 의무 명시). 새 데이터셋은 별도 작업.
_DATASET_ROUTES = ["/materials", "/binder"]


class JobEditModal(ctk.CTkToplevel):
    """수집 작업 추가/편집 모달 (design §3.2).

    manager.py 의 _pick_keyword_dialog 와 같은 계열(transient + grab_set, 부모 중앙).
    저장 시 jobs_logic.merge_job_form 으로 config.json 세 키를 원자적으로 갱신한다.
    """

    def __init__(self, parent: "PortalSettingsDialog", config_path: Path,
                 owner: "PortalSettingsDialog", original_keyword: str | None):
        super().__init__(parent)
        self.owner = owner
        self.config_path = config_path
        self.original_keyword = original_keyword
        self._dataset_auto = True  # 사용자가 드롭다운을 직접 바꾸기 전까지 자동 전환

        mode = "편집" if original_keyword else "추가"
        self.title(f"수집 작업 {mode}")
        self.geometry("460x560")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build()
        self._prefill()
        self._sync_binder_visibility()

        self.after(10, self._center_on_parent)

    def _center_on_parent(self):
        self.update_idletasks()
        parent = self.master
        px = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{px}+{py}")

    # ── Build ──
    def _build(self):
        pad = {"padx": 20, "pady": (0, 5)}
        ctk.CTkLabel(self, text=f"수집 작업 {('편집' if self.original_keyword else '추가')}",
                     font=ctk_font({"family": "Segoe UI", "size": 15, "weight": "bold"}),
                     text_color=TEXT).pack(anchor="w", padx=20, pady=(15, 5))

        # 키워드 / 실행 시각
        ctk.CTkLabel(self, text="키워드", font=ctk.CTkFont(size=13)).pack(anchor="w", padx=20)
        self.ent_keyword = ctk.CTkEntry(self, width=420, placeholder_text="예: PBHAv1.0")
        self.ent_keyword.pack(padx=20, pady=(0, 5))

        ctk.CTkLabel(self, text="실행 시각", font=ctk.CTkFont(size=13)).pack(anchor="w", padx=20)
        self.ent_times = ctk.CTkEntry(self, width=420, placeholder_text="22:00 (쉼표로 여러 개, 비우면 수동 전용)")
        self.ent_times.pack(padx=20, pady=(0, 2))
        ctk.CTkLabel(self, text="(쉼표로 여러 개, 비우면 수동 전용)",
                     font=ctk.CTkFont(size=11), text_color=TEXT_MUTED).pack(anchor="w", padx=20)

        # 활성화 스위치
        sw_row = ctk.CTkFrame(self, fg_color="transparent")
        sw_row.pack(fill="x", **pad)
        self.sw_enabled = ctk.CTkSwitch(sw_row, text="활성화")
        self.sw_enabled.pack(side="left", padx=(20, 0))
        self.sw_enabled.select()

        # ── 수집 패턴 ──
        ctk.CTkLabel(self, text="── 수집 패턴 ──", font=ctk.CTkFont(size=12),
                     text_color=TEXT_MUTED).pack(anchor="w", padx=20, pady=(8, 2))
        self.pat_var = ctk.StringVar(value="materials")
        ctk.CTkRadioButton(
            self, text="완료문서함 — 양식명 검색 (자재 방식)",
            variable=self.pat_var, value="materials",
            command=self._on_pattern_change,
        ).pack(anchor="w", padx=20, pady=1)
        ctk.CTkRadioButton(
            self, text="부서공개함 — 기안자/문서제목 검색 (PBHA 방식)",
            variable=self.pat_var, value="binder",
            command=self._on_pattern_change,
        ).pack(anchor="w", padx=20, pady=1)

        # 부서공개함 옵션 (binder 선택 시에만 표시)
        self.binder_frame = ctk.CTkFrame(self, fg_color=BG_INNER)
        self.binder_frame.pack(fill="x", padx=20, pady=(4, 5))
        ctk.CTkLabel(self.binder_frame, text="부서공개함 옵션",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=10, pady=(8, 2))
        ctk.CTkLabel(self.binder_frame, text="기안자", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=10)
        self.ent_drafter = ctk.CTkEntry(self.binder_frame, width=380, placeholder_text="예: 김지훈")
        self.ent_drafter.pack(padx=10, pady=(0, 2))
        ctk.CTkLabel(self.binder_frame, text="문서제목 포함", font=ctk.CTkFont(size=12)).pack(anchor="w", padx=10)
        self.ent_title = ctk.CTkEntry(self.binder_frame, width=380, placeholder_text="예: PBHA")
        self.ent_title.pack(padx=10, pady=(0, 2))
        self.sw_weekdays = ctk.CTkSwitch(self.binder_frame, text="평일만 실행")
        self.sw_weekdays.pack(anchor="w", padx=10, pady=(2, 8))

        # 서버 데이터셋
        ctk.CTkLabel(self, text="서버 데이터셋", font=ctk.CTkFont(size=13)).pack(anchor="w", padx=20)
        self.route_var = ctk.StringVar(value="/materials")
        self.opt_dataset = ctk.CTkOptionMenu(
            self, values=_DATASET_ROUTES, variable=self.route_var,
            command=self._on_dataset_manual_change,
        )
        self.opt_dataset.pack(anchor="w", padx=20, pady=(0, 2))
        ctk.CTkLabel(self, text="(패턴 선택 시 자동 지정, 변경 가능)",
                     font=ctk.CTkFont(size=11), text_color=TEXT_MUTED).pack(anchor="w", padx=20)

        # 버튼
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(12, 16))
        ctk.CTkButton(btn_frame, text="저장", width=120, command=self._on_save,
                      **btn_primary()).pack(side="right", padx=(10, 0))
        ctk.CTkButton(btn_frame, text="취소", width=80, command=self.destroy,
                      **btn_ghost()).pack(side="right")

    def _on_pattern_change(self):
        """패턴 라디오 변경: 부서공개함 옵션 show/hide + 데이터셋 자동 전환."""
        self._sync_binder_visibility()
        if self._dataset_auto:
            route = "/binder" if self.pat_var.get() == "binder" else "/materials"
            self.route_var.set(route)

    def _on_dataset_manual_change(self, _value: str):
        """사용자가 드롭다운을 직접 바꾸면 이후 자동 전환을 끈다 (design §3.2)."""
        self._dataset_auto = False

    def _sync_binder_visibility(self):
        if self.pat_var.get() == "binder":
            self.binder_frame.pack(fill="x", padx=20, pady=(4, 5))
        else:
            self.binder_frame.pack_forget()

    # ── Prefill ──
    def _prefill(self):
        """편집 모드: jobs + collectors + dataset_routes 에서 모든 필드를 채운다."""
        if not self.original_keyword:
            return
        job = next((j for j in self.owner.jobs if j["keyword"] == self.original_keyword), None)
        if job:
            self.ent_keyword.insert(0, job["keyword"])
            self.ent_times.insert(0, ", ".join(job["times"]))
            if job.get("enabled", True):
                self.sw_enabled.select()
            else:
                self.sw_enabled.deselect()
        collectors = self.owner._collectors()
        spec = collectors.get(self.original_keyword, {}) or {}
        ctype = str(spec.get("type", "")).strip()
        if ctype == "binder":
            self.pat_var.set("binder")
            self.ent_drafter.insert(0, str(spec.get("drafter", "")))
            self.ent_title.insert(0, str(spec.get("title", "")))
            if spec.get("weekdays"):
                self.sw_weekdays.select()
        else:
            self.pat_var.set("materials")
        route = self.owner._dataset_route(self.original_keyword)
        self.route_var.set(route)
        # 편집 모드에서 프리필된 데이터셋이 패턴과 다르면 사용자가 이미 커스터마이징한 것.
        expected = "/binder" if self.pat_var.get() == "binder" else "/materials"
        self._dataset_auto = route == expected

    # ── Save ──
    def _on_save(self):
        """저장: 검증 → merge → config.json 한 번에 기록. 실패 시 모달 유지."""
        keyword = self.ent_keyword.get().strip()
        pattern = self.pat_var.get()
        drafter = self.ent_drafter.get()
        title = self.ent_title.get()
        times, t_err = jobs_logic.validate_times(self.ent_times.get())
        if t_err:
            messagebox.showwarning("경고", t_err, parent=self)
            self.ent_times.focus()
            return
        # config 로드(검증·병합의 단일 출처)
        cfg = self._load_config()
        if cfg is None:
            return
        errors = jobs_logic.validate_form(
            cfg, keyword, pattern, drafter, title, self.original_keyword
        )
        if errors:
            messagebox.showwarning("경고", "\n".join(errors), parent=self)
            self.ent_keyword.focus()
            return
        jobs_logic.merge_job_form(
            cfg,
            keyword=keyword,
            times=times,
            enabled=bool(self.sw_enabled.get()),
            pattern=pattern,
            drafter=drafter,
            title=title,
            weekdays=bool(self.sw_weekdays.get()),
            dataset_route=self.route_var.get(),
            original_keyword=self.original_keyword,
        )
        if not self._write_config(cfg):
            return  # _write_config 가 이미 경고를 띄움
        self.owner.on_modal_saved()
        self.destroy()

    def _load_config(self) -> dict | None:
        try:
            if self.config_path.exists():
                with open(self.config_path, encoding="utf-8") as f:
                    return json.load(f)
            return {}
        except (OSError, json.JSONDecodeError) as e:
            messagebox.showwarning("경고", f"config.json 로드 실패: {e}", parent=self)
            return None

    def _write_config(self, cfg: dict) -> bool:
        """config.json 을 한 번의 json.dump 로 기록 (원자적 3-키 갱신)."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
            return True
        except (OSError, json.JSONDecodeError) as e:
            messagebox.showwarning("경고", f"작업 저장 실패: {e}", parent=self)
            return False
