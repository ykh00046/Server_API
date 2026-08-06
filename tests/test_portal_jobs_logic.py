# tests/test_portal_jobs_logic.py
"""portal_jobs_logic 순수 로직 단위 테스트 (Tk 없는 CI 환경).

design §4(저장 매핑)·§3.1(배지)·§3.2(검증) 규칙을 위젯 없이 검증한다.
이 테스트는 customtkinter/tkinter 를 import 하지 않는다.
"""

from __future__ import annotations

import portal_jobs_logic as jobs_logic


# ==========================================================
# normalize_jobs — enabled 보존
# ==========================================================
class TestNormalizeJobs:
    def test_preserves_explicit_enabled_true(self):
        raw = [{"keyword": "자재", "times": ["09:00"], "enabled": True}]
        out = jobs_logic.normalize_jobs(raw)
        assert out == [{"keyword": "자재", "times": ["09:00"], "enabled": True}]

    def test_preserves_explicit_enabled_false(self):
        raw = [{"keyword": "자재", "times": ["09:00"], "enabled": False}]
        out = jobs_logic.normalize_jobs(raw)
        assert out[0]["enabled"] is False

    def test_enabled_absent_defaults_true(self):
        """design §4 'enabled 하위 호환' — 필드 부재 = True."""
        raw = [{"keyword": "자재", "times": ["09:00"]}]
        out = jobs_logic.normalize_jobs(raw)
        assert out[0]["enabled"] is True

    def test_nonbool_enabled_normalized_via_bool(self):
        raw = [{"keyword": "자재", "times": [], "enabled": 1}]
        out = jobs_logic.normalize_jobs(raw)
        assert out[0]["enabled"] is True

    def test_strips_keyword_and_times(self):
        raw = [{"keyword": "  자재  ", "times": ["  09:00  ", ""]}]
        out = jobs_logic.normalize_jobs(raw)
        assert out[0]["keyword"] == "자재"
        assert out[0]["times"] == ["09:00"]

    def test_drops_empty_keyword(self):
        raw = [{"keyword": "   ", "times": ["09:00"]}]
        assert jobs_logic.normalize_jobs(raw) == []

    def test_drops_non_dict_items(self):
        raw = ["not-a-dict", {"keyword": "자재", "times": ["09:00"]}, 42]
        out = jobs_logic.normalize_jobs(raw)
        assert len(out) == 1
        assert out[0]["keyword"] == "자재"

    def test_non_list_returns_empty(self):
        assert jobs_logic.normalize_jobs(None) == []
        assert jobs_logic.normalize_jobs({"keyword": "x"}) == []


# ==========================================================
# validate_times — HH:MM 쉼표 목록
# ==========================================================
class TestValidateTimes:
    def test_empty_is_manual_only(self):
        times, err = jobs_logic.validate_times("")
        assert times == []
        assert err is None

    def test_empty_after_strip_is_manual_only(self):
        times, err = jobs_logic.validate_times("   ")
        assert times == []
        assert err is None

    def test_single_valid_time(self):
        times, err = jobs_logic.validate_times("09:00")
        assert err is None
        assert times == ["09:00"]

    def test_normalizes_hour_to_two_digits(self):
        times, err = jobs_logic.validate_times("9:05")
        assert err is None
        assert times == ["09:05"]

    def test_multiple_comma_separated(self):
        times, err = jobs_logic.validate_times("13:00, 09:00")
        assert err is None
        assert times == ["09:00", "13:00"]  # 정렬

    def test_dedup(self):
        times, err = jobs_logic.validate_times("09:00,09:00")
        assert err is None
        assert times == ["09:00"]

    def test_bad_format_rejected(self):
        _times, err = jobs_logic.validate_times("9-00")
        assert err is not None
        assert "형식" in err

    def test_out_of_range_rejected(self):
        _times, err = jobs_logic.validate_times("25:00")
        assert err is not None
        assert "범위" in err

    def test_bad_minutes_rejected(self):
        _times, err = jobs_logic.validate_times("09:60")
        assert err is not None
        assert "범위" in err


# ==========================================================
# resolve_badge — 패턴 배지 (폴백 포함)
# ==========================================================
class TestResolveBadge:
    def test_binder_weekdays(self):
        collectors = {"PBHAv1.0": {"type": "binder", "weekdays": True}}
        badge, fallback = jobs_logic.resolve_badge(collectors, "PBHAv1.0")
        assert badge == "부서공개함·평일"
        assert fallback is False

    def test_binder_no_weekdays(self):
        collectors = {"PBHAv1.0": {"type": "binder", "weekdays": False}}
        badge, fallback = jobs_logic.resolve_badge(collectors, "PBHAv1.0")
        assert badge == "부서공개함"
        assert fallback is False

    def test_materials_explicit(self):
        collectors = {"자재": {"type": "materials"}}
        badge, fallback = jobs_logic.resolve_badge(collectors, "자재")
        assert badge == "완료문서함"
        assert fallback is False

    def test_missing_entry_is_fallback(self):
        """design §3.1 — collectors에 entry 없음 → 폴백."""
        badge, fallback = jobs_logic.resolve_badge({}, "자재")
        assert badge == "완료문서함(기본)"
        assert fallback is True

    def test_empty_collectors_dict(self):
        badge, fallback = jobs_logic.resolve_badge(None, "자재")
        assert fallback is True

    def test_binder_weekdays_falsy_treated_as_off(self):
        collectors = {"k": {"type": "binder"}}  # weekdays 키 없음
        badge, fallback = jobs_logic.resolve_badge(collectors, "k")
        assert badge == "부서공개함"
        assert fallback is False


# ==========================================================
# merge_job_form — §4 collectors 규칙
# ==========================================================
class TestMergeCollectors:
    def test_binder_always_written(self):
        """binder: 항상 collectors 에 기록(type/box/drafter/title/weekdays)."""
        cfg = {"search": {"jobs": []}}
        jobs_logic.merge_job_form(
            cfg, keyword="PBHA", times=["22:00"], enabled=True, pattern="binder",
            drafter="김지훈", title="PBHA", weekdays=True, dataset_route="/binder",
        )
        spec = cfg["search"]["collectors"]["PBHA"]
        assert spec["type"] == "binder"
        assert spec["box"] == "dept_open"
        assert spec["drafter"] == "김지훈"
        assert spec["title"] == "PBHA"
        assert spec["weekdays"] is True

    def test_materials_updates_existing_entry_only(self):
        """materials: 기존 entry 가 있을 때만 갱신, 생성하지 않는다(폴백 유지)."""
        cfg = {"search": {"jobs": [], "collectors": {"자재": {"type": "binder", "box": "dept_open"}}}}
        jobs_logic.merge_job_form(
            cfg, keyword="자재", times=["09:00"], enabled=True, pattern="materials",
            drafter="", title="", weekdays=False, dataset_route="/materials",
        )
        spec = cfg["search"]["collectors"]["자재"]
        assert spec["type"] == "materials"
        assert spec["box"] == "completed"

    def test_materials_does_not_create_entry(self):
        """materials + 기존 entry 없음 → collectors 에 기록하지 않는다(폴백 유지)."""
        cfg = {"search": {"jobs": []}}
        jobs_logic.merge_job_form(
            cfg, keyword="신규키워드", times=["09:00"], enabled=True, pattern="materials",
            drafter="", title="", weekdays=False, dataset_route="/materials",
        )
        assert "collectors" not in cfg["search"] or "신규키워드" not in cfg["search"]["collectors"]


# ==========================================================
# merge_job_form — §4 dataset_routes 규칙
# ==========================================================
class TestMergeDatasetRoutes:
    def test_non_materials_route_writes_entry(self):
        cfg = {"search": {"jobs": []}}
        jobs_logic.merge_job_form(
            cfg, keyword="PBHA", times=["22:00"], enabled=True, pattern="binder",
            drafter="김지훈", title="PBHA", weekdays=True, dataset_route="/binder",
        )
        assert cfg["api_backup"]["dataset_routes"]["PBHA"] == "/binder"

    def test_materials_route_writes_no_entry(self):
        cfg = {"search": {"jobs": []}}
        jobs_logic.merge_job_form(
            cfg, keyword="자재", times=["09:00"], enabled=True, pattern="materials",
            drafter="", title="", weekdays=False, dataset_route="/materials",
        )
        routes = cfg.get("api_backup", {}).get("dataset_routes", {})
        assert "자재" not in routes

    def test_materials_route_deletes_existing_entry(self):
        """route=='/materials' → 기존 entry 삭제(config 최소 유지)."""
        cfg = {
            "search": {"jobs": []},
            "api_backup": {"dataset_routes": {"자재": "/binder"}},
        }
        jobs_logic.merge_job_form(
            cfg, keyword="자재", times=["09:00"], enabled=True, pattern="materials",
            drafter="", title="", weekdays=False, dataset_route="/materials",
        )
        assert "자재" not in cfg["api_backup"]["dataset_routes"]


# ==========================================================
# merge_job_form — jobs entry (enabled) + rename
# ==========================================================
class TestMergeJobsAndRename:
    def test_jobs_entry_has_enabled(self):
        cfg = {"search": {"jobs": []}}
        jobs_logic.merge_job_form(
            cfg, keyword="자재", times=["09:00"], enabled=False, pattern="materials",
            drafter="", title="", weekdays=False, dataset_route="/materials",
        )
        job = cfg["search"]["jobs"][0]
        assert job["keyword"] == "자재"
        assert job["times"] == ["09:00"]
        assert job["enabled"] is False

    def test_rename_moves_collectors_and_dataset_routes(self):
        """rename: collectors·dataset_routes 구 키 → 새 키 (orphan 제거)."""
        cfg = {
            "search": {
                "jobs": [{"keyword": "OLD", "times": ["09:00"], "enabled": True}],
                "collectors": {"OLD": {"type": "binder", "box": "dept_open"}},
            },
            "api_backup": {"dataset_routes": {"OLD": "/binder"}},
        }
        jobs_logic.merge_job_form(
            cfg, keyword="NEW", times=["09:00"], enabled=True, pattern="binder",
            drafter="김지훈", title="PBHA", weekdays=True, dataset_route="/binder",
            original_keyword="OLD",
        )
        # 구 키는 사라지고 새 키로 이동
        assert "OLD" not in cfg["search"]["collectors"]
        assert "NEW" in cfg["search"]["collectors"]
        assert "OLD" not in cfg["api_backup"]["dataset_routes"]
        assert cfg["api_backup"]["dataset_routes"]["NEW"] == "/binder"

    def test_rename_replaces_old_jobs_entry_no_orphan(self):
        cfg = {
            "search": {
                "jobs": [{"keyword": "OLD", "times": ["09:00"], "enabled": True}],
            },
        }
        jobs_logic.merge_job_form(
            cfg, keyword="NEW", times=["10:00"], enabled=True, pattern="materials",
            drafter="", title="", weekdays=False, dataset_route="/materials",
            original_keyword="OLD",
        )
        kws = [j["keyword"] for j in cfg["search"]["jobs"]]
        assert "OLD" not in kws
        assert "NEW" in kws

    def test_same_keyword_overwrites_not_duplicates(self):
        cfg = {"search": {"jobs": [{"keyword": "자재", "times": ["08:00"], "enabled": True}]}}
        jobs_logic.merge_job_form(
            cfg, keyword="자재", times=["09:00"], enabled=False, pattern="materials",
            drafter="", title="", weekdays=False, dataset_route="/materials",
            original_keyword="자재",
        )
        matching = [j for j in cfg["search"]["jobs"] if j["keyword"] == "자재"]
        assert len(matching) == 1
        assert matching[0]["times"] == ["09:00"]
        assert matching[0]["enabled"] is False


# ==========================================================
# validate_form — 검증 규칙
# ==========================================================
class TestValidateForm:
    def _cfg_with_jobs(self, keywords):
        return {"search": {"jobs": [{"keyword": k, "times": ["09:00"]} for k in keywords]}}

    def test_empty_keyword_rejected(self):
        errors = jobs_logic.validate_form(
            self._cfg_with_jobs([]), "", "materials", "", "", None
        )
        assert any("키워드" in e for e in errors)

    def test_duplicate_keyword_rejected(self):
        errors = jobs_logic.validate_form(
            self._cfg_with_jobs(["자재"]), "자재", "materials", "", "", None
        )
        assert any("이미" in e for e in errors)

    def test_duplicate_keyword_allows_self_when_editing(self):
        """편집 중인 자기 자신(original_keyword)은 중복에서 제외."""
        errors = jobs_logic.validate_form(
            self._cfg_with_jobs(["자재"]), "자재", "materials", "", "", "자재"
        )
        assert not any("이미" in e for e in errors)

    def test_binder_requires_drafter_or_title(self):
        """binder + 기안자·문서제목 둘 다 비면 거부."""
        errors = jobs_logic.validate_form(
            self._cfg_with_jobs([]), "PBHA", "binder", "", "", None
        )
        assert any("binder" in e for e in errors)

    def test_binder_ok_with_drafter(self):
        errors = jobs_logic.validate_form(
            self._cfg_with_jobs([]), "PBHA", "binder", "김지훈", "", None
        )
        assert not errors

    def test_binder_ok_with_title(self):
        errors = jobs_logic.validate_form(
            self._cfg_with_jobs([]), "PBHA", "binder", "", "PBHA", None
        )
        assert not errors

    def test_materials_needs_neither_drafter_nor_title(self):
        errors = jobs_logic.validate_form(
            self._cfg_with_jobs([]), "자재", "materials", "", "", None
        )
        assert not errors
