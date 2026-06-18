# anomaly-detection-v1 Completion Report

> **Status**: Complete
>
> **Project**: Production Data Hub
> **Feature**: 생산 이상 탐지 + 능동 알림 (Anomaly Detection + Proactive Alerting)
> **Author**: Claude / bkit:pdca
> **Completion Date**: 2026-06-19
> **PDCA Cycle**: anomaly-detection-v1 (Plan→Design→Do→Check→Act→QA→Report)
> **Match Rate**: 96% → 실질 100% (Act 보정 후)

---

## 1. Summary

| Item | Content |
|------|---------|
| Feature | 생산 데이터 규칙 기반 이상 탐지 + 기존 webhook(`emit_event`) 능동 알림 |
| Problem | 모든 관측이 pull(수동 조회)이라 급감·장시간 미생산 등 이상을 늦게 발견 |
| Solution | read-only 주기 스캔 → 순수 규칙 판정 → 쿨다운 dedup → 신규 이상만 webhook 발행 |
| Core Value | 관측을 pull→push로 전환, 발견 시간(MTTD) 단축. 전달/재시도/관리 UI는 webhook 재사용으로 신규 코드 최소화 |
| Duration | 1 Session |

### 결과 요약

```
┌─────────────────────────────────────────────┐
│  Overall Completion: 100%                    │
│  Tests: 567 passed (anomaly 신규 29 포함)     │
│  Ruff:  All checks passed                    │
│  Match Rate: 96% → 100% (Act)                │
└─────────────────────────────────────────────┘
```

## 2. Related Documents

| Phase | Document |
|-------|----------|
| Plan | `docs/01-plan/features/anomaly-detection-v1.plan.md` |
| Design | `docs/02-design/features/anomaly-detection-v1.design.md` |
| Check | `docs/03-analysis/anomaly-detection-v1.analysis.md` |
| Report | 본 문서 |

## 3. Delivered

### 3.1 신규 모듈 (`api/anomaly/`)

| 파일 | 역할 |
|------|------|
| `schemas.py` | `Finding` dataclass, kind→event_type 매핑, severity 순서 |
| `rules.py` | 순수 탐지 함수(I/O 없음): `detect_volume_anomalies`, `detect_stale_items` |
| `store_state.py` | 쿨다운 상태 load/save/filter_new/mark_emitted/prune |
| `detector.py` | 조율: read-only 쿼리 → 규칙 → dedup → `emit_event` |
| `__init__.py` | 공개 API 재노출 + 이벤트 타입 선등록(관리 UI 노출) |

### 3.2 통합 지점

| 변경 | 내용 |
|------|------|
| `api/routers/anomaly.py` | `GET /anomaly/scan`(기본 dry-run), `GET /anomaly/rules` |
| `api/main.py` | 라우터 등록 |
| `shared/config.py` | `ANOMALY_*` 9개 노브 |
| `tools/anomaly_watch.py` | 스케줄 러너(단발/`--dry-run`/`--daemon`/`--interval`), watcher.py 패턴 |
| `.env.example` / `.gitignore` | 노브 문서화 + 상태파일 무시 |

### 3.3 탐지 규칙 (기본값)

| 규칙 | 조건 | event_type |
|------|------|------------|
| 급감 | 직전 완료일 양품 ≤ 후행 14일 평균 대비 −50% | `production.anomaly.volume_drop` |
| 급증 | 직전 완료일 양품 ≥ 평균 대비 +100% | `production.anomaly.volume_spike` |
| 장시간 미생산 | 활성 품목이 7일 이상 미생산 | `production.anomaly.stale_item` |

- 당일(미마감) 데이터는 제외 → 거짓 급감 방지.
- 기준선 < `MIN_BASELINE_QTY`면 급감/급증 skip(0 나눗셈·노이즈 방지).
- 동일 이상은 24h 쿨다운 내 재발행 안 함.

## 4. 재사용한 기존 인프라

| 인프라 | 재사용 방식 |
|--------|------------|
| webhook `emit_event` | 발행 한 줄 위임 — 큐·backoff·dead-letter·관리 UI·bulk retry 무변경 활용 |
| `DBRouter.get_connection(read_only=True)` | 운영 DB 무변경 읽기 |
| `tools/watcher.py` 패턴 | 상태파일 + 단발/데몬 실행 모델 |
| conftest `live_db` 픽스처 | API 테스트 DB 라우팅 |

## 5. Verification

| 검증 | 결과 |
|------|------|
| 단위(rules 경계값) | 14 케이스 통과 |
| 단위(store_state 쿨다운/손상복구) | 8 케이스 통과 |
| 통합(detector, 합성 DB) | 5 케이스 통과(급감+stale 동시, 쿨다운 재발행 0, dry-run 비기록) |
| API(scan/rules) | 3 케이스 통과 |
| 전체 회귀 | pytest 567 passed |
| 정적분석 | ruff All checks passed |
| 런타임 스모크 | `anomaly_watch.py --dry-run` 정상(실 DB findings=0) |

## 6. 운영 방법

```bash
# 1회 스캔(발행)
python tools/anomaly_watch.py
# 미발행 미리보기
python tools/anomaly_watch.py --dry-run
# 데몬(기본 1시간 주기)
python tools/anomaly_watch.py --daemon
# API 미리보기 / 임계치 확인
GET /anomaly/scan        # dry-run
GET /anomaly/rules
```
알림 수신: `/notifications/webhooks`에 `production.anomaly.*` 이벤트 구독 webhook 등록.

## 7. Lessons / Try (Next)

- **Keep(좋았던 점)**: 순수 규칙/조율 분리로 핵심 로직 단위 테스트가 쉬웠고, webhook 재사용으로 신규 코드가 "규칙+스케줄러"에 한정됨.
- **Try(후속)**:
  - `anomaly-detection-v2`: 계절성/추세 기반 통계 탐지(STL·이동표준편차).
  - 품목별 개별 임계치 + 대시보드 이상 타임라인 시각화.
  - 운영 데이터로 기본 임계치 튜닝(현 값은 보수적 시작점).

## 8. Commit Plan (논리 계층별 분할)

1. `feat(config): anomaly-detection-v1 환경 노브 + .env.example/.gitignore`
2. `feat(anomaly): 규칙 기반 탐지 코어(schemas/rules/store_state/detector)`
3. `feat(api): /anomaly 라우터 + main 등록 + 스케줄 러너`
4. `test(anomaly): rules/state/detector/api 단위·통합 테스트`
5. `docs(pdca): anomaly-detection-v1 plan/design/analysis/report`

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-06-19 | Claude / bkit:pdca | 최초 작성 (사이클 완료) |
