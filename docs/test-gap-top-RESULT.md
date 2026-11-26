# test-gap-top 결과 (2026-11-26)

- 브랜치: `test/gap-top` (기점 d92596b), worktree `C:/X/Server_API/.claude/worktrees/test-gap-top`
- 근거 지도: `C:/X/_ops/glm-assets-20261126/testgap/Server_API.md` (모델 작성, 아래에서 코드와 대조)
- 운영 코드는 바꾸지 않았다. 시험 파일 3개만 새로 만들었다. push·merge 하지 않았다.
- 실 DB·네트워크·서버·포트는 쓰지 않았다. 모든 DB는 pytest tmp_path의 임시 SQLite, 시간·안정화 대기는 가짜로 바꿨다(실제 sleep 없음).

## 새 시험 파일

- `tests/test_watcher_run_check.py` (18건, 그중 xfail strict 2건): 공백 2
- `tests/test_db_watcher_thread.py` (8건): 공백 3
- `tests/test_archive_live_boundary.py` (21건): 공백 5, 공백 7

## 공백 2 — tools/watcher.py 실행 코어

코드가 실제로 하는 일
- `_check_live_db` (tools/watcher.py:110-133): 상태와 다르면 안정화 대기 후 치유하고 파일 상태를 다시 읽는다(126). 같으면 대기 없이 그래도 치유한다(129-132).
- `_check_archive_db` (136-157): 파일 없으면 로그만(142-144). 바뀌면 안정화 대기 후 치유(150-152). 바뀌지 않으면 치유하지 않는다(155-157). 즉 주기적 치유는 Live만 받는다.
- `_run_periodic_analyze` (160-180): `now - last_ts < 86400`이면 건너뛴다. 정확히 24시간이면 실행한다. 실패해도 시각은 now로 넘어간다(180).
- `run_check` (183-222): Live 검사 → Archive 검사 → ANALYZE → 상태 저장. 저장하는 파일 상태는 ANALYZE 이전에 잡은 값이다(201, 204, 210-216).
- `run_daemon` (225-241): `(OSError, RuntimeError, ValueError, JSONDecodeError, sqlite3.Error)`만 잡는다(234).
- `main` (247-273): 치유 결과에 error가 있을 때만 1을 반환한다. ANALYZE 실패는 반환 코드에 반영되지 않는다.

지도의 주장 대조
- "run_check 계열은 어떤 시험도 부르지 않는다": 맞다.
- 129-133 "미변경인데도 heal" 분기: 맞다. 단 이 분기는 Live에만 있다. Archive는 미변경이면 치유하지 않는다(지도에는 이 구분이 없다).
- 사례 "ANALYZE 실패 → main 반환 코드 1": 현재 코드와 다르다. main은 ANALYZE 실패를 보지 않는다. 시험하지 않고 아래 관찰로만 남겼다.

추가한 시험
- `test_first_run_heals_both_dbs_runs_analyze_and_saves_state`: 상태 파일 없음(전부 0) → 두 DB 모두 changed, 안정화 대기 2회, 인덱스 6종 실제 생성, ANALYZE 즉시 2건 성공, last_analyze_ts=now 저장.
- `test_state_is_refreshed_after_heal_so_next_cycle_sees_unchanged`: ANALYZE가 아닌 날, 치유 후 다시 읽은 파일 상태가 저장되어 다음 주기는 unchanged·대기 없음.
- `test_unchanged_live_db_is_still_healed`: 상태=실제 → 안정화 대기 없이 Live 인덱스 6종 생성.
- `test_unchanged_archive_db_is_not_healed`: 현재 동작 고정 — 미변경 Archive는 치유하지 않음.
- `test_changed_but_unstable_live_db_skips_heal`: 불안정 → 치유 안 함, 경고 로그.
- `test_archive_skipped_as_unstable_is_healed_on_next_cycle` (xfail strict, 버그 1)
- `test_cycle_after_analyze_does_not_report_its_own_write_as_change` (xfail strict, 버그 2)
- `test_missing_archive_is_skipped_and_state_zeroed`, `test_missing_live_db_is_skipped`: 파일 없음 → 건너뜀, 파일을 새로 만들지 않음, 상태 (0, 0).
- `test_periodic_analyze_boundary` (5개 모수): ts=0, 24h+1초, 정확히 24h → 실행 / 24h-1초, 0초 → 건너뜀.
- `test_failed_analyze_is_recorded_and_still_advances_timestamp`: 실패가 summary에 남고 시각은 넘어감(현재 동작 고정).
- `test_main_returns_1_when_heal_reports_error`, `test_main_returns_0_on_clean_run`.
- `test_daemon_survives_a_failed_cycle`: sqlite3 오류, OSError 뒤에도 루프가 계속 돌고 매 주기 interval만큼(1초 단위) 쉰다.

증명하지 못하는 것
- 실제 `wait_for_stabilization`과 엮인 동작(가짜로 바꿨다. 그 함수 자체는 test_db_maintenance가 다룬다).
- `get_file_state`가 OSError를 삼키고 (0, 0)을 주는 순간의 run_check 흐름(파일 교체 타이밍).
- 운영 PC Task Scheduler에서의 실행, 실 DB 크기에서의 소요 시간.

## 공백 3 — tools/db_watcher.py DBWatcher

코드가 실제로 하는 일
- `run` (tools/db_watcher.py:42-65): interval초를 1초씩 자고 `_check_and_heal` 호출. `(sqlite3.Error, OSError)`는 "Watcher Error"(57-62), 그 밖의 모든 Exception은 "Watcher Unexpected Error"(63-65)로 큐에 넣고 60초 쉰 뒤 계속.
- `_check_and_heal` (71-105): 바뀐 DB만 안정화 대기 후 치유. 불안정하면 상태를 갱신하지 않아(103-105) 다음 주기에 다시 시도한다.

지도의 주장 대조
- "시험 없음": 맞다.
- 예외 생존 처리 위치 "~58-60, sqlite3.Error·OSError": 일부만 맞다. 63-65의 범용 Exception 처리도 있다.

추가한 시험
- `test_init_tracks_only_existing_db_files`, `test_change_detected_heals_indexes_and_refreshes_state`, `test_unchanged_db_is_not_touched`, `test_unstable_db_keeps_old_state_and_is_retried_next_cycle`, `test_deleted_db_file_is_skipped`
- `test_run_loop_survives_exceptions_in_a_cycle`: OSError, sqlite3.OperationalError, RuntimeError, KeyError가 차례로 나도 5번째 주기까지 돌고, 오류마다 60초 대기, 메시지 분류가 맞다.
- `test_run_loop_survives_real_getmtime_oserror`: 실제 `_check_and_heal` 경로에서 `os.path.getmtime`이 OSError(파일 교체 모사) → 기록 후 다음 주기 진행.
- `test_stop_during_interval_sleep_skips_the_cycle`: 대기 중 stop() → 주기 실행 없이 종료.

증명하지 못하는 것
- 실제 스레드(start/join)로 돌렸을 때의 동작(run을 시험 스레드에서 직접 불렀다), `manual_trigger`, manager GUI와의 연결.

## 공백 5 — /records 커서 페이지네이션 (아카이브+라이브)

코드가 실제로 하는 일
- 커서 조건 (api/routers/records.py:131-141)은 정렬 `production_date DESC, source DESC, id DESC` (175)와 맞물린다. next_cursor는 마지막 행의 (date, id, source) (196-199).
- UNION 각 부분이 컷오프로 걸러진다: 아카이브 `production_date < cutoff`, 라이브 `>= cutoff` (shared/database.py:246-260). 그래서 같은 날짜가 두 DB에 동시에 나올 수 없고, 같은 id는 source로 갈린다.

지도의 주장 대조
- "live_and_archive_db fixture를 쓰는 시험 0건": 맞다(이번에 처음 사용).
- "같은 날짜·같은 id가 두 DB에 동시에 존재하면 누락/중복": 같은 id는 시험 데이터에 실제로 넣었고 누락·중복이 없었다. 같은 날짜는 컷오프 필터 때문에 두 DB에서 함께 나올 수 없다. 위험은 코드상 성립하지 않는다.

추가한 시험 (`TestRecordsCursorAcrossArchiveAndLive`)
- 시험 데이터: conftest 시드 + 아카이브 2025-12-01, 2025-12-31×2(같은 날 동점), 잘못 적재된 2026-01-15 / 라이브 2026-01-01×2(컷오프 당일 동점), 2026-12-31, 2027-01-01, 잘못 적재된 2025-12-31.
- `test_single_page_sees_both_sources_without_wrong_side_rows`: 한 번에 15행, 정해진 순서, 잘못 적재된 2행은 제외.
- `test_cursor_pages_return_every_row_once_in_order` (limit 1, 2, 3, 4, 7, 14, 15): 커서를 끝까지 따라가면 15행이 중복·누락 없이 같은 순서로 나온다.
- `test_cursor_pages_across_cutoff_with_date_range`: 2025-12-01~2026-01-31, limit=1로 컷오프를 넘어가는 페이지.
- `test_same_id_in_both_dbs_is_kept_apart_by_source`: id 1~5가 양쪽에 다 있어도 각각 나온다.
- `test_archive_only_range_pages`: 아카이브만 대상인 구간.

증명하지 못하는 것
- 페이지 사이에 데이터가 바뀌는 경우(ERP 교체 중 조회), 대량 데이터에서의 성능, offset 경로와 커서의 혼용.

## 공백 7 — /summary/monthly_by_item 연말 경계

코드가 실제로 하는 일
- api/routers/summary.py:158-161: 12월이면 다음 해 01-01, 아니면 같은 해 다음 달 01일을 `pick_targets`에 넘긴다. 집계 조건은 `substr(production_date, 1, 7) = year_month` (169).
- 2025-12는 `pick_targets("2025-12-01", "2026-01-01")` → 아카이브와 라이브 둘 다 조회된다(date_to가 배타적인데 `>=` 비교라서, shared/database.py:122). 라이브 쪽은 결과가 비어 수치는 맞다. `pick_targets` docstring 예시(99행 "Archive only")와 다르지만 기존 시험 `test_cutoff_as_date_to_exclusive`가 이 동작을 의도로 고정하고 있다. 수치 오류는 아니고 불필요한 조회일 뿐이다.

지도의 주장 대조
- 12월 계산 위치 158-161: 맞다. 계산도 맞다(시험으로 확인).
- "'2026-13'은 패턴 통과 뒤 map(int)에서 터진다": 틀렸다. `map(int)`는 "2026-13"을 13으로 문제없이 바꾸고, 다음 달 경계 "2026-14-01"을 만든 뒤 빈 목록과 200을 돌려준다. "2026-00"도 200과 빈 목록. 500은 나지 않는다. 다만 잘못된 달을 400으로 거르지 않는 입력 검증 빈틈은 남는다(다른 엔드포인트는 잘못된 날짜에 400).

추가한 시험 (`TestMonthlyByItemYearBoundary`)
- `test_next_month_bound_passed_to_router` (2025-12, 2026-12, 2026-11, 2026-01): `pick_targets`에 넘어가는 경계값을 감시.
- `test_december_2025_aggregates_archive_month_only`: BW0021 21, AA0001 5. 라이브에 잘못 적재된 2025-12-31 행은 빠진다.
- `test_january_2026_aggregates_live_month_only`: 아카이브에 잘못 적재된 2026-01-15 행은 빠진다.
- `test_december_2026_excludes_next_january`: 2027-01-01 행이 섞이지 않는다.
- `test_no_month_filter_keeps_months_separate_across_cutoff`
- `test_out_of_range_month_is_not_a_server_error` ("2026-13", "2026-00"): 500이 아니어야 하고, 200이면 빈 목록. 나중에 400으로 바꿔도 통과하도록 썼다.

증명하지 못하는 것
- 캐시(`api_cache`)가 DB 교체 후 오래된 월 집계를 돌려주는 경우.

## 공백 6 — WEBHOOK_MAX_PAYLOAD_BYTES

- 확인 결과: 시행되지 않는다. 시험은 쓰지 않았다(지시대로).
- 근거
  - 정의: shared/config.py:130 `WEBHOOK_MAX_PAYLOAD_BYTES = int(os.getenv("WEBHOOK_MAX_PAYLOAD_BYTES", 65536))`
  - 저장소 전체(webcloring-pdf 제외)에서 이 이름을 읽는 코드가 없다. 나오는 곳은 config.py:130과 docs/ 4곳뿐.
  - 적재: api/notifications/deliveries_repo.py:51 (`create_pending_delivery`), :117 (`enqueue_delivery`)가 `json.dumps(dict(payload))`를 크기 검사 없이 저장한다.
  - 전송: api/notifications/dispatcher.py:72 `body = orjson.dumps(dict(payload))`를 크기 검사 없이 보낸다.
- 판단: 운영 결함 후보로 기록한다. 고치지 않았다.
- 문서 쪽 사정: docs/03-analysis/webhook-notifications-v1.analysis.md:72가 "Constant defined for future use ... out-of-scope per Plan §2.2"라고 적었으나, docs/01-plan/features/webhook-notifications-v1.plan.md의 §2.2(90-100행) Out of Scope 목록에는 payload 크기 항목이 없다. 의도된 미루기인지 누락인지는 문서로 확정되지 않는다.

## 찾은 버그 (운영 코드 미수정, xfail strict로 남김)

버그 1 — 불안정으로 건너뛴 Archive 치유가 다시 시도되지 않는다 (중간)
- 시험: `tests/test_watcher_run_check.py::test_archive_skipped_as_unstable_is_healed_on_next_cycle`
- 실패하는 단언: `assert _index_names(wenv.archive) == set(REQUIRED_INDEXES)` → 실제 `set()`
- 근거: `_check_archive_db`가 불안정 경로에서도 새로 읽은 mtime/size를 돌려준다(tools/watcher.py:141, 153-154, 157). `run_check`가 그것을 상태로 저장한다(210-216). 다음 주기에는 상태=실제라 unchanged로 보고, Archive는 미변경 시 치유하지 않으므로(155-157) 다음 변경 때까지 치유가 빠진다. 같은 경우 DBWatcher는 상태를 갱신하지 않고 다시 시도한다(tools/db_watcher.py:103-105). Live는 미변경 시에도 치유하므로 이 문제가 가려진다.

버그 2 — ANALYZE가 쓴 변경을 다음 주기에 'DB 변경'으로 오인한다 (낮음)
- 시험: `tests/test_watcher_run_check.py::test_cycle_after_analyze_does_not_report_its_own_write_as_change`
- 실패하는 단언: `assert second["live"]["changed"] is False` → 실제 True
- 근거: 파일 상태는 tools/watcher.py:201, 204에서 잡히고 ANALYZE는 그 뒤 207에서 돈다. ANALYZE가 sqlite_stat1을 써서 파일이 바뀌지만 저장되는 것은 이전 상태다(210-216). 그래서 ANALYZE가 돈 다음 주기에는 두 DB가 모두 changed로 보고되고 안정화 대기(DB마다 3×5초)와 치유 검사를 다시 한다. 수치 오류는 없고 로그 오보와 대기 시간 낭비다.

## 관찰 (시험 없음, 버그로 확정하지 않음)

- `run_daemon`은 다섯 가지 예외만 잡는다(tools/watcher.py:234). KeyError·TypeError 같은 다른 예외가 나면 데몬 프로세스가 끝난다. DBWatcher는 모든 Exception에서 살아남도록 되어 있어(tools/db_watcher.py:63-65) 둘의 방침이 다르다. 운영 Task가 끝난 프로세스를 다시 띄우는지는 확인하지 않았다.
- `main`은 ANALYZE 실패를 반환 코드에 반영하지 않는다(tools/watcher.py:267-271). ANALYZE 실패 뒤에도 last_analyze_ts가 넘어가 24시간 동안 재시도하지 않는다(180). 현재 동작으로 시험에 고정했다.
- `/summary/monthly_by_item`은 "2026-13", "2026-00"을 400으로 거르지 않고 200과 빈 목록을 준다.

## 시험 수와 실행 명령

실행 환경: `C:/X/Server_API/.venv/Scripts/python.exe` (pytest 9.1.1), 작업 폴더는 worktree. 패키지 설치 없음.

- 수집 수(전): `python -m pytest --collect-only -q` → 503 tests collected
- 수집 수(후): 같은 명령 → 550 tests collected (+47: 18 + 8 + 21)
- 새 시험 + 같은 영역 기존 시험:
  `python -m pytest tests/test_watcher_run_check.py tests/test_watcher_state.py tests/test_db_watcher_thread.py tests/test_archive_live_boundary.py tests/test_routers_db.py tests/test_db_router.py tests/test_db_maintenance.py tests/test_db_attach.py tests/test_archive_whitelist.py tests/test_cache.py tests/test_db_connection_lifecycle.py tests/test_archive_cutoff.py -q`
  → 1 failed, 192 passed, 2 xfailed
- 실패 1건은 기존 시험 `tests/test_routers_db.py::TestSystemRouter::test_healthz_db_connected`(`assert "disk_free_gb" in body`)다. 새 파일 없이 기존 파일만 돌려도 똑같이 실패한다. 원인: worktree에는 database/ 폴더가 없어(gitignore 대상) api/routers/system.py:107 `shutil.disk_usage(DATABASE_DIR)`가 OSError를 내고 109-110에서 조용히 넘어가 키가 빠진다. 이 worktree 환경 탓이며 이번 변경과 무관하다. 고치지 않았다.
- 린트: `python -m ruff check tests/test_watcher_run_check.py tests/test_db_watcher_thread.py tests/test_archive_live_boundary.py` → All checks passed!
- xfail 2건이 의도한 단언에서 실패하는지 `--runxfail`로 확인했다.

## 돌리지 않은 것

- 전체 시험 묶음은 돌리지 않았다. `tests/test_api_integration.py`와 `tests/test_audit.py`의 일부는 기본 DB_FILE(로컬 실 DB 사본)을 읽기 전용으로 조회한다(지도 §4). 실 데이터 금지 조건 때문에 제외했다. `tests/test_process_utils.py`, `tests/test_service_mode.py`는 실제 프로세스를 띄우므로 이번 영역 밖이라 돌리지 않았다.
- 커버리지(`--cov`)는 재지 않았다. tools/는 측정 범위(`api`, `shared`) 밖이다.

## 지도에서 틀린 것

- 공백 7: "'2026-13'이 map(int)에서 터진다" — 틀림. 200과 빈 목록.
- 공백 3: 예외 처리 위치를 sqlite3.Error·OSError(58-60)로만 적음 — 범용 Exception 처리(63-65)도 있다.
- 공백 2 사례 "ANALYZE 실패 → main 반환 코드 1" — 현재 코드는 그렇게 동작하지 않는다(의도인지는 미확정).
- 공백 5: 같은 날짜가 두 DB에 동시에 나오는 위험 — 컷오프 필터 때문에 일어날 수 없다. 같은 id는 source로 갈려 문제없다.
- 공백 2·3에서 지도가 짚지 못한 실제 결함 2건(위 버그 1, 2)이 나왔다.
