# Server_API 1차 스모크 및 정합성 검증 리포트

작성일: 2026-03-31

## 요약

- 현재 heartbeat 환경에서는 `python3`만 존재하고 핵심 런타임 의존성(`fastapi`, `uvicorn`, `streamlit`, `orjson`, `cachetools`, `google.genai`)이 설치되어 있지 않아 API 프로세스 기동 및 pytest 실행을 재현할 수 없었다.
- 저장소 문서와 코드 시그니처를 대조한 결과, 실행 문서 일부가 현재 코드 기준과 어긋나 있었다.
- 이 heartbeat에서는 스모크 전용 의존성 파일(`requirements-smoke.txt`)과 실행 스크립트(`tools/smoke_api.sh`)를 추가해 최소 검증 경로를 고정했다.
- 대시보드 기본 포트는 문서, `.env.example`, 코드 기본값을 모두 `8502`로 정렬했다.
- 다만 WSL에서 `/mnt/c` 마운트 경로에 직접 venv를 만들면 `pip` self-upgrade 또는 대규모 설치가 비정상적으로 오래 걸릴 수 있어, 설치 단계 자체가 운영 리스크로 확인됐다.

## 확인한 내용

### 환경/실행

- `python3 --version`: `Python 3.12.3`
- `python3 -m pytest -q tests`: 실패 (`No module named pytest`)
- `api.main` import: 실패 (`No module named fastapi`)
- `tools/smoke_api.sh`: 추가 완료
- `SMOKE_INSTALL=1 tools/smoke_api.sh`: `/mnt/c` 마운트 경로 venv 설치가 장시간 정체되어 heartbeat 안에서 완료 확인 실패

### 코드 기준 엔드포인트

- `GET /`
- `GET /healthz`
- `GET /healthz/ai`
- `GET /records`
- `GET /records/{item_code}`
- `GET /items`
- `GET /summary/monthly_total`
- `GET /summary/by_item`
- `GET /summary/monthly_by_item`
- `POST /chat/`

## 문서 정합성 결과

### 수정 완료

- `README.md`
  - 저장소 준비 예시를 현재 프로젝트명 기준으로 일반화
  - `GET /records` 파라미터에서 `q`, `offset` 누락 보완
  - `limit` 기본값을 코드 기준 `1000`으로 수정
  - `next_cursor`, `has_more`, `count` 응답 필드 명시
  - 최소 스모크 검증 절차(`tools/smoke_api.sh`) 추가
- `docs/specs/operations_manual.md`
  - 고정 개인 경로를 프로젝트 루트 기준 표기로 교체
  - 작업 스케줄러 예시를 환경 독립적인 placeholder로 정리
- `shared/config.py`
  - `DASHBOARD_PORT` 기본값을 `8502`로 조정해 문서 및 `.env.example`과 일치시킴
- `requirements-smoke.txt`
  - API/pytest/import 검증에 필요한 최소 의존성만 분리
- `tools/smoke_api.sh`
  - `pytest` → `api.main` import → 선택적 `/healthz` 순서의 재현 가능한 스모크 실행 스크립트 추가

### 추가 확인 필요

- 보드 이슈에서 언급한 계획 항목은 저장소에서는 다음 현행 경로로 정리되어 있다.
  - `plans/2026-03-31-server-api-intake.md` -> `docs/01-plan/features/server-api-intake.plan.md`
  - `plans/2026-03-31-server-api-consistency-and-smoke.md` -> `docs/01-plan/features/server-api-consistency-and-smoke.plan.md`
- Windows 운영 예시(`python`, 경로 placeholder, 작업 스케줄러`)가 실제 배포 표준과 일치하는지는 별도 실행 환경에서 재검증이 필요하다.

## 리스크

- 현재 heartbeat 환경에서는 설치된 의존성이 없어 "문서대로 실행 가능" 여부를 검증하지 못했다.
- 테스트와 실제 서버 기동을 자동으로 재현할 수 있는 명령 세트가 문서에 고정돼 있지 않아 환경 의존성이 크다.
- `/mnt/c/X/Server_API`처럼 WSL 마운트 경로에 직접 venv를 둘 경우 패키지 설치가 매우 느리거나 `pip` 자체 갱신이 깨질 수 있다. 스모크는 전체 `requirements.txt`보다 `requirements-smoke.txt`로 좁혀 수행하는 편이 안전하다.
- 기본 포트 정렬은 끝냈지만, 실제 운영 환경이 `8502`를 기준으로 방화벽/바로가기/작업 스케줄러를 사용 중인지 별도 런타임 검증이 필요하다.

## 권장 후속 작업

1. 재현 가능한 실행 환경(venv 또는 CI smoke job)을 정의하고 `pytest` + `api.main` import를 자동 검증한다.
2. 운영 문서의 경로 표기를 고정 개인 경로 대신 프로젝트 루트 기준 또는 환경변수 기준으로 통일한다.
3. 보드 이슈 설명에 연결된 계획 문서의 실제 저장 위치를 정리하거나, 문서 링크를 현행 경로로 갱신한다.
4. 가능하면 Linux 네이티브 경로(예: `~/work/...`) 또는 CI 워크스페이스에서 `SMOKE_INSTALL=1 tools/smoke_api.sh`를 다시 실행해 설치 병목이 `/mnt/c` 특이점인지 분리 확인한다.
