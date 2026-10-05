# run-trigger-global-guard-v1 — 수동 실행 트리거의 전역(교차 데이터셋) 동시 실행 가드

- 상태: 완료 (2026-10-05)
- 브랜치: `feat/run-trigger-global-guard`
- 출처: roadmap-2026h2 B-9 (v0.7 신설). 사고 기록은 Dashboard-Raw_material 메모리
  `feedback_ops_server_readonly`(2026-08-24)

## 배경 / 문제

`POST /{dataset}/run`의 동시 실행 가드(`api/materials/automation.py`)는 `_trigger_lock` +
**해당 데이터셋의 runs 테이블**에서 `status='running'`인 automation 행을 찾는 방식이었다. 자재
(`material_runs`)와 바인더(`binder_runs`)는 테이블이 다르므로 자재가 실행 중이어도 바인더 트리거는
통과했다. 그런데 두 봇 실행은 **같은 Selenium 포털 세션을 공유**한다 — 2026-08-24 "확인 목적
POST"가 자재+바인더를 동시에 기동시켜 포털 세션이 꼬인 사고가 정확히 이 구멍이다. 이후 Dashboard
`/data-hub` 프록시가 교차 차단을 넣었지만, `/run`을 직접 호출하는 경로는 여전히 무방비였다.

## 설계

| 위치 | 변경 |
|---|---|
| `api/materials/runs.py` | `reap_stale_running_all()` — 등록된 모든 데이터셋의 고아 running 행 정리(합계 반환). `active_automation_dataset() -> Dataset \| None` — 어느 데이터셋이든 running automation이 있으면 그 Dataset. 기존 `has_active_automation(runs_table)`·`reap_stale_running(runs_table)`은 유지(단일 테이블 프리미티브) |
| `api/materials/automation.py` | 락 안에서 `reap_stale_running_all()` → `active_automation_dataset()`로 교체. 409 메시지에 **실행 중인 쪽의 title**("이미 실행 중인 자동화가 있습니다 (Materials). 크롤러는 포털 세션을 공유하므로…")을 넣어 호출자가 어느 쪽을 기다리는지 알 수 있게 함 |
| `tests/test_materials.py` | `test_cross_dataset_run_blocked`(자재 running → `/binder/run` 409, detail에 Materials, 바인더 테이블에는 행 미생성), `test_cross_dataset_stale_reaped`(바인더 고아 행이 자재 트리거 때 함께 failed 처리) — **되돌려 실패 확인**: automation.py를 stash한 상태에서 2건 모두 FAILED |
| `docs/specs/operations_manual.md` | 비활성 상태코드 409→503 오기 정정(B-5 이후 503), "이미 실행 중" 행에 교차 차단·고아 정리 설명 |

데이터셋이 늘어나도(B-4 체크리스트) `all_datasets()`를 돌므로 가드는 자동 확장된다.

## 커버하지 않는 경로 (의도적)

- **매니저 "Run Now"**: 서버 `/run`을 거치지 않고 봇 `main.py --auto`를 직접 spawn한다(`manager.py
  run_portal_now`). 운용 PC 앞에 앉은 사람이 누르는 버튼이라 서버 가드 밖. 봇 자체의 스케줄 실행과의
  충돌도 마찬가지로 봇 측 책임 — 봇에 실행 락이 없다는 점(2026-10-05 grep)은 C-5(봇-서버 계약) 때
  봇 저장소 과제로 넘긴다.
- Dashboard `/data-hub` 프록시의 교차 차단은 그대로 두는 것이 맞다(서버 왕복 없이 친절 메시지).
  서버 가드는 그 뒤의 마지막 방어선.

## 검증

- 488 tests · ruff 그린 · 커버리지 93%(floor 88).
- 새 테스트 2건은 가드 교체 전 코드에서 실패함을 확인(되돌려 실패시켜 증명).
