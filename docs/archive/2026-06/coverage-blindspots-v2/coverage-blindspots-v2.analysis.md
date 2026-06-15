# coverage-blindspots-v2 — Gap Analysis

> **Cycle**: coverage-blindspots-v2
> **PDCA Phase**: Check
> **Date**: 2026-06-15
> **Plan**: [[coverage-blindspots-v2.plan]]
> **Match Rate**: **100%** (AC 7/7)

## AC별 검증

| # | Criterion | 실측 결과 | 판정 |
|---|-----------|-----------|:----:|
| AC1 | test_kpi_cards 5함수 ≥8 케이스 green | 9 케이스 green(calculate_kpis×4, sparkline×3, format/has_signal×2) | ✅ |
| AC2 | test_watcher_state load/save ≥4 케이스 green | 4 케이스 green(missing/corrupt/roundtrip/valid-json) | ✅ |
| AC3 | kpi_cards.py 측정 포함, 파일 ≥75% | **88%**(51 stmt, 7 miss = 방어 분기 74-75 + render_kpi_cards 렌더부 170-190) | ✅ |
| AC4 | watcher.py source 미포함(floor 안전) | cov-report에 watcher.py 부재(test-only) | ✅ |
| AC5 | measured ≥ 72 | **76.30%**(75→76, floor 72 통과) | ✅ |
| AC6 | 389 green + ruff + CI | 389 passed(376+13), ruff clean, CI(아래) | ✅ |
| AC7 | match rate ≥ 90% | 100% | ✅ |

## 처리 내역

- **kpi_cards.py**: 순수함수 5개 단위 테스트(importlib 격리 — streamlit import는 되나 순수함수는 st 미호출). omit 화이트리스트에서 제거 → 측정 88%. render_kpi_cards 렌더부(170-190)와 방어 분기(74-75, item_totals 빈데 df 비어있지 않은 경계)만 미커버.
- **watcher.py**: load_state(파일 없음/손상 JSON→default), save_state(roundtrip) 테스트. STATE_FILE/DATABASE_DIR monkeypatch(tmp). **source 미추가** — run_check(DB+FS+time IO)가 미측정이라 통째 측정 시 floor 붕괴하므로 test-only.

## 설계 정합

- v1/expansion 원칙 계승: "측정 가치 있는 순수 로직만, 렌더/IO 제외". kpi_cards는 측정, watcher run_check는 비측정.
- floor 72 유지(측정 추가분으로 76% 됐으나 인플레 금지 — Plan Non-Goal 준수).
- STATE_FILE이 모듈 전역 런타임 조회라 monkeypatch 정상 동작([[feedback_default_shadowing]] 확인 — 기본인자 캡처 아님).

## 권장 조치

없음 — **100% → Report.** 후속: dashboard-apptest-v1(렌더 테스트), run_check 리팩터+측정.
