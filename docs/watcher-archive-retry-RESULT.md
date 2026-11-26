# watcher-archive-retry 결과 (2026-11-26)

- 브랜치: `fix/watcher-archive-retry` (기점 `test/gap-top` 65f31c8), worktree `C:/X/Server_API/.claude/worktrees/watcher-archive-retry`
- 고친 파일: `tools/watcher.py`, `tests/test_watcher_run_check.py`. 다른 운영 코드(`shared/`, `tools/db_watcher.py`, Live 경로, 데몬 루프, 로그 형식)는 바꾸지 않았다.
- push·merge 하지 않았다. 실 DB·네트워크·서버·포트·운영 PC는 쓰지 않았다. 모든 DB는 임시 SQLite.

## 직접 확인한 것 (고치기 전 코드, 65f31c8 기준 줄 번호)

결함 1 — 불안정으로 건너뛴 Archive 치유가 다시 시도되지 않음
- `tools/watcher.py:141`에서 새 mtime/size를 읽고, 불안정 경로(153-154)는 로그만 남긴 뒤 157에서 그 새 값을 돌려준다.
- `run_check`가 그 값을 저장한다(210-216). 다음 주기에는 상태=실제라 unchanged(155-156)이고, Archive는 미변경이면 치유하지 않는다.
- `tools/db_watcher.py:103-105`는 안정화에 성공했을 때만 상태를 갱신한다. 불안정이면 갱신하지 않아 다음 주기에 다시 시도한다.
- 결과 문서(`docs/test-gap-top-RESULT.md`)의 설명과 줄 번호가 맞다.

결함 2 — 감시기 자신의 ANALYZE 쓰기를 다음 주기에 'DB 변경'으로 봄
- 파일 상태는 201, 204에서 잡히고 ANALYZE는 207에서 돈다. 저장되는 것은 ANALYZE 이전 값이다(210-216).
- 결과 문서의 설명이 맞다. 한 가지 덧붙임: 실제 운영 DB가 WAL 모드라면 ANALYZE는 먼저 `-wal` 파일에 쓰고 본 파일은 체크포인트 때 바뀐다. 이때는 이 오보가 ANALYZE 직후가 아니라 체크포인트 시점에 나거나 나지 않을 수 있다(아래 "확인하지 못한 것").

## 바꾼 내용 (고친 뒤 줄 번호)

결함 1
- `tools/watcher.py:154-158`: 불안정 경로에서 `return state["archive_mtime"], state["archive_size"]`로 지난번 저장 상태를 그대로 돌려준다. DBWatcher와 같은 방식이다.
- 안전한 이유: 치유가 실제로 돈 경로(150-152)는 그대로 치유 뒤 상태를 다시 읽어 저장하므로, 끝난 치유는 반복되지 않는다. 파일이 계속 불안정하면 매 주기 안정화 대기(최대 3×5초×재시도)를 다시 한다. DBWatcher와 같은 비용이다.
- Live 경로는 바꾸지 않았다. Live는 미변경이어도 매 주기 치유하므로 이 결함이 드러나지 않는다(지시대로 Live 동작 유지).

결함 2
- `tools/watcher.py:164-178` `_change_counter` 새로 추가: SQLite 머리말의 파일 변경 카운터(오프셋 24, 4바이트)를 읽는다. 롤백 저널 모드(머리말 18·19바이트 = 1)일 때만 값을 주고, WAL 모드거나 읽을 수 없으면 None.
- `tools/watcher.py:181-211` `_run_periodic_analyze`에 선택 인자 `file_states` 추가(기본 None이라 기존 호출·시험 그대로). DB마다 ANALYZE 직전 상태와 카운터를 읽고, ANALYZE 뒤 다음 세 조건이 모두 맞을 때만 저장 예정 상태를 ANALYZE 뒤 값으로 바꾼다.
  - ANALYZE 직전 파일 상태 = 이번 주기에 검사해 저장하려던 상태 (검사 뒤 외부 변경 없음)
  - 카운터를 읽을 수 있음 (롤백 저널 모드)
  - ANALYZE 동안 카운터가 정확히 1 올랐음 (ANALYZE 자신의 커밋 1건뿐)
- `tools/watcher.py:245-250` `run_check`: 저장할 두 DB 상태를 사전으로 넘기고, 돌아온 값으로 저장한다.
- 진짜 변경을 숨기지 않는 이유
  - 검사와 ANALYZE 사이 외부 쓰기: 첫 조건에서 걸러진다.
  - ANALYZE 도중(또는 직후 상태 읽기 전) 외부 커밋: 롤백 모드에서 카운터가 2 이상 오르므로 걸러진다. 임시 DB로 확인: ANALYZE만 3→4, 외부 커밋+ANALYZE 3→5.
  - WAL 모드: 임시 DB로 확인한 결과 외부 커밋+ANALYZE가 합쳐 카운터가 1만 올랐다(2→3). 카운터로 구분할 수 없으므로 WAL 파일에는 갱신을 하지 않는다. 즉 WAL 모드에서는 결함 2가 이전처럼 남는다(숨기지 않는 쪽을 택함).
  - 남는 이론상 틈: ANALYZE 도중 파일이 통째로 바뀌고 새 파일의 카운터가 우연히 정확히 이전+1이며 롤백 모드인 경우. 이때는 그 교체를 흡수한다. Live는 매 주기 치유하므로 영향이 없고, Archive만 다음 변경까지 치유가 미뤄질 수 있다.
- 개발 중 확인: 카운터 조건 없이 "직전 상태 = 저장 예정 상태"만 보던 첫 판은 ANALYZE 도중 외부 쓰기 시험에서 외부 변경을 흡수해 실패했다. 그래서 카운터 조건을 넣었다.

## 시험

실행 환경: `C:/X/Server_API/.venv/Scripts/python.exe` (pytest 9.1.1), 작업 폴더는 worktree. 패키지 설치 없음. 시간은 가짜 시계, 안정화 대기는 가짜 함수(실제 sleep 없음).

xfail을 뗀 시험 2건 (단언은 그대로)
- `test_cycle_after_analyze_does_not_report_its_own_write_as_change`
- `test_archive_skipped_as_unstable_is_healed_on_next_cycle`

새 시험 (`tests/test_watcher_run_check.py`, 9건)
- `test_skipped_archive_heal_keeps_old_state_then_retries_once`: 불안정 주기에 옛 상태 (0, 0) 유지 → 다음 주기 changed·안정화 대기 1회·인덱스 6종 치유 → 그다음 주기는 치유·대기 없음.
- `test_skipped_archive_heal_is_retried_even_when_analyze_ran_that_cycle`: 같은 주기에 ANALYZE가 돌아도 옛 상태가 덮이지 않고 다음 주기에 치유된다.
- `test_completed_archive_heal_is_not_repeated_when_nothing_changed`: 치유 뒤 두 주기 연속 changed 아님, 결과 None, 대기 없음.
- `test_external_change_in_cycle_is_still_detected_with_analyze` (4건: live/archive × 검사 뒤/ANALYZE 도중): 외부 쓰기는 저장 상태에 흡수되지 않고 다음 주기에 changed로 잡힌다. 다른 DB의 ANALYZE 쓰기는 흡수된다.
- `test_change_counter_reads_rollback_header_only`: 롤백 모드 → 정수, WAL·짧은 파일·없는 파일 → None.
- `test_wal_db_state_is_not_refreshed_after_analyze`: WAL DB는 ANALYZE 뒤에도 저장 상태가 바뀌지 않는다(이전 동작).

명령과 결과
- `python -m pytest tests/test_watcher_run_check.py -q` → 27 passed
- `python -m pytest tests/test_watcher_run_check.py tests/test_db_watcher_thread.py tests/test_watcher_state.py -q` → 39 passed (`tools.watcher`를 import하는 시험 파일은 이 둘과 test_watcher_run_check뿐)
- 이전 보고서와 같은 묶음: `python -m pytest tests/test_watcher_run_check.py tests/test_watcher_state.py tests/test_db_watcher_thread.py tests/test_archive_live_boundary.py tests/test_routers_db.py tests/test_db_router.py tests/test_db_maintenance.py tests/test_db_attach.py tests/test_archive_whitelist.py tests/test_cache.py tests/test_db_connection_lifecycle.py tests/test_archive_cutoff.py -q` → 1 failed, 203 passed (이전: 1 failed, 192 passed, 2 xfailed. +9는 새 시험)
  - 실패 1건은 이전과 같은 `tests/test_routers_db.py::TestSystemRouter::test_healthz_db_connected`(worktree에 database/ 폴더가 없어 `disk_free_gb` 빠짐). 이번 변경과 무관하다.
- 수집 수: `python -m pytest --collect-only -q` → 559 (이전 550, +9)
- 고치기 전 코드로 되돌려 같은 시험 파일을 돌린 결과: 9 failed, 18 passed. 실패한 것은 xfail을 뗀 2건, 결함 1 새 시험 2건(옛 상태 유지·ANALYZE 동반 재시도), `_change_counter` 시험(함수 없음), 외부 변경 시험 4건(외부 변경 감지 자체가 아니라 "다른 DB는 unchanged" 단언, 즉 결함 2 때문에 실패). 이후 고친 파일로 되돌려 바이트 일치를 확인했다.
- 린트: `python -m ruff check tools/watcher.py tests/test_watcher_run_check.py` → All checks passed!

## 배포 뒤 운영자가 보게 될 것

- Archive DB가 바뀐 직후 불안정해 "Archive DB not stable, skipping index check"가 찍힌 경우, 다음 주기(1시간 뒤)에 다시 "Archive DB changed"가 찍히고 안정화 대기 후 인덱스 검사가 돈다. 이전에는 그 뒤 "Archive DB unchanged"만 찍히고 치유가 빠졌다.
- 롤백 저널 모드 DB에서는 ANALYZE가 돈 다음 주기에 "Live DB changed"/"Archive DB changed" 오보와 안정화 대기(DB마다 약 15초)가 사라진다. WAL 모드 DB에서는 이전과 같다.
- 상태 파일(`database/.watcher_state.json`) 형식은 그대로다.

## 확인하지 못한 것·남은 문제

- 운영 DB의 저널 모드를 확인하지 않았다(실 DB 금지). API 연결이 `PRAGMA journal_mode=WAL`을 건다(`shared/_db_connection.py:103`). 운영 DB가 WAL이면 결함 2 수정은 효과가 없다. 그 경우 오보는 이전처럼 남지만 숨겨지는 변경은 없다.
- Live 경로의 같은 성격 문제(고치지 않음, 지시대로 Live 동작 유지): 미변경 Live를 치유할 때(129-133, 지금 줄 번호도 같음) 실제로 인덱스를 만들면 상태를 다시 읽지 않아 다음 주기가 "Live DB changed"로 본다. 인덱스가 빠져 있을 때만 생기며, 새 시험은 Live 인덱스를 미리 만들어 이 영향을 뺐다.
- 실제 `wait_for_stabilization`, 실제 Task Scheduler 실행, 큰 DB에서의 ANALYZE 시간과 동시 쓰기 타이밍은 시험하지 않았다.
- 전체 시험 묶음은 돌리지 않았다(실 DB 사본을 읽는 시험이 있어 제외, 이전 보고서와 같은 이유).
