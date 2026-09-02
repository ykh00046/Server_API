# Server_API 딥 버그 헌팅 감사 보고서

> **상태: ✅ 완료 반영** (2026-07-15) — F-01/F-02/F-03이 05 지시서로 수정되어 `main`(9603290) 병합·push. F-04~F-17은 본 사이클 범위 밖(후속).

> 감사일: 2026-07-12 · 대상: `C:\X\Server_API` (api/ · dashboard/ · shared/ · tools/ 핵심 모듈 전수 정독)
> 방법: 소스 정독 + **실행 검증** (설치된 google-genai 2.8.0 SDK로 오류 객체 재현, 라이브/아카이브 DB read-only 조회로 데이터 형식 확인, streamlit 1.58 스레드 모델 소스 확인). 앱 실행·DB 수정 없음.
> 제외: 01/02/04 문서에 이미 기록된 이슈(인증 미사용, 쿼리 이중화, 챗 폴백 로직 이중화, /materials/run·webhook CRUD 무보호)는 재보고하지 않음.

---

## 1. 요약

| 심각도 | 건수 |
|---|---|
| Critical | 1 |
| High | 2 |
| Medium | 9 |
| Low | 5 |
| **합계** | **17** |

핵심 패턴 3가지:

1. **테스트와 실환경의 형태 불일치** — 폴백/재시도 테스트는 `status` 필드 없는 가짜 오류로 green이지만, 실제 SDK 오류에서는 판정 로직이 전부 False를 반환한다 (F-01).
2. **데이터 형식 가정 붕괴** — `production_date`가 실제로는 한국어 오전/오후 datetime 문자열인데, 일부 SQL이 ISO datetime을 가정한다 (F-02, F-16).
3. **스레드 수명과 자원 수명의 불일치** — thread-local 연결 캐시가 "스레드는 오래 산다"를 가정하지만, Streamlit과 ThreadPoolExecutor는 스레드를 계속 새로 만든다 (F-03).

---

## 2. 발견 목록

### F-01 [Critical] Gemini 폴백·재시도가 실제 SDK 오류에서 전혀 동작하지 않음

- **위치**: `api/_gemini_client.py:56-65` (`is_fallbackable`), `api/chat.py:160-180` (`_is_retryable_error`), 구조 문제는 `api/_chat_stream.py:124-166` (`_open_model_stream`)
- **문제**: 두 판정 함수 모두 `status_code = getattr(e, "status", 0) or 0` 후 `status_code in {429, 503, ...}`로 비교한다. 그러나 설치된 google-genai 2.8.0의 `APIError`는 **`.code`가 HTTP 상태코드(int)이고 `.status`는 문자열**(`"RESOURCE_EXHAUSTED"`, `"UNAVAILABLE"`)이다. 실제 API 응답 JSON에는 `error.status`가 항상 포함되므로 `.status`는 비어 있지 않은 문자열이 되고 → `status_code == 0` 분기(문자열 스캔 폴백)를 건너뛰며 → `"RESOURCE_EXHAUSTED" in {429, 503}`은 False. **실행으로 검증 완료**:
  ```
  e = ClientError(429, {"error": {"code": 429, "message": "...", "status": "RESOURCE_EXHAUSTED"}})
  is_fallbackable(e)      → False   (기대: True)
  _is_retryable_error(e)  → (False, 'RESOURCE_EXHAUSTED')   (기대: (True, 429))
  ```
- **테스트가 못 잡는 이유**: `tests/test_chat_fallback.py:57-69`는 `ClientError(429, {"error": {"message": ...}})`처럼 **`status` 필드를 뺀** JSON으로 오류를 만든다. 이때 `.status`는 None → `or 0` → 문자열 스캔 경로로 빠져 테스트는 green이다. 실서비스 오류 형태와 테스트 형태가 다르다.
- **추가 (스트리밍 경로는 구조적으로도 도달 불가)**: 도구가 Python callable이면 SDK는 AFC(자동 함수 호출) 경로를 타는데, 2.8.0의 `aio.models.generate_content_stream`(models.py:8697~)은 이 경우 **HTTP 요청을 전혀 보내지 않고 async generator만 반환**한다. 즉 429/503은 `_open_model_stream`의 try/except가 아니라 첫 `__anext__`(= `_consume_stream` 내부)에서 발생하고, 그곳의 `except Exception` 핸들러는 폴백 없이 `ERR_INTERNAL` + raw 오류 문자열을 SSE로 내보낸다. `.status` 버그를 고쳐도 스트리밍 폴백은 열기 단계에서 발동할 수 없다.
- **발동 조건**: 실서비스에서 429(무료 쿼터 소진)·503 발생 시 항상.
- **영향**: 문서화된 "flash → flash-lite 폴백"과 "지수 백오프 재시도"가 **운영에서 사실상 죽은 기능**. 쿼터 초과 시 재시도 0회, 폴백 0회로 즉시 실패. 스트리밍에서는 사용자에게 raw API 오류 문자열(`str(error)[:500]`)이 노출되고 `_ERROR_MESSAGES`의 친화적 메시지 매핑(`rate_limited`)도 우회된다. AI 챗 전 경로(대시보드 AI 패널 포함) 전파.
- **수정 방향**: 판정을 `getattr(e, "code", None)`(int) 기준으로 교체하고, 문자열 `status`(`RESOURCE_EXHAUSTED`/`UNAVAILABLE`)도 보조 판정에 추가. 테스트 오류 픽스처에 실제 응답 형태(`status` 포함)를 반영. 스트리밍은 `_consume_stream`의 첫 청크 이전 오류를 폴백 가능하게 재구성(P1-1 `_chat_core` 추출 시 함께).
- **확신도**: 확실 (실행 재현).

### F-02 [High] 주별 집계 SQL이 실데이터 날짜 형식에서 전부 NULL 버킷 — 주별 추세 화면 무의미

- **위치**: `dashboard/data.py:296-307` (`load_weekly_summary`의 `week_expr = "strftime('%Y-W%W', production_date)"`), 소비처 `dashboard/views/trends.py:117-119`
- **문제**: 라이브/아카이브 DB의 `production_date`는 전량 `"2026-01-13 오전 12:00:00"` 형태(한국어 오전/오후, 22자 고정)다. SQLite `strftime`은 이 문자열을 파싱하지 못해 **모든 행에서 NULL**을 반환한다. **실데이터로 검증 완료**: 라이브 DB 1,542행 전체가 `strftime('%Y-W%W', production_date) = NULL`이고, 주별 집계 쿼리는 `[(None, 4072174.52, 1542)]` — 전 기간 총합이 담긴 **단일 NULL 행 1개**를 반환한다. 아카이브(25,587행)도 동일.
- **발동 조건**: 생산 추세 페이지에서 "주별" 선택 시 항상.
- **영향**: 주별 추세 차트/표가 x축 "None" 버킷 하나로 렌더된다. 같은 데이터를 pandas로 파싱하는 `charts.py`(`_parse_production_dt` 경유)는 정상이라 **페이지 간 수치가 상충**한다. `data.py:296` 주석은 "charts.py와 동일 규칙으로 통일"이라 주장하지만 SQL 쪽만 죽어 있다 — 과거 "주 경계 불일치 버그"를 고친 커밋이 실데이터 형식에서는 검증되지 않았음을 시사.
- **수정 방향**: `strftime('%Y-W%W', substr(production_date, 1, 10))`처럼 날짜 10자만 잘라 넘기거나(같은 파일의 일별 집계가 이미 `substr(...,1,10)` 사용), P1-2 `shared/queries.py` 통합 시 주 버킷 식을 SSOT로. 빈 fixture가 아닌 **실데이터 형식의 fixture**로 characterization 테스트.
- **확신도**: 확실 (실데이터 재현).

### F-03 [High] SQLite 연결 누수 — `_all_connections` 전역 리스트에 죽은 스레드의 연결이 영구 축적

- **위치**: `shared/_db_connection.py:21-51`, `shared/database.py:174-180` (`get_connection`의 thread-local 캐시 + `_all_connections.append`), `api/tools/summary.py:305-310` (`compare_periods`의 ThreadPoolExecutor)
- **문제**: `DBRouter.get_connection`은 연결을 (a) thread-local에 캐시하고 (b) 전역 `_all_connections` 리스트에 강한 참조로 추가한다. 제거 경로는 `_discard_connection`(같은 스레드가 mtime 변경/죽은 연결을 발견했을 때)과 atexit뿐이다. 그런데:
  - **Streamlit**: rerun마다 새 `ScriptRunner` 스레드를 만든다(streamlit 1.58 `app_session.py:488→script_runner.py:343`, 소스로 확인). 스레드가 죽으면 그 thread-local 연결은 다시는 `_discard_connection`될 수 없고, `_all_connections`의 강참조 때문에 **GC도 안 된다**. 캐시 미스가 나는 rerun마다 연결 1~2개가 영구 누적.
  - **compare_periods (AI 도구)**: 호출마다 새 `ThreadPoolExecutor(max_workers=2)` → 새 스레드 2개 → 새 연결 2개 → executor 종료로 스레드 사망 → **호출당 연결 2개 누수** (api_cache 5분 TTL 미스마다).
  - `_discard_connection`의 주석("ERP 파일 교체마다 무한 증식하던 것 수정")은 mtime 경로만 고쳤고 스레드 사망 경로는 남아 있다.
- **발동 조건**: 대시보드 장기 구동(운영 PC는 상시 구동) + AI 비교 질의 반복.
- **영향**: 파일 핸들·메모리 누적(연결마다 mmap 256MB 설정, Windows 핸들 소모). 수 주 구동 시 수백~수천 개의 열린 ro 핸들이 라이브 DB 파일을 물고 있게 된다. ERP 파일 교체·백업 절차와의 상호작용 리스크 포함.
- **수정 방향**: `_all_connections`를 약참조(`weakref.WeakSet`)로 바꾸거나, 죽은 스레드의 연결을 주기 정리(예: `threading.Thread` 생존 확인 태그). `compare_periods`는 executor 대신 순차 실행(쿼리 2개, 병렬 이득 미미) 또는 모듈 수준 공유 executor로.
- **확신도**: 확실 (참조 체인·스레드 모델 모두 소스로 확인).

### F-04 [Medium] 기간 통계의 평균이 아카이브 경계를 걸치면 비가중 평균으로 왜곡 — AI 답변 수치 오류

- **위치**: `api/tools/summary.py:61-77` (`get_production_summary`의 `outer_select="... AVG(avg_val) AS average"`), 동일 패턴 `api/tools/summary.py:282-295` (`compare_periods._query_stats`)
- **문제**: `build_aggregation_sql`은 아카이브/라이브 각각에서 `AVG(good_quantity) AS avg_val`을 낸 뒤(소스당 1행) 외부에서 `AVG(avg_val)`로 합친다. 이는 **행수 무시한 "평균의 평균"**이다. 예: 아카이브 10,000건 평균 100, 라이브 10건 평균 1,000이면 참평균 ≈ 100.9인데 550이 보고된다. 합계(`SUM(total)`)·건수(`SUM(cnt)`)는 정확하므로 한 응답 안에서 `total/count ≠ average`인 모순 데이터가 나간다.
- **발동 조건**: 조회 기간이 `ARCHIVE_CUTOFF_DATE`(2026-01-01)를 걸칠 때 — "작년부터 지금까지 평균", "올해 vs 작년 비교"(compare_periods의 각 기간이 경계를 걸치는 경우) 등 AI가 흔히 만드는 질의.
- **영향**: AI 챗의 `average_quantity`가 틀린 값으로 답변·표 생성에 사용됨. 월별 집계 계열(`/summary/monthly_total` 등)은 월이 경계를 걸칠 수 없어(컷오프가 1월 1일) 이 왜곡이 **발생하지 않음** — 무그룹 기간 통계 2곳만 문제.
- **수정 방향**: 외부 select를 `SUM(total) * 1.0 / SUM(cnt) AS average`로 (cnt=0 가드 포함).
- **확신도**: 확실 (SQL 구성상 필연).

### F-05 [Medium] execute_custom_query의 LIMIT 가드가 존재 검사뿐 — 값 무제한 + substring 오탐으로 가드 해제

- **위치**: `api/tools/custom.py:211-213`
- **문제**: `if "LIMIT" not in sql_upper: sql_clean += " LIMIT 1000"` 뿐이다. (a) 모델이 `LIMIT 999999`를 쓰면 그대로 통과 — docstring의 "max 1000 rows"는 어디서도 강제되지 않는다. (b) `"LIMIT"`이 문자열 리터럴/식별자 일부로만 등장해도(`WHERE item_name LIKE '%UNLIMITED%'`) 자동 LIMIT이 붙지 않아 전건 반환. (c) `LIMIT ?` + params `["999999"]`도 통과.
- **발동 조건**: 프롬프트로 유도 가능("전체 데이터 다 보여줘" → 모델이 큰 LIMIT 작성). 악의 없이도 모델이 자발적으로 큰 LIMIT을 쓸 수 있음.
- **영향**: 아카이브 25,587행 + 라이브 전체가 도구 결과 dict로 직렬화되어 **Gemini 컨텍스트로 그대로 투입** — 토큰 폭발, 요청 실패/쿼터 소진, 응답 지연. `_run_query_with_timeout`(10초)은 실행 시간만 제한하고 결과 크기는 제한하지 않는다.
- **수정 방향**: fetchmany로 행수 하드캡(예: 1000행) + 초과 시 truncated 플래그를 결과에 명시. LIMIT 문자열 검사는 보조로만.
- **확신도**: 확실.

### F-06 [Medium] GET /records/{item_code}의 limit 무검증 — 음수/거대값으로 전체 덤프

- **위치**: `api/routers/records.py:237-240`
- **문제**: `def get_item_records(item_code: str, limit: int = 5000)` — `Query(ge=..., le=...)` 제약이 없는 유일한 limit 파라미터다(형제 엔드포인트 `/records`는 `le=5000`, `/items`는 `le=2000`). `limit=-1`이면 `build_union_sql`이 `LIMIT -1`을 생성하고 **SQLite에서 LIMIT -1은 무제한**이다. `limit=99999999`도 그대로 통과.
- **발동 조건**: `GET /records/BW0021?limit=-1` 한 번.
- **영향**: 해당 품목 전 이력(아카이브 포함) 무제한 반환 + `@api_cache`가 그 거대 결과를 캐시(200개 슬롯 점유). 내부망 open-access 전제에서 실수/스크립트로 쉽게 발동.
- **수정 방향**: `limit: int = Query(default=5000, ge=1, le=5000)`.
- **확신도**: 확실.

### F-07 [Medium] anomaly `last_scan_ts`가 findings 있을 때만 갱신 — "마지막 발행 스캔"이 정상 운영에서 영구 정지 표시

- **위치**: `api/anomaly/detector.py:170-172` (`if emit and findings: _emit_new(...)`), `last_scan_ts` 갱신은 `_emit_new` 내부(:211)에만 존재
- **문제**: 스캔 결과 findings가 0건(정상 상태의 기본값)이면 `_emit_new`가 호출되지 않아 상태 파일의 `last_scan_ts`가 갱신되지 않는다. 데몬이 매시간 성실히 스캔해도 `/anomaly/state`의 `last_scan_ts`는 마지막으로 이상이 있었던 시점에 멈춰 있다.
- **발동 조건**: 이상이 없는 기간(대부분의 시간).
- **영향**: 이상탐지 대시보드의 "마지막 발행 스캔" 메트릭(views/anomaly.py:96-104)이 "기록 없음"/수일 전으로 표시 → 운영자가 데몬 장애로 오인하거나, 반대로 **실제 데몬 정지를 이 지표로 감지할 수 없다** (관측 지표로서 무의미). F-1(헬스 페이지) 계획이 이 값을 소비하면 오류가 전파된다.
- **수정 방향**: `run_detection`에서 emit 여부·findings 유무와 무관하게 스캔 완료 시 `last_scan_ts` 저장 (상태 파일 쓰기 1회 추가).
- **확신도**: 확실.

### F-08 [Medium] anomaly 쿨다운 상태 파일의 프로세스 간 read-modify-write 경합 — 중복 발행/쿨다운 유실

- **위치**: `api/anomaly/detector.py:187-215` (`_emit_new`: load → filter → emit → mark → save), `api/anomaly/store_state.py` (락 없음)
- **문제**: `POST /anomaly/scan`(API 프로세스)과 `tools/anomaly_watch.py --daemon`(별도 프로세스)이 같은 `.anomaly_state.json`을 락 없이 load→save 한다. 동시 실행 시 (a) 둘 다 같은 finding을 "쿨다운 밖"으로 판정해 **웹훅 중복 발행**, (b) 늦게 저장한 쪽이 먼저 저장한 쪽의 cooldown 마킹을 **덮어써 유실**(다음 스캔에서 또 발행). `save_state`의 atomic replace는 파일 파손만 막고 lost-update는 못 막는다. webhook worker는 "single-process assumption"을 명시했지만 anomaly 상태는 그 가정 문서화도 없이 다중 프로세스에 노출된다.
- **발동 조건**: 데몬 스캔 시각과 운영자의 수동 스캔(대시보드/HTTP)이 겹칠 때. 스캔은 수 초 걸리므로(전 품목 조회) 창이 좁지 않다.
- **영향**: 동일 이상 알림 중복 수신, 쿨다운 무력화. 데이터 파손은 없음.
- **수정 방향**: 상태 파일 옆에 파일락(`msvcrt.locking`/`portalocker`) 또는 발행 경로를 API 프로세스 단일화(데몬이 `POST /anomaly/scan` 호출).
- **확신도**: 유력 (경합 창은 코드상 명백, 실측 재현은 미수행).

### F-09 [Medium] 단건 재발송 API가 상태 무관 requeue — success 재발송·in_flight 이중발송 가능

- **위치**: `api/notifications/deliveries_repo.py:314-335` (`requeue_delivery`), `api/routers/notifications.py:228-235`
- **문제**: 벌크 재시도는 `RETRYABLE_TERMINAL_STATUSES = ("dead", "failure")`로 제한하며 주석에 "in_flight 재큐잉은 이중발송, success는 재전송 위험이라 의도적으로 제외"라고 명시했다. 그런데 **단건 `POST /notifications/deliveries/{id}/retry` → `requeue_delivery`는 존재 여부만 확인**하고 어떤 상태든 `queued`로 되돌린다. success 행을 재발송하거나, worker가 dispatch 중인 in_flight 행을 requeue해 동시 이중발송이 가능하다 — 같은 파일 안에서 스스로 세운 불변식을 깨는 API.
- **발동 조건**: 대시보드/HTTP로 delivery id 하나 지정(전달 이력 화면에서 id는 그대로 노출됨).
- **영향**: 수신처에 중복 webhook (동일 `X-Webhook-Delivery` id지만 수신처가 dedup을 구현했다는 보장 없음). in_flight requeue 시 worker 완료 UPDATE와 경쟁하여 상태 필드가 뒤섞일 수 있음.
- **수정 방향**: `requeue_delivery`에 `WHERE status IN ('dead','failure')` 조건 추가, 미충족 시 409 반환.
- **확신도**: 확실.

### F-10 [Medium] /healthz/ai가 async 핸들러에서 동기 네트워크 호출 — 이벤트 루프 블로킹

- **위치**: `api/routers/system.py:142-196` (`async def ai_health_check` 내 `client.models.list()`)
- **문제**: `ai_health_check`는 `async def`인데 `genai.Client(...)` 생성과 `client.models.list()`(실제 HTTPS 왕복 + 전체 모델 페이지네이션)를 **await/to_thread 없이 직접 호출**한다. 호출 동안 uvicorn 이벤트 루프 전체가 멈춘다.
- **발동 조건**: 캐시(10분) 만료 후 `/healthz/ai` 호출. Gemini 엔드포인트가 느릴 때(장애 시 수 초~타임아웃) 최악.
- **영향**: 블로킹 동안 **모든 HTTP 요청·진행 중 SSE 스트림(하트비트 포함)이 정지**. 헬스체크가 오히려 서비스를 멈추는 역설. 봇 health_checker가 `/healthz`만 쓰는 것은 확인했으나(P0-1 문서), F-1 헬스 페이지가 이 엔드포인트를 소비하게 되면 10분마다 정지가 재발한다.
- **수정 방향**: `await asyncio.to_thread(client.models.list)` 또는 `client.aio.models.list()` 사용. TOCTOU(락 해제 후 이중 핑)도 함께 정리하면 좋으나 부차적.
- **확신도**: 확실.

### F-11 [Medium] 자동화 동시 실행 가드가 데이터셋별로 분리 — /materials/run + /binder/run 동시 봇 2개 기동

- **위치**: `api/materials/automation.py:107-116` (`has_active_automation(runs_table=...)`), `api/materials/runs.py:110-116`
- **문제**: `_trigger_lock`은 "동시 더블클릭으로 봇 2개 기동" 사고를 막으려 도입됐지만, 활성 검사 `has_active_automation`이 **데이터셋별 runs 테이블 단위**다. `/materials/run`과 `/binder/run`을 (다른 페이지에서, 또는 API로) 연달아 호출하면 각자 자기 테이블만 보고 통과 → 같은 PC에서 `webcloring-pdf main.py --auto` 프로세스 2개가 동시에 뜬다. 두 봇은 같은 포털 계정/브라우저 프로필/Excel 이력을 다루는 동일 프로그램이다(키워드만 다름).
- **발동 조건**: 자재 페이지와 바인더 페이지에서 각각 "지금 실행" (MATERIALS_RUN_ENABLED=1 환경).
- **영향**: Selenium 세션·포털 로그인 충돌, 수집 실패 또는 부분 수집 → 백업 데이터 유실 가능. 가드의 존재 이유("봇은 한 번에 하나")를 정면으로 깬다.
- **수정 방향**: 활성 검사를 전 데이터셋 runs 테이블 합집합으로 (registry 순회 한 줄), 또는 프로세스 수준 락 파일.
- **확신도**: 유력 (동시 기동은 코드상 확실; 봇 2개의 실제 충돌 양상은 webcloring-pdf 내부 확인 필요).

### F-12 [Medium] Overview KPI가 limit-절단된 레코드로 계산 — 같은 화면의 월별 차트와 수치 불일치

- **위치**: `dashboard/views/overview.py:149-155`, `dashboard/components/kpi_cards.py:17-85` (`calculate_kpis`)
- **문제**: KPI(총 생산량·배치 수·활성 제품·평균 배치)는 `load_records(..., limit)` 결과 DataFrame으로 계산한다. limit 기본 5,000(사이드바 슬라이더)이고 정렬이 최신순이므로, 기간 내 행수가 limit을 넘으면 **오래된 행이 조용히 잘린 채 합산**된다. 반면 같은 화면의 월별 추세 차트는 `load_monthly_summary`(무제한 집계)를 쓴다 → 한 화면에서 KPI 합계 < 차트 합계. 아카이브가 25,587행이므로 2025년을 포함한 범위 선택 시 기본값으로 즉시 발동한다.
- **발동 조건**: 필터 기간 내 레코드 수 > limit (예: 2025 전체~현재 조회).
- **영향**: 경영 지표 화면의 총량이 실제보다 작게 표시. 잘림 사실이 UI에 표시되지 않아(경고 없음) 신뢰 훼손형 오류. Top10/분포 차트도 동일 df 기반이라 함께 왜곡.
- **수정 방향**: KPI는 집계 SQL(P1-2 `period_summary_query`)로 계산하고 레코드 df는 표시용으로만. 최소한 `len(df) == limit`일 때 "상위 N건만 반영됨" 배지 표시.
- **확신도**: 확실 (행수/limit 관계 실측).

### F-13 [Low] materials upsert가 문서 재수집 시 사라진 품목 행을 남김 — 스테일 행 잔존

- **위치**: `api/materials/store.py:246-306` (`upsert_materials`)
- **문제**: (doc_number, seq) 단위 upsert만 하고 **같은 문서의 기존 행 중 이번 배치에 없는 seq는 삭제하지 않는다**. 문서가 수정되어 품목이 줄었거나 seq가 재배열되면(3행→2행) 옛 seq 행이 영구 잔존해 문서 조회(`get_document`)와 합계가 부풀려진다. 배치 내 dedupe 주석의 "full-snapshot 의도"가 문서 단위로는 관철되지 않는다.
- **발동 조건**: 포털에서 기안 문서가 수정 재수집되는 경우(드묾).
- **영향**: 해당 문서의 품목 수/수량 과다 표시. 자연 치유 없음(삭제 API로 수동 정리만 가능).
- **수정 방향**: upsert 전 `DELETE FROM {table} WHERE doc_number IN (batch_docs) AND (doc_number, seq) NOT IN (incoming)` 또는 문서 단위 delete-then-insert를 한 트랜잭션으로.
- **확신도**: 확실 (동작), 발동 빈도는 낮음.

### F-14 [Low] backup_db.py가 5개 DB 중 2개만 백업 — 유일본인 notifications/anomaly 이력이 무백업

- **위치**: `tools/backup_db.py:216-258` (`main` — `DB_FILE`, `ARCHIVE_DB_FILE`만 처리)
- **문제**: 백업 스크립트는 생산 라이브/아카이브만 대상으로 하고 `notifications.db`(webhook 설정+secret, 전달 이력), `materials.db`, `anomaly.db`는 아예 백업하지 않는다. 01 문서 P0-2가 "notifications/anomaly 이력은 유일본"이라고 지적하면서도 복구 검증에 초점을 맞췄는데, **백업 자체가 없는 파일이 있다는 점**은 별도 결함이다. webhook secret은 분실 시 수신처 재등록이 필요하다.
- **수정 방향**: `run_backup` 대상에 3개 store DB 추가 (backup API 사용 중이라 WAL 안전).
- **확신도**: 확실.

### F-15 [Low] watcher: 아카이브 안정화 실패 시 새 mtime을 저장해 이후 인덱스 점검이 영구 스킵

- **위치**: `tools/watcher.py:147-162, 186-192`
- **문제**: 아카이브 변경 감지 → `wait_for_stabilization` 실패 시 heal을 건너뛰는데, 함수 상단에서 읽은 **새 mtime/size가 그대로 state에 저장**된다. 다음 사이클엔 "Archive DB unchanged"가 되고, 라이브와 달리 아카이브의 unchanged 분기는 주기 점검(`check_and_heal_indexes`)을 **하지 않으므로**, 다음 실제 파일 변경(연 1회 수준)까지 인덱스 점검이 영영 스킵된다.
- **발동 조건**: 아카이브 교체 직후 워처 사이클과 겹칠 때 1회.
- **영향**: 아카이브 인덱스 유실 시 복구 지연 → 조회 성능 저하가 조용히 지속.
- **수정 방향**: 안정화 실패 시 state에 **이전 mtime을 유지**해 다음 사이클에 재시도, 또는 아카이브 unchanged 분기에도 주기 점검 추가.
- **확신도**: 확실.

### F-16 [Low·잠재] anomaly 일별 집계가 `GROUP BY production_date` (전체 문자열) — 시간 성분이 생기는 순간 규칙 붕괴

- **위치**: `api/anomaly/detector.py:30-38` (`_fetch_daily_totals`)
- **문제**: docstring은 "Daily totals"라지만 실제로는 datetime 문자열 전체로 GROUP BY 한다. 현재 데이터는 시간부가 전 행 `"오전 12:00:00"` 고정이라(실측: distinct 전체 = distinct 일자 = 20) 우연히 일별과 같다. 그러나 ERP가 실제 시각을 쓰기 시작하면(코드베이스의 `_parse_production_dt`가 오전/오후 시각 파싱을 지원하는 것 자체가 그 가능성의 방증) 배치 1건 = 버킷 1개가 되어 급감/급증 판정이 "직전 배치 vs 배치 평균"으로 변질된다 — 오탐 폭주 또는 전면 미탐.
- **수정 방향**: `GROUP BY substr(production_date, 1, 10)` (다른 모듈과 동일 관례). `latest["date"]`를 메시지/키에 쓰는 부분도 10자 절단.
- **확신도**: 확실 (잠재 결함; 현 데이터에서는 미발동임을 실측 확인).

### F-17 [Low] 챗 SSE 클라이언트: ConnectError 재시도가 "토큰 미수신" 조건을 확인하지 않음

- **위치**: `dashboard/components/ai_section.py:128-147` (`_stream_chat_tokens`)
- **문제**: docstring은 "no tokens have been yielded yet일 때만 재시도(중복 텍스트 방지)"라 하고 ReadTimeout 분기는 `not tokens_yielded`를 확인하지만, **ConnectError 분기는 확인 없이 재시도**한다. httpx에서 토큰 수신 후 ConnectError는 사실상 없지만, 프록시/리다이렉트 구성 변화 시 중복 답변 렌더 가능성이 열려 있고 계약(주석)과 코드가 다르다.
- **수정 방향**: ConnectError 분기에도 `not tokens_yielded` 조건 추가 (1줄).
- **확신도**: 확실 (코드 불일치), 실피해 가능성 낮음.

---

## 3. 수색했지만 문제를 찾지 못한 영역 (범위 증빙)

아래는 실제로 정독·교차검증했으나 결함을 발견하지 못한 영역이다. "안전 확인"이지 "무결 보증"은 아니다.

| 영역 | 확인 내용 |
|---|---|
| **SSE 스트림 자원 정리** (`api/_chat_stream.py`) | `_iter_with_heartbeat`의 pending `__anext__` cancel, `_consume_stream` finally의 `stream.aclose()`, `contextlib.aclosing` — 타임아웃/클라이언트 절단/예외 3경로 모두 누수 없음. 타임아웃·부분 실패 시 세션 미저장 규칙도 일관 |
| **AFC 도구의 이벤트 루프 안전성** | google-genai 2.8.0 async AFC는 동기 도구를 `asyncio.to_thread`로 실행함을 SDK 소스로 확인(`_extra_utils.py:404`) — `execute_custom_query`의 10초 쿼리도 루프를 막지 않음 |
| **execute_custom_query 4중 방어** | 주석 제거 → 세미콜론 → SELECT-only → 금칙어(워드바운더리+`PRAGMA_` 등 substring) → `production_records` 참조 강제 → mode=ro 전용 연결 + interrupt 타임아웃. 우회 시도(주석 은닉, pragma_table_info, ATTACH)로 검증 — LIMIT 건(F-05) 외 통과 못함. 타임아웃 시 연결 GC 위임은 문서화된 의도적 결정 |
| **webhook 비동기 큐** (`deliveries_repo.py`, `worker.py`, `backoff.py`) | claim(BEGIN IMMEDIATE + rowcount 확인)·orphan 회수(lease)·shutdown 중 release·백오프 스케줄·Retry-After 캡 모두 정합. 타임스탬프는 `_now_iso()`가 UTC-aware로 통일되어 queue_stats/메트릭의 24h 창도 일관(초기 의심했으나 반박됨) |
| **dispatcher 응답 바디 폭주 방어** | 16KB 스트리밍 캡 후 1KB 저장 — GB급 응답에도 안전. HMAC 서명·헤더 구성 정상 |
| **인증/감사 계층** (`shared/auth.py`, `api/_audit.py`, `main.py` 미들웨어) | 상수시간 비교(전 후보 순회), 마스킹, PUBLIC_PATHS SSOT, 미들웨어 순서(request_id가 outer) 정합. auth ON + 무자격 시 fail-closed |
| **rate limiter** | 슬라이딩 윈도우 원자성(is_allowed가 check+record), cleanup 스캔 바운드, chat 리미터의 별도 정리 경로 확인 |
| **cursor 페이지네이션** (`records.py`) | 커서 인코딩 shape 검증, (date, source, id) 3키 커서와 ORDER BY 방향 일치, limit+1 has_more 패턴 정상 |
| **세션 스토어** (`_session_store.py`) | IP 바인딩 격리, per-IP/전체 축출 산식(`len - MAX + 1`), TTL lazy cleanup 정상 |
| **캐시 계층** (`shared/cache.py`) | mtime 기반 무효화 + 1s mtime 캐시 + TOCTOU double-check, 키 충돌 없음 |
| **materials upsert 산식** | 배치 내 dedupe(last-write-wins), inserted/updated 카운트의 500개 청크 IN 조회, doc_date 파생(YYYYMMDD 검증), NULL doc_date의 DESC 정렬 위치(마지막) — F-13 외 정상 |
| **월별 집계의 경계 안전성** | 컷오프가 1월 1일이라 어떤 월/일 버킷도 두 DB에 걸치지 않음 — `AVG(avg_val)` 왜곡(F-04)이 월별 계열에는 없음을 확인 |
| **webhook URL SSRF 가드** | 스킴 제한, loopback/link-local/metadata IP 차단, ipv4_mapped 우회 처리 — 내부망 전제에서 합리적 |
| **backup_db 백업 방식** | sqlite3 backup API 사용(WAL 중 파일 복사 아님) + quick_check 검증 + 실패 시 부분 파일 삭제 — 대상 누락(F-14) 외 절차 자체는 견고 |
| **ATTACH 화이트리스트** (`_db_attach.py`) | resolve 후 화이트리스트 대조, 바인딩 우선 + 검증된 경로만 문자열 폴백 |
| **LIKE escape** | `escape_like_wildcards` 백슬래시 선처리 순서 정상, 전 호출부 ESCAPE '\' 일치 |

---

## 4. 우선 조치 권고 순서

1. **F-01** — 폴백/재시도 판정 수정 + 실오류 형태 테스트 (P1-1 `_chat_core` 추출의 선행 근거로 승격 권장: "정책이 이미 죽어 있음"이 확인됐으므로 A-7의 착수 조건이 충족됨)
2. **F-02** — 주별 집계 substr 수정 (1줄) + 실형식 fixture
3. **F-03** — 연결 누수 (WeakSet 전환 + compare_periods executor 제거)
4. **F-06, F-09, F-05** — 저비용 검증 강화 3건 (각 1~5줄)
5. **F-04, F-12** — 수치 정확성 2건은 P1-2 `shared/queries.py` 사이클에 편입
6. 나머지 Medium/Low는 각 서브시스템의 다음 정기 사이클에 배치
