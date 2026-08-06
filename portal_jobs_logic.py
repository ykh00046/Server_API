"""portal_jobs_logic — 매니저 수집 작업 UI의 순수 로직 계층.

이 모듈은 customtkinter/tkinter 에 **의존하지 않는다** (CI 가 headless).
portal_settings_dialog.py 의 위젯 코드에서 분리된, 검증·정규화·병합 로직만
담는다 — 위젯 없이 단위 테스트할 수 있도록.

저장 매핑 규칙은 docs/02-design/features/manager-collector-ui-v1.design.md
§4(데이터 모델 / 저장 매핑)가 단일 출처이다.

세 곳의 config.json 키를 원자적으로(한 번의 json.dump) 다룬다:
  - search.jobs[]                : {keyword, times, enabled}
  - search.collectors[키워드]     : {type, box, drafter, title, weekdays}
  - api_backup.dataset_routes[키워드] : "/materials" | "/binder"
"""

from __future__ import annotations

import re
from typing import Any

# 시각 검증 정규식 — portal_settings_dialog._add_job 의 구 의미를 그대로 가져옴.
# HH:MM (HH 1~2자리 허용), 쉼표로 여러 개. 비면 수동 전용(빈 리스트).
_TIME_PART_RE = re.compile(r"^\d{1,2}:\d{2}$")

# collectors box 유도값 (UI 미노출) — design §4.
_BOX_BY_PATTERN = {"materials": "completed", "binder": "dept_open"}

# collectors type 허용값
_PATTERNS = ("materials", "binder")


# ==========================================================
# 작업 목록 정규화
# ==========================================================
def normalize_jobs(raw: Any) -> list[dict]:
    """config 의 search.jobs 원소를 정규화한다.

    - keyword: strip, 빈 값은 버린다.
    - times: 빈 항목 제거 + 정규화된 리스트.
    - enabled: 부재 시 True(하위 호환). 비bool 값은 bool() 로 정규화.

    design §4 'enabled 하위 호환' + 봇 settings.search_jobs 와 동일 의미.
    """
    if not isinstance(raw, list):
        return []
    jobs: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        keyword = str(item.get("keyword", "")).strip()
        if not keyword:
            continue
        times = [str(t).strip() for t in (item.get("times") or []) if str(t).strip()]
        jobs.append({
            "keyword": keyword,
            "times": times,
            "enabled": bool(item.get("enabled", True)),
        })
    return jobs


# ==========================================================
# 시각 문자열 검증
# ==========================================================
def validate_times(raw: str) -> tuple[list[str], str | None]:
    """HH:MM 쉼표 목록을 검증·정규화한다.

    Returns:
        (times, error) — error 가 None 이면 times 는 중복 제거·정렬된
        "HH:MM" 리스트. raw 가 비면 ([], None) (수동 전용).
    """
    text = (raw or "").replace(" ", "")
    if not text:
        return [], None
    times: list[str] = []
    for part in text.split(","):
        if not part:
            continue
        if not _TIME_PART_RE.match(part):
            return [], f"시각 형식 오류: '{part}' (HH:MM, 쉼표 구분)"
        hh, mm = (int(x) for x in part.split(":"))
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            return [], f"시각 범위 오류: '{part}'"
        norm = f"{hh:02d}:{mm:02d}"
        if norm not in times:
            times.append(norm)
    return sorted(times), None


# ==========================================================
# 패턴 배지 해석
# ==========================================================
def resolve_badge(collectors: dict, keyword: str) -> tuple[str, bool]:
    """collectors 사전에서 키워드의 패턴 배지를 해석한다.

    design §3.1:
      - type=="binder" → "부서공개함", weekdays 면 "부서공개함·평일".
      - type=="materials" (명시) → "완료문서함".
      - entry 없음(폴백) → "완료문서함(기본)", fallback=True.

    Returns:
        (badge_text, is_fallback)
    """
    spec = (collectors or {}).get(keyword, {}) or {}
    ctype = str(spec.get("type", "")).strip()
    if ctype == "binder":
        if spec.get("weekdays"):
            return "부서공개함·평일", False
        return "부서공개함", False
    if ctype == "materials":
        return "완료문서함", False
    return "완료문서함(기본)", True


# ==========================================================
# 모달 저장 병합 — 검증
# ==========================================================
def validate_form(
    config: dict,
    keyword: str,
    pattern: str,
    drafter: str,
    title: str,
    original_keyword: str | None,
) -> list[str]:
    """모달 폼 값의 사전 검증. 에러 메시지 리스트(빈 리스트=통과).

    design §3.2 검증 규칙:
      1. 키워드 필수. 저장 전 strip().
      2. 중복 금지(편집 중인 자기 자신 제외).
      3. binder 선택 시 기안자·문서제목 둘 다 비면 거부.
    """
    errors: list[str] = []
    kw = (keyword or "").strip()
    if not kw:
        errors.append("키워드를 입력하세요.")
    else:
        existing = [
            str(j.get("keyword", "")).strip()
            for j in (config.get("search", {}) or {}).get("jobs", [])
            if isinstance(j, dict)
        ]
        # 편집 모드: 자기 자신(original_keyword)은 중복에서 제외.
        if original_keyword and original_keyword.strip() == kw:
            pass
        elif kw in existing:
            errors.append(f"'{kw}' 작업이 이미 있습니다.")
    if pattern == "binder" and not (drafter or "").strip() and not (title or "").strip():
        errors.append("부서공개함(binder)은 기안자 또는 문서제목이 필요합니다.")
    return errors


# ==========================================================
# 모달 저장 병합 — collectors / dataset_routes 헬퍼
# ==========================================================
def _apply_collectors(
    sec: dict, keyword: str, pattern: str, drafter: str, title: str, weekdays: bool
) -> None:
    """design §4 collectors 기록 규칙을 collectors 사전에 반영.

    - binder: 항상 기록(type/box/drafter/title/weekdays).
    - materials: 기존 entry 가 있을 때만 type=materials 갱신(생성하지 않음).
    """
    collectors = sec.setdefault("collectors", {})
    if not isinstance(collectors, dict):
        collectors = {}
        sec["collectors"] = collectors
    if pattern == "binder":
        collectors[keyword] = {
            "type": "binder",
            "box": _BOX_BY_PATTERN["binder"],
            "drafter": (drafter or "").strip(),
            "title": (title or "").strip(),
            "weekdays": bool(weekdays),
        }
        return
    # materials — 폴백 유지: 기존 entry 가 있을 때만 갱신, 없으면 기록하지 않는다.
    existing = collectors.get(keyword)
    if isinstance(existing, dict):
        existing["type"] = "materials"
        existing["box"] = _BOX_BY_PATTERN["materials"]


def _apply_dataset_routes(api_backup: dict, keyword: str, route: str) -> None:
    """design §4 dataset_routes 규칙.

    - route == "/materials" (폴백 기본값) → entry 를 쓰지 않고, 있으면 삭제.
    - 그 외(/binder 등) → entry 기록.
    """
    routes = api_backup.setdefault("dataset_routes", {})
    if not isinstance(routes, dict):
        routes = {}
        api_backup["dataset_routes"] = routes
    if route == "/materials":
        routes.pop(keyword, None)
    else:
        routes[keyword] = route


def _rename_moves(
    config: dict, old_keyword: str, new_keyword: str
) -> None:
    """rename: collectors·dataset_routes 의 구 키 entry 를 새 키로 이동(orphan 제거)."""
    if old_keyword == new_keyword:
        return
    collectors = (config.get("search", {}) or {}).get("collectors", {})
    if isinstance(collectors, dict) and old_keyword in collectors:
        collectors[new_keyword] = collectors.pop(old_keyword)
    api_backup = config.setdefault("api_backup", {})
    if not isinstance(api_backup, dict):
        return
    routes = api_backup.get("dataset_routes", {})
    if isinstance(routes, dict) and old_keyword in routes:
        routes[new_keyword] = routes.pop(old_keyword)


# ==========================================================
# 모달 저장 병합 — 메인
# ==========================================================
def merge_job_form(
    config: dict,
    *,
    keyword: str,
    times: list[str],
    enabled: bool,
    pattern: str,
    drafter: str,
    title: str,
    weekdays: bool,
    dataset_route: str,
    original_keyword: str | None = None,
) -> dict:
    """모달 폼 값을 config dict 에 병합해 갱신된 config 를 반환.

    design §4 전체 규칙을 한 번에 적용한다. 호출자가 반환값을 한 번의
    json.dump 로 기록한다(원자적 3-키 갱신). 검증은 별도(validate_form)로
    먼저 수행해야 한다 — 이 함수는 정규화된 값을 받아 병합만 한다.

    Args:
        config: 로드된 config.json dict (복사하지 않고 in-place 갱신 후 반환).
        keyword: 새 키워드(strip 가정).
        times: 정규화된 "HH:MM" 리스트(비면 수동 전용).
        enabled: 작업 활성화 여부.
        pattern: "materials" | "binder".
        drafter / title: 부서공개함 검색 필터(binder 에서만 사용).
        weekdays: 평일만 실행 여부(binder 스펙에 기록).
        dataset_route: "/materials" | "/binder".
        original_keyword: 편집 모드의 원래 키워드. 다르면 rename 처리.
    """
    # §4 search.jobs: keyword/times/enabled 갱신(rename 시 구 키 제거).
    sec = config.setdefault("search", {})
    if not isinstance(sec, dict):
        sec = {}
        config["search"] = sec
    jobs = sec.get("jobs")
    if not isinstance(jobs, list):
        jobs = []
    original_kw = (original_keyword or "").strip() or None
    if original_kw and original_kw != keyword:
        jobs = [j for j in jobs if str(j.get("keyword", "")).strip() != original_kw]
    # 동일 키워드 entry 가 있으면 덮어쓰기 위해 제거 후 재추가.
    jobs = [j for j in jobs if str(j.get("keyword", "")).strip() != keyword]
    jobs.append({"keyword": keyword, "times": list(times), "enabled": bool(enabled)})
    sec["jobs"] = jobs
    sec["profiles"] = []  # 레거시 일원화

    # rename: collectors·dataset_routes 구 키 → 새 키 이동(orphan 제거).
    if original_kw and original_kw != keyword:
        _rename_moves(config, original_kw, keyword)

    # §4 collectors 기록 규칙.
    _apply_collectors(sec, keyword, pattern, drafter, title, weekdays)

    # §4 dataset_routes 기록 규칙.
    api_backup = config.setdefault("api_backup", {})
    if isinstance(api_backup, dict):
        _apply_dataset_routes(api_backup, keyword, dataset_route)

    return config
