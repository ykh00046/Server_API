# 백업 옆 -wal/-shm 파일 누적 수정 결과 (fix/backup-sidecars, 2026-11-26)

## 1. 실제 원인

- 운영자 추측("검증 단계가 백업을 WAL 모드로 연다")은 절반만 맞다. 검증이 WAL 모드를 고른 것이 아니라, 백업 파일이 처음부터 WAL 모드로 만들어져 있었다.
- 원인 1 (백업 파일이 WAL 모드가 됨): 변경 전 `tools/backup_db.py:82`의 `source_conn.backup(backup_conn)`. SQLite backup API는 원본의 1쪽(page 1)을 그대로 복사한다. 1쪽 헤더 18·19번째 바이트가 저널 모드를 나타내는데, 앱 DB 3개(materials, notifications, anomaly)는 WAL 모드라서 이 값이 2(WAL)이다. 그래서 사본도 WAL 모드 파일이 된다. 복사 자체는 사본 연결이 원래 rollback 모드로 열려 있던 상태에서 끝나므로, 데이터는 모두 본 `.db` 파일에 들어가 있고 `-wal`은 만들어지지 않는다.
- 원인 2 (옆 파일이 생기고 안 지워짐): 변경 전 `tools/backup_db.py:122-126`의 `verify_backup`이 사본을 `mode=ro`로 연다. WAL 모드 파일을 열면 SQLite는 `-shm`(공유 메모리 색인, 32 KB)과 `-wal`을 만든다. 마지막 연결이 닫힐 때 이 둘을 지우는 일은 체크포인트를 할 수 있는 연결만 하는데, 읽기 전용 연결은 그것을 못 하므로 닫은 뒤에도 남는다. 연결은 제대로 닫히고 있었다(`conn.close()`, 131행). "연결을 안 닫아서"는 원인이 아니다.
- 원인 3 (계속 쌓임): 변경 전 `tools/backup_db.py:157`의 정리 glob이 `{prefix}_*.db`만 잡는다. `.db-wal`, `.db-shm`은 대상이 아니어서 백업이 보존 개수에서 밀려 지워져도 옆 파일은 남는다.
- production, archive_2025 원본이 WAL 모드가 아니면 그 두 접두어에는 옆 파일이 생기지 않는다. 운영 PC에서 어느 원본이 WAL인지는 확인하지 못했다. 보고된 "하루 약 10개"는 5개 DB 모두 WAL일 때(5 × 2) 숫자와 맞는다.

### 재현 방법

- 임시 폴더에 WAL 모드 SQLite DB를 만들고 쓰기 연결을 열어 둔 채(`wal_autocheckpoint=0`) 행을 넣었다. 그 다음 작업트리의 `backup_database`, `verify_backup`을 차례로 불렀다. 스크립트는 세션 스크래치 폴더에 두었고 저장소에는 넣지 않았다.
- 변경 전 결과
  - 원본 헤더 (18, 19) = (2, 2)
  - `backup_database` 직후 백업 폴더: `app_20260101_000000.db` 하나뿐. 사본 헤더 = (2, 2)
  - `verify_backup` 직후 백업 폴더: `.db` 8192 B, `.db-shm` 32768 B, `.db-wal` 0 B. 운영자가 본 크기(32 KB, 0 B)와 같다.
- 즉 옆 파일은 백업 단계가 아니라 검증 단계에서 생기고, 그 바탕은 백업 단계에서 사본이 WAL 헤더를 물려받은 것이다.

## 2. 수정 내용 (`tools/backup_db.py`)

- 백업 직후 사본 연결에서 `PRAGMA journal_mode=DELETE`를 실행한다(현재 92-96행). 돌려받은 값이 `delete`가 아니면 SQLite 오류로 처리해 백업을 실패시키고, 사본과 옆 파일을 지운다(107행). 바꾸는 대상은 새로 만든 사본뿐이다. 원본 연결은 지금처럼 `mode=ro`로만 열고 원본에는 아무것도 쓰지 않는다.
- `verify_backup`은 열기 전에 헤더를 읽어 WAL 모드 사본이면 실패로 판정한다(164행). 그래서 검증 자체가 옆 파일을 만들 수 없고, `-wal`에 기대는 사본이 검증을 통과할 수 없다.
- 검증에 실패한 사본은 `-wal`, `-shm`까지 함께 지운다(`_remove_backup_files`, 293행).
- 보존 정리(`cleanup_old_backups`)
  - 보존 개수를 넘어 `.db`를 지운 경우, 그 `.db` 삭제가 성공한 뒤에 같은 이름의 `-wal`, `-shm`도 지운다.
  - 그 다음 매번(정리할 것이 없을 때도) `_cleanup_stale_sidecars(prefix)`로 예전 실행이 남긴 옆 파일을 치운다(228행).
- 새 로그 줄은 두 가지뿐이다. `[INFO] Removed stale sidecar: <이름>`, `[WARN] Kept non-empty WAL beside backup: <이름> (<크기> bytes)`. 삭제 실패 시 기존과 같은 형식의 `[WARN] Failed to remove <이름>: <오류>`.
- 파일 이름, 접두어, 보존 개수(30/12/30), 종료 코드, 요약 줄 형식은 바꾸지 않았다.

### 백업이 완전한 이유

- backup API는 원본의 WAL에 있던 커밋 행까지 포함한 일관된 스냅샷을 사본 연결을 통해 쓴다. 사본 연결은 새 파일을 rollback 모드로 열었으므로 이 쓰기는 본 `.db`에 바로 들어간다.
- `journal_mode=DELETE` 전환은 SQLite가 먼저 WAL을 모두 체크포인트하고, 성공했을 때만 헤더를 rollback으로 바꾼 뒤 `-wal`, `-shm`을 지운다. 체크포인트를 끝내지 못하면 전환을 거부하고 `wal`을 돌려준다. 코드가 이 경우를 실패로 처리하므로 "데이터가 `-wal`에 남은 채 `-wal`이 지워진 사본"은 만들어질 수 없다. 새 사본에는 이 도구 말고 다른 연결이 없으므로 전환이 막힐 이유도 없다.
- 재현 스크립트로 확인: 원본 본 파일이 4096 B(헤더 쪽만)이고 500행 전부가 `-wal`(24752 B)에만 있던 상태에서 백업했다. 사본은 16384 B 한 파일, 헤더 (1, 1), `journal_mode`=`delete`, 500행 모두 있음. 사본을 다시 읽기 전용으로 열어도 옆 파일이 생기지 않았다.

## 3. 정리가 지우는 것과 절대 건드리지 않는 것

- 대상 이름: `BACKUP_DIR` 바로 아래의 `<접두어>_YYYYMMDD_HHMMSS.db-wal`, `<접두어>_YYYYMMDD_HHMMSS.db-shm`. 접두어는 이 도구의 5개(`production`, `archive_2025`, `materials`, `notifications`, `anomaly`)이고, 정리는 호출된 접두어 하나씩만 본다(정규식 `^<접두어>_\d{8}_\d{6}\.db(-wal|-shm)$`).
- 지우는 것
  - 보존 정리로 지운 백업의 `-wal`, `-shm`
  - 짝인 `.db`가 없는 옆 파일(고아)
  - 남아 있는 백업 옆의 `-shm`(색인일 뿐 데이터가 없다)
  - 남아 있는 백업 옆의 크기 0인 `-wal`
- 지우지 않는 것
  - 남아 있는 백업 옆의 크기가 0보다 큰 `-wal`. 그 백업의 데이터가 들어 있을 수 있어 남기고 WARN을 남긴다. 이 도구가 만든 옆 파일은 늘 0 B였으므로 정상 운영에서는 나오지 않는다.
  - 모든 `.db` 파일. 옆 파일 정리는 `.db`를 열지도, 고치지도, 지우지도 않는다. `.db` 삭제는 기존 보존 규칙(접두어별 최신 N개)으로만 일어난다.
  - 다른 접두어의 파일, 이름 형식이 다른 파일(예: `production_manual.db-wal`), `-journal` 파일, 그 밖의 아무 파일, 백업 폴더 밖의 파일(원본 DB 폴더 포함)

## 4. 테스트

- 파일: `tests/test_backup_db.py`. 기존 11개는 고치지 않았고 5개를 더했다. 모두 `tmp_path` 아래에서만 돈다.
  - `test_wal_source_backup_is_single_complete_file`: 쓰기 연결이 열린 WAL 원본(200행이 `-wal`에만 있음)을 백업하면 백업 폴더에 `.db` 하나만 있고, 헤더가 rollback, 200행 모두 있음, 검증 후에도 옆 파일 없음.
  - `test_backup_leaves_wal_source_unchanged`: 백업 전후 원본 폴더의 파일 목록이 같고, `.db`와 `-wal`이 바이트 단위로 같고, 원본 `journal_mode`가 `wal`이고 내용이 같다. `-shm`은 바이트 비교에서 뺐다. 이유는 6절.
  - `test_cleanup_removes_sidecars_of_deleted_backups`: 보존에서 밀려난 백업의 `-shm`, `-wal`도 지워진다.
  - `test_cleanup_removes_stale_sidecars_and_touches_nothing_else`: 남은 백업 옆 `-shm`과 빈 `-wal`, 고아 옆 파일은 지워지고, 크기가 있는 `-wal`, 다른 접두어 옆 파일, 형식이 다른 이름, `-journal`, `notes.txt`, `.db` 내용은 그대로다.
  - `test_failed_verification_removes_backup_and_sidecars`: WAL 헤더 사본(옆 파일 포함)은 검증에서 실패하고 백업 폴더가 비게 된다.
- 실행한 명령(작업트리에서)
  - `C:/X/Server_API/.venv/Scripts/python.exe -m pytest tests/test_backup_db.py -q -p no:cacheprovider` → `16 passed in 0.54s`
  - `C:/X/Server_API/.venv/Scripts/python.exe -m ruff check tools/backup_db.py tests/test_backup_db.py` → `All checks passed!`
- 확인용으로 `tools/backup_db.py`만 변경 전 판(HEAD)으로 잠시 되돌려 같은 테스트를 돌렸다 → `4 failed, 12 passed`. 실패한 4개는 새 테스트 중 원본 무변경 테스트를 뺀 4개다(원본 무변경은 변경 전에도 지켜지던 성질이라 통과). 그 뒤 수정본으로 되돌리고 다시 `16 passed`를 확인했다.

## 5. 배포 후 운영자가 보게 될 것

- 새로 만들어지는 백업은 `.db` 한 파일뿐이다. 옆에 `-wal`, `-shm`이 생기지 않는다.
- 다음 정기 실행(02:30)에서 접두어마다 백업이 성공한 뒤 정리가 돌면서, 지금까지 쌓인 옆 파일이 지워진다. 로그에 `Removed stale sidecar: ...` 줄이 지워진 파일 수만큼 나온다. 쌓인 `-wal`이 모두 0 B라면 남는 것이 없다.
- 어떤 접두어의 백업이 그날 실패하면 그 접두어의 정리는 돌지 않으므로(기존 동작), 그 접두어의 옆 파일은 다음 성공 때 또는 `python tools/backup_db.py --cleanup` 실행 때 지워진다.
- 이미 있는 예전 백업 `.db`는 그대로 둔다(헤더가 WAL인 채로). 누군가 이 예전 백업을 다시 열면 옆 파일이 또 생길 수 있고, 다음 실행에서 다시 치워진다. 예전 백업도 데이터는 본 `.db`에 다 들어 있다(그때 생긴 `-wal`은 0 B였다).
- 백업 크기, 이름, 보존 개수, 요약 줄, 종료 코드는 그대로다.

## 6. Archive 보존 개수 (항목 2, 바꾸지 않음)

- 코드가 하는 일
  - `ARCHIVE_BACKUP_RETENTION = 12` (`tools/backup_db.py:47`). 정리는 날짜가 아니라 파일 개수로 센다. 접두어 `archive_2025_*.db`를 mtime 최신순으로 12개 남기고 나머지를 지운다.
  - 인자 없는 실행은 archive도 매번 백업한다(`main()`의 `if not args.live:` 블록, 현재 370행). `--archive`만 따로 도는 주간 예약은 저장소에 없다.
  - 따라서 매일 한 번 인자 없이 돌면 archive 백업은 최근 12일치가 남는다.
- 설명이 주장하는 것
  - 상수 옆 주석: `# Keep last 12 weekly backups` (`tools/backup_db.py:47`)
  - 모듈 docstring: `Retention policy: 30 daily backups for Live DB, 12 weekly for Archive DB` (`tools/backup_db.py:9`)
  - README.md:164: `Archive 12개`라고만 쓰고 주기는 말하지 않는다.
  - `docs/specs/operations_manual.md` §5 표: Archive "최근 12개". 같은 절의 스케줄 예시는 "매일 오전 2:00, 인수 `tools/backup_db.py`"(인자 없이 전체)라서, 그 예시대로 등록하면 역시 12일치다.
  - `docs/backup-coverage-RESULT.md` §8은 "archive는 원래 주 1회 정책이므로 `--live`와 인자 없는 실행을 나눠 예약할지 함께 정한다"고 적어 두었다.
- 결정할 것(사람): 12일치로 충분하면 주석·docstring의 "weekly"를 고치고, 12주치를 원하면 archive만 주 1회로 따로 예약하거나 보존 개수를 바꾼다. 이번 작업에서는 아무것도 바꾸지 않았다.

## 7. 확인하지 못한 것과 남은 점

- 운영 PC, 실제 `database/` 폴더, 실제 백업 파일은 보지 않았다. 운영 PC의 원본 5개 중 어느 것이 WAL 모드인지, 쌓인 `-wal`이 정말 모두 0 B인지는 확인하지 못했다. 크기가 있는 `-wal`이 있으면 지우지 않고 WARN으로 남는다.
- 원본 쪽 `-shm`: 읽기 전용이라도 SQLite 읽기 연결은 원본 `-shm` 안의 read-mark 칸을 갱신한다. 데이터가 아니고 앱 자신의 읽기도 늘 하는 일이며, 변경 전 코드도 같았다. 그래서 테스트에서 `-shm`만 바이트 비교에서 뺐다.
- 원본을 쓰는 앱 연결이 하나도 없을 때(앱이 꺼져 있고 원본 옆에 `-wal`/`-shm`이 없을 때) 백업하면, 원본 폴더에 빈 `-wal`(0 B)과 `-shm`이 새로 생기고 남는다. 재현 스크립트로 확인했다. 원인은 읽기 전용 원본 연결(`mode=ro`)이 WAL 원본을 열 때의 SQLite 동작이고, 변경 전에도 같았다. 내용은 없고 앱이 다음에 열 때 그대로 쓴다. 이것을 없애려면 원본을 쓰기 가능으로 열거나 원본 옆 파일을 지워야 하는데, 원본에 쓰지 않는다는 조건 때문에 고치지 않았다. 앱이 돌고 있는 평소 02:30 실행에서는 원본 옆 파일이 이미 있으므로 새로 생기는 것이 없다(테스트로 확인).
- 전체 테스트(`pytest tests/`)는 돌리지 않았다. `tools/backup_db.py`를 import하는 테스트는 `tests/test_backup_db.py`뿐이다.
- push, 병합은 하지 않았다.
