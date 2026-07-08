# anomaly-dashboard-v2 Completion Report

> **Feature**: 이상탐지 관측 UI (발행 이력 + 쿨다운 + what-if)
> **Cycle**: Plan 2026-07-07 → Report 2026-07-08 (1일)
> **Match Rate**: 96% (gap-detector, 코드 수정 0건으로 통과)
> **운영 확인**: 2026-07-08 운영 PC에서 페이지 실화면 확인 완료

## 결과 요약

로드맵(roadmap-2026h2) B-2/M3 소진. 이상탐지 v1의 push 알림에 pull 관측을
더해 루프를 닫았다 — 운영자는 이제 대시보드에서 "지금/최근 30일/왜 안
왔나/임계치를 바꾸면"에 답을 얻는다.

| 커밋 | 내용 |
|---|---|
| 07ca644 | store_findings: anomaly.db 발행 이력 영속화 (never-raise, 90일 보존) |
| 9b8903e | RuleOverrides + detector 이력 훅 (emit+overrides ValueError 심층 방어) |
| 74e4392 | GET /findings·/state·/scan what-if 확장 (POST 서명 불변) |
| 142354b | dashboard/views/anomaly.py 5섹션 + 네비 등록 |
| 05f25ea | gap 분석 96% + 설계 v0.3 소급 정정 4건(Low, 전부 문구) |

테스트 629 → **650** (신규 21: store 8, 훅/가드 4, API 6, 헬퍼 3),
전체 게이트(ruff·C901·coverage floor 88) 그린 유지.

## 핵심 설계 결정 (재사용 가치)

1. **이력은 별도 파일(anomaly.db) + fire-and-forget** — 쿨다운 state 파일은
   이력이 될 수 없음(7일 prune, 메시지 없음)을 Plan 단계에서 발견. 기록
   실패가 발행을 못 막는다는 계약(FR-6)을 모듈 내부 never-raise로 보장.
2. **what-if는 물리적으로 발행 불가** — 오버라이드 파라미터를 GET 라우트에만
   두고, run_detection이 emit+overrides를 재거부(2중), POST는 파라미터
   자체를 안 받음(3중). "미리보기가 실발행을 왜곡할 수 없다"를 구조로 증명.
3. **streamlit-free 헬퍼는 전용 모듈** — _parsing.py(AI 특성화 테스트 전용)를
   오염시키지 않고 anomaly_view_helpers.py 분리, 디스크 직접 로드 테스트.

## 남긴 것 / 후속

- 과거 이력 소급 없음(도입 시점부터 누적) — 의도된 제약.
- 오탐 데이터가 쌓이면 roadmap B-6(품목별 임계치)의 착수 근거가 된다.
- 운영 배포: update + 매니저 재시작만(신규 의존성/마이그레이션 없음),
  anomaly.db는 첫 발행 시 자동 생성.

## Phase 기록

Plan 6013535 → Design 46f62ea(+0.2/0.3) → Do 4커밋 → Check 05f25ea(96%)
