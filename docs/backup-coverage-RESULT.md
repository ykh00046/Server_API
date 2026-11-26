# 백업 대상 확대 결과 (fix/backup-coverage, 2026-11-26)

## 1. 확인한 것

앱이 운영에서 쓰는 SQLite 파일은 5개다. 경로는 모두 `shared/config.py`의 상수이고 `DATABASE_DIR = BASE_DIR / "database"`(config.py:25) 아래에 있다.

- 생산 Live DB: `DB_FILE = DATABASE_DIR / "production_analysis.db"` (shared/config.py:28). `shared/database.py:161-167`에서 URI 모드로 연다.
- 2025 Archive DB: `ARCHIVE_DB_FILE = DATABASE_DIR / "archive_2025.db"` (shared/config.py:29). `shared/database.py:174`, `shared/_db_attach.py:44`에서 ATTACH한다.
- 알림 DB: `NOTIFICATIONS_DB_FILE = DATABASE_DIR / "notifications.db"` (shared/config.py:127). `api/notifications/_store_connection.py:27`에서 호출 시점에 경로를 읽고 `:44`에서 연결, `:47`에서 WAL 모드로 바꾼다.
- 자재 DB: `MATERIALS_DB_FILE = DATABASE_DIR / "materials.db"` (shared/config.py:138). `api/materials/store.py:49`(경로), `:86`(연결), `:89`(WAL). 바인더 데이터(`binder_requests`, `binder_runs`, api/materials/datasets.py:51-52)도 같은 파일의 표다.
- 이상 탐지 DB: `ANOMALY_DB_FILE = DATABASE_DIR / "anomaly.db"` (shared/config.py:200). `api/anomaly/store_findings.py:39`(경로), `:60`(연결), `:63`(WAL).

SQLite가 아닌 상태 파일 `ANOMALY_STATE_FILE = DATABASE_DIR / ".anomaly_state.json"`(shared/config.py:197)도 있다. 이번 작업 범위(SQLite)가 아니라 백업 대상에 넣지 않았다.

## 2. 변경 전 백업 범위

- 백업됨: `production_analysis.db`(접두어 `production`, 30개 보존), `archive_2025.db`(접두어 `archive_2025`, 12개 보존). 변경 전 `tools/backup_db.py`의 `main()`이 `run_backup`을 이 두 개에만 호출했다.
- 백업 안 됨: `materials.db`, `notifications.db`, `anomaly.db`. 감사 문서의 "공백 1" 주장은 사실이다.
- `ARCHIVE_DB_WHITELIST`(shared/config.py:155-175, 환경변수 `ARCHIVE_DB_WHITELIST`) 로 추가 아카이브 파일을 지정할 수 있지만 그런 파일도 백업 도구에 들어 있지 않다. 운영 PC에서 이 환경변수를 쓰는지는 확인하지 못했다(.env를 열지 않았음). 이번 변경에서도 다루지 않았다.
- 백업 도구 테스트는 없었다(tests/ 아래에 backup_db를 참조하는 파일이 없었음).

## 3. 백업 예약 여부

- 백업 도구를 예약 실행하는 곳은 없다.
- `deploy-ops/ops-install.ps1`이 등록하는 예약 작업은 4개(ProductionHubApi, ProductionHubPortal, ProductionHubWatcher, ProductionHubUpdate)이고, 이 중 백업 도구를 부르는 작업은 없다(ops-install.ps1:4-8, 72-95).
- `deploy-ops/ops_launch.py`의 역할은 portal, portal-once, watcher뿐이다(ops_launch.py:30-34). watcher는 `tools/watcher.py --daemon --interval 3600`이고 인덱스 점검만 하며 백업은 하지 않는다.
- `manager.py`, `tools/watcher.py`, `tools/db_watcher.py`, `install.bat`, `update.bat`, `scripts/`에도 backup_db 호출이 없다.
- 도구 docstring의 "Can be scheduled via Windows Task Scheduler"는 가능하다는 설명일 뿐이다. README의 `backups/ # 자동 백업` 문구는 사실과 달라서 고쳤다(5절).
- 따라서 운영 PC에서 누군가 손으로 작업을 따로 등록하지 않았다면, 현재 5개 DB 모두 정기 백업이 없다. 운영 PC는 확인하지 않았다(접속 금지 조건).
- 지시에 따라 예약은 추가하지 않았다.

## 4. 바꾼 것 (`tools/backup_db.py`)

- `shared.config`에서 `MATERIALS_DB_FILE`, `NOTIFICATIONS_DB_FILE`, `ANOMALY_DB_FILE`을 가져온다. 새 절대 경로는 넣지 않았다.
- `APP_BACKUP_RETENTION = 30`을 추가했다(앱 DB마다 30개 보존).
- `_app_db_targets()`를 추가했다. (이름, 경로, 접두어, 보존 개수)를 돌려주고, 접두어는 `materials`, `notifications`, `anomaly`다. 호출할 때 모듈 전역을 읽으므로 테스트에서 경로를 바꿔 끼울 수 있다.
- `_run_app_backups()`를 추가했다. 앱 DB마다 기존 `run_backup`(mtime 안정화, SQLite backup API, quick_check 검증, 검증 실패 시 삭제, 보존 정리)을 그대로 쓴다. 파일이 없으면 `Skipping <이름> - not present on this machine: <경로>`를 남기고 건너뛴 것으로 센다. 실패로 세지 않는다.
- `main()`
  - 인자 없이 실행하면 기존 두 DB 다음에 앱 DB 3개를 백업한다.
  - `--live`와 `--archive`는 범위를 바꾸지 않았다. 각각 production만, archive만 백업한다.
  - `--cleanup`은 앱 DB 접두어 3개의 정리도 한다.
  - 요약 줄은 `Backup Summary: N success, M failed, K skipped`로 바꿨다. 끝에 skipped가 붙었다.
- 기존 두 DB의 접두어(`production`, `archive_2025`), 파일 이름 형식(`<접두어>_YYYYMMDD_HHMMSS.db`), 보존 개수(30, 12), 정리용 glob은 바꾸지 않았다. 지금 있는 백업 파일도 계속 정리 대상에 맞는다.
- 판단해서 정한 것: 없는 파일을 건너뛰는 규칙은 새 앱 DB 3개에만 적용했다. production이나 archive_2025 파일이 없으면 지금처럼 실패로 세고 종료 코드 1을 낸다. 운영 DB가 사라진 상황을 조용히 넘기지 않기 위해서다. 기존 두 DB에도 건너뛰기를 적용하려면 따로 결정해야 한다.
- 접두어끼리 겹치지 않는다. 앞의 `archive_2025_*` 기존 파일을 다른 접두어의 glob이 잡지 않는다는 점은 테스트로 확인했다.
- 문서: README.md의 database 구조 설명(`backups/` 줄)과 "DB 백업" 사용 예 주석을 새 범위에 맞게 고쳤다.

## 5. 추가한 테스트

- 파일: `tests/test_backup_db.py`, 11개 테스트.
- 모든 DB 경로(5개)와 `BACKUP_DIR`은 monkeypatch로 `tmp_path` 아래를 가리킨다. `wait_for_stabilization`은 sleep만 하므로 True를 돌려주게 바꿨다. sqlite backup API와 quick_check는 실제로 돈다.
- 검사하는 것
  - 백업 성공 시 사본이 quick_check를 통과하고 데이터가 같다.
  - 원본이 없으면 `run_backup`이 False를 돌려준다.
  - 검증에 실패한 백업(SQLite가 아닌 바이트)은 지워진다.
  - 보존 정리가 같은 접두어에서 가장 오래된 것만 지우고, 더 오래된 다른 접두어 파일은 남긴다.
  - 보존 개수 이내이면 아무것도 지우지 않는다.
  - 인자 없는 실행이 5개 DB를 모두 백업하고, 각 사본이 검증을 통과한다.
  - 앱 DB 2개가 없을 때 건너뛰기 로그가 남고, 요약이 `3 success, 0 failed, 2 skipped`이며 종료 코드는 0이다.
  - production이 없으면 종료 코드 1이다(기존 동작 유지).
  - `--live`는 production만 백업한다.
  - 앱 DB 백업이 실패하면 종료 코드 1이다.
  - `--cleanup`이 앱 접두어도 정리한다.
- 실행한 명령(작업트리에서, 본 체크아웃의 문서화된 py3.12 venv 사용)
  - `C:/X/Server_API/.venv/Scripts/python.exe -m pytest tests/test_backup_db.py -q -p no:cacheprovider` → `11 passed in 0.40s`
  - `C:/X/Server_API/.venv/Scripts/python.exe -m ruff check tools/backup_db.py tests/test_backup_db.py` → `All checks passed!`
- 작업트리의 `tools/backup_db.py`가 import되는 것을 `__file__`로 확인했다. 작업트리에는 `database/` 폴더와 `.env`가 없어 실제 데이터에 닿을 경로가 없다.

## 6. 실행하거나 확인하지 못한 것

- 전체 테스트(`pytest tests/`)는 돌리지 않았다. 지시대로 새 파일만 돌렸다. 기존 테스트 중 backup_db를 import하는 파일은 없다.
- CI 커버리지 floor는 확인하지 않았다. 커버리지 측정 대상은 `api`, `shared`뿐이라(pyproject.toml `[tool.coverage.run] source`) `tools/` 변경은 floor에 영향이 없다.
- 운영 PC의 실제 DB 크기, WAL 상태, 손으로 등록한 예약 작업 유무, `ARCHIVE_DB_WHITELIST` 설정은 확인하지 못했다.
- 실제 운영 DB를 대상으로 도구를 실행하지 않았다.

## 7. 위험

- 앱 DB 3개는 WAL 모드다. 백업은 원본을 `mode=ro`로 열어 backup API로 복사하므로 WAL 내용까지 일관되게 복사된다. 다만 SQLite 규칙상, 읽기 전용으로 여는 WAL DB는 `-shm` 파일이 있거나 폴더에 쓸 수 있어야 한다. 운영 PC에서 실행 계정에 database 폴더 쓰기 권한이 없으면 열기가 실패하고, 그 DB는 failed로 집계된다.
- `wait_for_stabilization`은 본 파일의 mtime과 크기만 본다. WAL DB는 쓰기가 `-wal` 파일에 쌓이므로 안정화 확인이 사실상 바로 통과한다. backup API가 일관된 스냅샷을 만들므로 손상 위험은 낮다.
- 인자 없는 실행이 하는 일이 늘었다. 백업 3개가 추가되어 디스크 사용량과 실행 시간이 늘고, 앱 DB 하나가 실패하면 종료 코드도 1이 된다. 이 도구의 종료 코드로 판정하는 외부 스크립트는 저장소에서 찾지 못했다.
- 백업 폴더가 운영 DB와 같은 디스크(`database/backups`)에 있다. 디스크 장애에는 대비가 되지 않는다(기존과 같음).

## 8. 운영에 반영하려면 운영자가 할 일 (하지 않았음)

- 이 브랜치를 검토하고 main에 병합한 뒤 push한다. push하면 ProductionHubUpdate가 10분 안에 운영 PC에 배포한다. 이 작업에서는 push하지 않았다.
- 배포만으로는 백업이 돌지 않는다. 예약 작업이 없기 때문이다. 정기 백업을 원하면 운영 PC에 예약 작업을 따로 등록하는 결정과 작업이 필요하다. 예를 들어 하루 1회 `python tools/backup_db.py`를 실행하는 작업을 SYSTEM 계정으로 등록한다. archive는 원래 주 1회 정책이므로 `--live`와 인자 없는 실행을 나눠 예약할지도 함께 정한다.
- 등록한 뒤 처음 한 번은 손으로 실행해 `database/backups`에 5개 접두어 파일이 생기는지, 요약 줄에 failed가 0인지 확인한다.
- `ARCHIVE_DB_WHITELIST`로 추가 아카이브를 쓰고 있다면 그 파일의 백업도 따로 정한다.
