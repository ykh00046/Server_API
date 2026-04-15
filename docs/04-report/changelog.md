# 변경 사항 기록

## [2026-03-31] - Server_API 인수 문서 및 보드 링크 정합화

### 추가된 문서

- `docs/01-plan/features/server-api-intake.plan.md`
  - Server_API 인수 관점의 기준 계획 추가
  - 현재 문서 구조와 보드 연계 범위 명시

- `docs/01-plan/features/server-api-consistency-and-smoke.plan.md`
  - 문서 정합성 보정과 최소 스모크 검증 범위를 별도 계획으로 정리
  - `requirements-smoke.txt`, `tools/smoke_api.sh`, 스모크 리포트와 연결

### 변경된 사항

- `README.md`
  - 문서 섹션에 현행 계획/리포트 링크 추가
  - `docs/01-plan` 및 `docs/04-report` 중심 구조로 갱신
  - 운영 매뉴얼 링크 추가, 기존 `docs/plans` 문서는 레거시 로드맵으로 구분

- `docs/04-report/server-api-smoke-2026-03-31.report.md`
  - 보드 이슈의 구 경로 표기를 저장소 현행 계획 문서 경로로 대응시켜 후속 참조 혼선을 제거

### 관련 리포트

- `docs/04-report/server-api-smoke-2026-03-31.report.md`

## [2026-02-26] - 세션 완료: AI 도구 추가, DB 자동화, 문서화 3종

### 추가된 기능

**AI 도구 (2개)**:
- `compare_periods()`: 두 기간 생산량 비교 (전월 대비, 올해 vs 작년 등)
  - 입력: period1_from, period1_to, period2_from, period2_to, item_code
  - 반환: total_qty, avg_qty, change_rate_pct, direction 등
  - 자동 라우팅: Archive/Live DB 기간 기반 선택
  - 트리거: "비교", "대비", "이번 달 vs 저번 달"

- `get_item_history()`: 특정 품목 최근 생산 이력 조회
  - 입력: item_code, limit (기본 10, 최대 50)
  - Archive + Live UNION ALL, 최신순 정렬
  - 트리거: "최근 이력", "마지막 N건", "언제 만들었어"

**DB 자동화 (1개)**:
- `run_analyze()`: DB 통계 갱신 함수
  - SQLite ANALYZE production_records 실행
  - Live + Archive DB 양쪽 지원
  - Watcher에 24시간 주기로 통합

**문서 (3개)**:
- `docs/plans/v8_consolidated_roadmap.md`: v6+v7 통합 로드맵
  - 완료 항목: 29개 (모든 파일 위치 명시)
  - 미완료: 9개 (우선순위 정의)
  - v8 기준 아키텍처 다이어그램

- `docs/specs/api_guide.md`: API 개발자 가이드 (630줄)
  - 9개 엔드포인트 + 7개 AI 도구 상세 설명
  - curl/Python 예제, Cursor Pagination 코드
  - 멀티턴 세션 + Rate Limiting 대응 방법
  - 에러 코드표

- `docs/specs/operations_manual.md`: 운영 가이드 (686줄)
  - 서버 시작/중지, 헬스체크, 로그 관리
  - DB 백업/복구 절차
  - 장애 대응 6가지 (DB 연결, API 다운, AI Chat, Dashboard 느림, 인덱스, 디스크)
  - Archive 전환 10단계 절차
  - 매일/주/월/년 정기 점검 체크리스트

### 변경된 사항

**api/tools.py**:
- `compare_periods()` 함수 추가 (95줄)
- `get_item_history()` 함수 추가 (67줄)
- 두 함수 모두 Type hints, docstring, 에러 처리 완비

**api/chat.py**:
- 두 신규 도구 import 추가
- tools 목록에 compare_periods, get_item_history 등록
- 시스템 인스트럭션 규칙 7, 8 추가 (각 도구 사용 조건)

**shared/db_maintenance.py** (신규):
- `run_analyze(db_path: str) -> dict` 함수
- ANALYZE production_records 실행
- 반환: success, duration_ms, error, analyzed_at

**tools/watcher.py**:
- `ANALYZE_INTERVAL = 86400` 상수 추가 (24시간)
- 상태 파일 필드 추가: `last_analyze_ts`
- `run_check()` 함수에 ANALYZE 로직 통합
  - Live DB + Archive DB 양쪽 ANALYZE 실행
  - 실행 시간 및 결과 로깅

**README.md**:
- 포트 정보 수정 (DASHBOARD_PORT: 8501 → 8502)
- API 엔드포인트 전체 갱신 (9개 명시)
- AI 도구 7개 목록 및 트리거 예시 추가
- DB 구조 섹션 추가 (Archive/Live, 인덱스 3개, 백업 정책)
- 프로젝트 구조 갱신 (shared 8개 모듈, tools/ 디렉토리)
- 테스트 케이스 수 갱신 (103개)
- 버전 이력 정리 (v1~v8)

### 수정된 버그

**tools/watcher.py**:
1. `check_and_heal_indexes(is_archive=True)`: 존재하지 않는 파라미터 제거
   - 함수 호출 시 is_archive 인자 제거

2. `LOGS_DIR` import 오류 수정
   - `from shared.config import LOGS_DIR` 추가
   - 기존 import 중복 제거

### 코드 통계

| 항목 | 수치 |
|------|:----:|
| 총 커밋 | 5개 |
| 변경 파일 | 8개 |
| 추가 코드 | +1,952줄 |
| 신규 함수 | 3개 |
| 신규 문서 | 3개 |
| 버그 수정 | 2개 |
| Design Match | 98% |

### Git Commits

```
c6f1133 - feat: AI 도구 2개 추가 및 DB ANALYZE 자동화
de689a5 - docs: v6+v7 통합 로드맵 v8 작성
764f34d - docs: README.md 현행화 (v8 기준)
a2951d4 - docs: API 사용 가이드 작성
147145a - docs: 운영 매뉴얼 작성
```

### 완료 보고서
- `docs/04-report/production-data-hub-2026-02-26-session.report.md`

---

## [2026-02-25] - 코드 품질 개선 완료

### 추가된 기능
- SQL 인젝션 방어 기능 (`escape_like_wildcards`, `validate_db_path` 함수)
- 스레드 안전성 개선 (락 추가로 동기화)
- 성능 최적화 (캐시 시스템 개선)
- 유틸리티 모듈 (`shared/validators.py`, `shared/path_setup.py`)

### 변경된 사항
- API 키 지연 초기화 패턴 적용
- 세션 저장소 메모리 관리 개선
- atexit 핸들러로 자원 정리
- LIKE 패턴 인젝션 방지
- 포털 설정 대화상자 패스워드 난독화

### 수정된 버그
- 세션 저장소 메모리 누수 문제 해결
- 스레드 경합 조건 수정
- 자원 정리 문제 개선
- 경로 검증 강화
- SQL 키워드 필터링 강화

---

## [2026-02-20] - 로드맵 재정리 및 첫 개선 보고서

### 추가된 기능
- v6 개선 로드맵 분석 완료
- v7 성능 개선 로드맵 분석 완료
- 완료 항목 29개 확인
- 미구현 항목 3개 우선순위 결정

### 변경된 사항
- 첫 PDCA 완료 보고서 작성
  - `docs/04-report/roadmap-consolidation-2026-02-26.report.md`

---

## [2026-02-19] - 초기 분석 시작

- 코드 품질 분석 수행 (23개 문제 식별)
- Critical: 5개, High: 6개, Medium: 6개, Low: 6개
- 우선순위별 개선 계획 수립
