# watcher-archive-retry 결과 (2026-11-26, 최종)

- 브랜치: `fix/watcher-archive-retry` (기점 `test/gap-top` 65f31c8), worktree `C:/X/Server_API/.claude/worktrees/watcher-archive-retry`
- 최종 상태: 결함 1은 고쳤다. 결함 2는 일부러 고치지 않았다(소유자 결정, 아래).
- 고친 파일: `tools/watcher.py`(결함 1 4줄만), `tests/test_watcher_run_check.py`. 다른 운영 코드(`shared/`, `tools/db_watcher.py`, Live 경로, 데몬 루프, 로그 형식)는 바꾸지 않았다.
- 커밋 순서: eb19c21(결함 1+2 수정) → 6adbac4(첫 보고서) → 이번 커밋(결함 2 수정 제거, 이 문서 갱신). 이력은 고쳐 쓰지 않았다.
- push·merge 하지 않았다. 실 DB·네트워크·서버·포트·운영 PC는 쓰지 않았다. 모든 DB는 임시 SQLite.

## 직접 확인한 것 (고치기 전 코드, 65f31c8 기준 줄 번호)

결함 1 — 불안정으로 건너뛴 Archive 치유가 다시 시도되지 않음
- `tools/watcher.py:141`에서 새 mtime/size를 읽고, 불안정 경로(153-154)는 로그만 남긴 뒤 157에서 그 새 값을 돌려준다.
- `run_check`가 그 값을 저장한다(210-216). 다음 주기에는 상태와 실제가 같아 unchanged(155-156)로 보고, Archive는 미변경이면 치유하지 않는다.
- `tools/db_watcher.py:103-105`는 안정화에 성공했을 때만 상태를 갱신한다. 불안정하면 갱신하지 않아 다음 주기에 다시 시도한다.
- `docs/test-gap-top-RESULT.md`의 설명과 줄 번호가 맞다.

결함 2 — 감시기 자신의 ANALYZE 쓰기를 다음 주기에 'DB 변경'으로 봄
- 파일 상태는 201, 204에서 잡히고 ANALYZE는 그 뒤 207에서 돈다. 저장되는 것은 ANALYZE 이전 값이다(210-216).
- 결과 문서의 설명이 맞다.

## 결함 1 수정 (최종 코드)

- `tools/watcher.py:154-158`: 불안정 경로에서 `return state["archive_mtime"], state["archive_size"]`로 지난번 저장 상태를 그대로 돌려준다. DBWatcher와 같은 방식이다.
- `git diff test/gap-top -- tools/watcher.py`에 남은 변경은 이 한 덩어리(+4줄)뿐이다.
- 안전한 이유
  - 치유가 실제로 돈 경로(150-152)는 그대로 치유 뒤 상태를 다시 읽어 저장하므로, 끝난 치유는 반복되지 않는다.
  - 파일이 계속 불안정하면 매 주기 안정화 대기(최대 3×5초×재시도)를 다시 한다. DBWatcher와 같은 비용이다.
  - Live 경로는 바꾸지 않았다. Live는 미변경이어도 매 주기 치유하므로 이 결함이 드러나지 않는다.

## 결함 2 — 일부러 고치지 않음

- 결정: 소유자가 결함 2 수정을 빼라고 결정했다(2026-11-26). 그래서 eb19c21에서 넣었던 `_change_counter`, `_run_periodic_analyze`의 `file_states` 인자, ANALYZE 뒤 상태 갱신을 이번 커밋에서 모두 걷어냈다.
- 이유
  - 심각도가 낮다. 수치 오류는 없고, ANALYZE가 돈 다음 주기에 생기는 "changed" 오보 로그와 DB마다 약 15초의 안정화 대기뿐이다. ANALYZE는 하루 1회다.
  - 그 수정은 롤백 저널 모드 DB에서만 효과가 있었다. 운영 DB는 WAL 모드다(API 연결이 `PRAGMA journal_mode=WAL`을 건다, `shared/_db_connection.py:103`). 임시 DB로 확인한 결과, WAL에서는 외부 커밋과 ANALYZE가 합쳐 머리말 변경 카운터가 1만 올라 둘을 구분할 수 없었다. 그래서 WAL 파일에는 그 수정을 적용하지 않게 해 두었고, 결국 운영에는 효과가 없었다.
  - 머리말 카운터를 읽는 논리는 얻는 것에 비해 복잡하다.
- 현재 상태: `test_cycle_after_analyze_does_not_report_its_own_write_as_change`를 `test/gap-top`과 같은 strict xfail로 되돌렸다. 단언은 같고, reason 문구는 바뀐 줄 번호(watcher.py:205, 208, 211, 214-220)와 "알려진 문제로 수용, 고치지 않음"을 적어 고쳤다. 나중에 누가 이 결함을 고치면 strict xfail이 깨져 알려 준다.

## 시험

실행 환경: `C:/X/Server_API/.venv/Scripts/python.exe` (pytest 9.1.1), 작업 폴더는 worktree. 패키지 설치 없음. 시간은 가짜 시계, 안정화 대기는 가짜 함수(실제 sleep 없음).

결함 1 시험 (모두 통과)
- `test_archive_skipped_as_unstable_is_healed_on_next_cycle`: xfail 표시만 뗐다. 단언은 그대로다.
- `test_skipped_archive_heal_keeps_old_state_then_retries_once`: 불안정 주기에는 옛 상태 (0, 0)를 유지한다. 다음 주기는 changed로 보고 안정화 대기 1회 뒤 인덱스 6종을 치유한다. 그다음 주기에는 치유도 대기도 없다.
- `test_skipped_archive_heal_is_retried_even_when_analyze_ran_that_cycle`: 같은 주기에 ANALYZE가 돌아도 다음 주기에 치유된다.
- `test_completed_archive_heal_is_not_repeated_when_nothing_changed`: 치유 뒤 두 주기 연속 changed가 아니고, 결과는 None, 대기도 없다.

결함 2 시험
- `test_cycle_after_analyze_does_not_report_its_own_write_as_change`: strict xfail(수용된 결함). `--runxfail`로 돌리면 의도한 단언 `second["live"]["changed"] is False`에서 실패한다(`assert True is False`).

지운 시험 (걷어낸 코드만 다루던 것)
- `test_change_counter_reads_rollback_header_only`, `test_wal_db_state_is_not_refreshed_after_analyze`
- `test_external_change_in_cycle_is_still_detected_with_analyze` 4건. ANALYZE 뒤 상태 갱신이 외부 변경을 흡수하지 않는지 지키는 시험이었다. 갱신이 없어진 지금은 흡수할 경로 자체가 없다. "다른 DB는 unchanged" 단언은 결함 2 때문에 실패한다. 그 단언을 빼면 남는 내용이 "상태를 갱신하지 않는다"뿐이라 의미가 없어 모두 지웠다.

명령과 결과
- `python -m pytest tests/test_watcher_run_check.py -q` → 20 passed, 1 xfailed
- `python -m pytest tests/test_watcher_run_check.py tests/test_db_watcher_thread.py tests/test_watcher_state.py -q` → 32 passed, 1 xfailed. `tools.watcher`를 import하는 시험 파일은 test_watcher_run_check와 test_watcher_state뿐이다.
- `python -m pytest tests/test_watcher_run_check.py -q --runxfail` → 1 failed(위 결함 2 시험), 20 passed
- 린트: `python -m ruff check tools/watcher.py tests/test_watcher_run_check.py` → All checks passed!
- 참고(중간 판, eb19c21 시점): 이전 보고서와 같은 12개 파일 묶음은 1 failed, 203 passed였다. 실패 1건은 worktree에 database/ 폴더가 없어 생기는 기존 `test_routers_db.py::TestSystemRouter::test_healthz_db_connected`다. 최종 판으로는 이 묶음을 다시 돌리지 않았다. 이번에 바꾼 것은 watcher.py와 그 시험 파일뿐이다.

## 배포 뒤 운영자가 보게 될 것

- Archive DB가 바뀐 직후 불안정해 "Archive DB not stable, skipping index check"가 찍히면, 다음 주기(1시간 뒤)에 다시 "Archive DB changed"가 찍히고 안정화 대기 뒤 인덱스 검사가 돈다. 이전에는 그 뒤 "Archive DB unchanged"만 찍히고 치유가 빠졌다.
- ANALYZE가 돈 다음 주기의 "changed" 오보와 안정화 대기는 이전과 같이 남는다(결함 2, 수용).
- 상태 파일(`database/.watcher_state.json`) 형식은 그대로다.

## 바꾸지 않은 것·확인하지 못한 것

- Live 경로의 비슷한 동작은 고치지 않았다(Live 동작 유지 지시). 미변경 Live를 치유할 때(watcher.py:129-133) 실제로 인덱스를 만들면 상태를 다시 읽지 않는다. 그래서 다음 주기가 "Live DB changed"로 본다. 인덱스가 빠져 있을 때만 생긴다. 결함 1 시험은 Live 인덱스를 미리 만들어 이 영향을 뺐다.
- 운영 DB의 실제 저널 모드는 파일로 확인하지 않았다(실 DB 접근 금지). WAL이라는 판단은 API 연결 코드에 근거한다.
- 실제 `wait_for_stabilization`, 실제 Task Scheduler 실행, 큰 DB에서의 시간은 시험하지 않았다.
- 전체 시험 묶음은 돌리지 않았다. 실 DB 사본을 읽는 시험이 있어서 뺐다(이전 보고서와 같은 이유).
