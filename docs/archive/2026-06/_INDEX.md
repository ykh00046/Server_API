# Archive Index - 2026년 6월

> 이 폴더는 2026년 6월에 완료된 PDCA 사이클의 문서를 보관합니다.

## 📁 아카이브 목록

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
