# Archive Index - 2026년 6월

> 이 폴더는 2026년 6월에 완료된 PDCA 사이클의 문서를 보관합니다.

## 📁 아카이브 목록

### 11. 커버리지 사각지대 v2 (coverage-blindspots-v2)
- **완료일**: 2026-06-15
- **상태**: ✅ 완료 (Match Rate 100%, AC 7/7)
- **요약**: dashboard `kpi_cards.py` 순수함수 5개(calculate_kpis/get_sparkline_data/get_sparkline_for_top_product/_format_number/_has_signal) 단위 테스트 + coverage 측정 포함(88%, omit 화이트리스트에서 제거). `tools/watcher.py` load_state/save_state 단위 테스트(STATE_FILE monkeypatch, test-only — run_check IO는 floor 보호 위해 source 미추가). 376→389 tests, TOTAL 75→76%, floor 72 유지(인플레 자제). 교훈: 파일의 순수도가 측정 포함 단위를 가른다.
- **문서**: plan / analysis / report

### 10. ruff E501 게이트 램프 (R7-ruff-e501-ramp)
- **완료일**: 2026-06-15
- **상태**: ✅ 완료 (Match Rate 100%, AC 7/7)
- **요약**: ruff 게이트에 E501(line-too-long, 100) 추가. **`ruff format` 미도입**(85/99 파일 재포맷 회피, blame 보존 — 사용자 결정). 99건 분류: code/ascii ~45건(15파일) 수동 래핑(SQL paren+concat 공백보존, f-string 분할, 시그니처/dict/list 줄바꿈, CSS 셀렉터 개행, noqa 0), 한글 프롬프트/UI 5파일(chat/ai_section/views/presets/portal_settings)+테스트 JSON 3파일은 per-file-ignore(한글 East-Asian-width 2라 래핑해도 재위반·의미훼손). 376 green. R6 후속. 잔여 C901은 R8.
- **문서**: plan / analysis / report

### 9. ruff B+SIM 게이트 램프 (R6-ruff-bugbear-sim-ramp)
- **완료일**: 2026-06-15
- **상태**: ✅ 완료 (Match Rate 100%, AC 7/7)
- **요약**: ruff 게이트를 `B`(bugbear 전체)+`SIM`(simplify)로 확장(select=F/BLE001/I/UP/B/SIM). 위반 41건 해소 — src B905(strict=True)/B025/B007 코드 수정, tests B017 per-file-ignore(broad raises 관용), SIM105 17건 contextlib.suppress(주석 보존), SIM117/300/102/108 autofix+수동. **B025가 db_maintenance.py 실버그 발견**(중복 `except sqlite3.Error` 도달불가 → 주석 의도대로 `except Exception` 복원). 376 green. R3→R5 후속. 잔여 E501/C901은 R7+.
- **문서**: plan / analysis / report

### 8. 커버리지 측정 범위 확장 (coverage-source-expansion)
- **완료일**: 2026-06-15
- **상태**: ✅ 완료 (Match Rate 100%, AC 6/6)
- **요약**: coverage-blindspots-v1에서 추출한 `dashboard/components/_parsing.py`(테스트된 순수 헬퍼)를 coverage 측정에 추가(90%), 렌더 코드는 omit 화이트리스트로 제외. floor 66→72(실측 75.14% −3pp). dashboard 전체(15%)는 floor 상향과 충돌해 선별 측정(사용자 결정). `--cov=file.py`/`source=[file]`이 importlib 로드를 "never imported"로 흘리는 함정 → `source=dir + omit 화이트리스트`로 해결. ci-and-env "source 불변" 불변식 의도적 해제.
- **문서**: plan / analysis / report

### 7. webcloring-pdf submodule 분리 준비 (webcloring-pdf-separation)
- **완료일**: 2026-06-15
- **상태**: ✅ 완료 (Match Rate 100%, AC 7/7) — outward 단계는 사용자 핸드오프(SEPARATION.md)
- **요약**: 2026-05 결정 실행. 사용자 선택 "준비만, push는 사용자". main `requirements.txt`에서 portal 전용 5개(selenium/webdriver-manager/google-api-python-client/google-auth-httplib2/google-auth-oauthlib) 제거(psutil은 process_utils용 잔류), `requirements.lock.txt` fresh freeze 재생성(95→79 핀) — **google-auth는 google-genai(Gemini) 전이로 자동 잔류**(수동 삭제 오제거 회피). freeze가 pytest 9.0.3→9.1.0 올려 노출된 strict-markers 이슈를 `timeout` 마커 등록으로 근본 수정. cleaned venv 376 green + import smoke. outward 5단계는 루트 `SEPARATION.md` 절차서로. design은 plan에 통합(compact).
- **문서**: plan / analysis / report (+ 루트 SEPARATION.md 운영문서)

### 6. 커버리지 사각지대 (coverage-blindspots-v1)
- **완료일**: 2026-06-14
- **상태**: ✅ 완료 (Match Rate 100%, AC 8/8)
- **요약**: 사각지대를 2종 분리 — (A) measured(api+shared)의 0% 파일은 **죽은 코드**(`shared/utils/data_helpers`+`date_helpers`, import 0건)였어서 삭제 → 72%→75%. (B) unmeasured(dashboard)의 brittle 로직(AI 마크다운 표 파싱·SSE 이벤트 파싱)을 streamlit-free `_parsing.py`로 추출(로직 1:1)하고 13개 characterization 테스트(importlib 격리)로 회귀 가드. 363→376 tests. pyproject source/floor 불변. 통찰: 0% 파일은 "테스트 대상"이 아니라 "분류 대상(삭제 vs 테스트)".
- **문서**: plan / design / analysis / report

### 5. flaky 제거: RateLimiter clock + bulk_retry 격리 (rate-limiter-clock-injection)
- **완료일**: 2026-06-13
- **상태**: ✅ 완료 (Match Rate 100%, AC 7/7)
- **요약**: 두 flaky 원천 제거 — (A) `RateLimiter`에 `clock` 주입(worker.py 선례)으로 sleep 4테스트를 FakeClock화(5.3s→0.21s, 경계 테스트 추가), (B) bulk_retry 간헐 실패(누적 4회)의 근본 원인 규명: `test_worker_stop_timeout_does_not_raise`의 누출 데몬 워커가 1.5s 느린 핸들러 반환 시 `NOTIFICATIONS_DB_FILE`을 전역 재해석 → 나중 테스트의 isolated_db(동일 id=1)에 success 기록. 타겟(스레드 드레인)+방어(conftest autouse 가드) 2중 수정. baseline 2/10 실패 → 10/10 green(363 passed). 제품 결함 아님(테스트 격리).
- **문서**: plan / design / analysis / report

### 4. 콜드 딥링크 라우팅 픽스 (nav-routing-fix-v1)
- **완료일**: 2026-06-11
- **상태**: ✅ 완료 (Match Rate 100%, AC 7/7)
- **요약**: ui-design-overhaul-v1 O1 해소 — `pages/` 디렉터리 존재만으로 활성화되는 Streamlit v1 유산 플래그(`uses_pages_directory`, 1.58 소스 규명)가 콜드 딥링크를 v1 라우팅(`_mpa_v1`)으로 보내 app.py를 우회. `dashboard/pages/`→`views/` 개명으로 근본 해소(URL 불변). 콜드 딥링크 Playwright 실측 PASS + `test_no_legacy_pages_directory` 재발 가드. 361→362 tests, CI run 27355978686.
- **문서**: plan / design / analysis / report

### 3. UI/디자인 대폭 개선 (ui-design-overhaul-v1)
- **완료일**: 2026-06-11
- **상태**: ✅ 완료 (Match Rate 100%, AC 10/10)
- **요약**: Pink/Sky 커스텀 CSS 체제 → 산업용 블루/슬레이트 + Streamlit 네이티브 테마(config.toml SSOT, light+dark, 설정 메뉴 토글). theme.py 351→99줄, KPI 카드 `st.metric(border+chart_data)` 네이티브화, 전 표면 Material 아이콘, unsafe_allow_html 18→5곳, 핑크 hex 잔재 0. Playwright 시각검증 10장(라이트/다크), 361 green + CI run 27349353535. 부수 발견: 1.58 변형 섹션 키 제약(D1), 콜드 딥링크 라우팅 우회(O1, 후속).
- **문서**: plan / design / analysis / report

### 2. 검토 Quick wins 4건 (review-quickwins-202606)
- **완료일**: 2026-06-10
- **상태**: ✅ 완료 (Match Rate 100%, AC 8/8)
- **요약**: ①rate-limit 공개경로를 `shared.auth.PUBLIC_PATHS` SSOT로 통일(+집합 단위 재발방지 테스트) ②`cache.py` id() 가드 의도 주석 — 재검증으로 "죽은 가드" 결론 정정(`@patch` 감지용 실동작) ③인덱스 도구를 `db_maintenance.REQUIRED_INDEXES`(6종)로 통합, 구버전 `create_index.py` 삭제 ④`chat.py` 미사용 wrapper+거짓 주석 제거. 360 → 361 tests, CI run 27267105258 green.
- **문서**: plan / design / analysis / report

### 1. CI 파이프라인 + 환경 표준화 (ci-and-env-standardization)
- **완료일**: 2026-06-10
- **상태**: ✅ 완료 (Match Rate 98%, AC 9/9)
- **요약**: GitHub Actions CI 신설 — lint(ruff lock-pinned)+test(pytest) 2-job, coverage floor 66% CI 전용, 러너용 빈 fixture DB step. 고아 WSL venv → Windows py3.12.12 정본 venv 재구축, `requirements.lock.txt` 99핀(runtime+dev). S1~S3 로컬 시뮬레이션 선검증으로 첫 run green (27261502491, lint 8s/test 1m4s). README 환경/CI 절 동기화.
- **문서**: plan / design / analysis / report
