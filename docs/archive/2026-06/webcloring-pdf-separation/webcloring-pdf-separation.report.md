# webcloring-pdf-separation Completion Report

> **Summary**: webcloring-pdf submodule 분리를 **준비** — main requirements/lock에서 portal 전용 의존성 제거(psutil 잔류), lock freeze 재생성으로 google-auth 오제거 회피, 사용자 실행용 SEPARATION.md 절차서 작성. 비가역·외부 단계(repo 생성·push·submodule add)는 사용자 핸드오프.
>
> **Project**: Server_API (Production Data Hub)
> **Date**: 2026-06-15
> **Match Rate**: 100% (AC 7/7 PASS)
> **Status**: Completed (in-repo 준비) / outward 단계 사용자 대기

---

## 1. 변경 요약

| ID | 변경 | 파일 | 커밋 |
|----|------|------|------|
| D1 | requirements.txt: portal 5개 제거(selenium/webdriver-manager/google-api-python-client/google-auth-httplib2/google-auth-oauthlib), psutil 재배치 | `requirements.txt` | 9269c8b |
| D2 | requirements.lock.txt: fresh py3.12 freeze 재생성 (95→79 핀, portal 직접+전이 제거, google-auth는 Gemini 전이로 자동 잔류) | `requirements.lock.txt` | 9269c8b |
| D3 | pyproject: `timeout` 마커 등록 (pytest 9.1 strict-markers 대응, addopts/select/source 불변) | `pyproject.toml` | 9269c8b |
| H1 | SEPARATION.md: outward 5단계 + 검증 + 롤백 + 일상작업 절차서 | `SEPARATION.md` | 754bf19 |
| H2 | README: webcloring-pdf submodule 설치 안내 | `README.md` | 754bf19 |

## 2. 검증 결과

- ✅ AC1~AC7 전부 PASS (**100%**)
- ✅ portal 의존성 제거 후 **cleaned venv에서 376 passed** + import smoke(api.main/shared/process_utils/gemini) — 메인 앱이 selenium/google-api 없이 완전 동작
- ✅ **google-auth 오제거 회피**: freeze 재생성으로 google-genai(Gemini) 전이임을 자동 확인 (수동 삭제 리스크 차단)
- ✅ ruff 클린, CI run green (재생성 lock의 Linux 설치 검증)
- ✅ 코드 로직 변경 0 (deps/문서/마커 등록만), manager.py 무수정

## 3. PDCA 메타데이터

```yaml
cycle: webcloring-pdf-separation
phase: completed
match_rate: 100
plan: docs/archive/2026-06/webcloring-pdf-separation/webcloring-pdf-separation.plan.md
design: (compact, plan에 통합)
analysis: docs/archive/2026-06/webcloring-pdf-separation/webcloring-pdf-separation.analysis.md
report: docs/archive/2026-06/webcloring-pdf-separation/webcloring-pdf-separation.report.md
duration_h: 1.0
trigger: 2026-05-19 submodule 분리 결정 실행 (사용자: 준비만, push는 사용자)
outward_status: pending-user (SEPARATION.md)
```

## 4. 사용자 후속 작업 (SEPARATION.md)

1. `cd webcloring-pdf && git init -b main` + 첫 커밋 (push 전 `git status`로 .env/google키/dist 제외 확인)
2. `gh repo create <owner>/webcloring-pdf --private --source . --push`
3. 부모: `git rm -r --cached webcloring-pdf`
4. `git submodule add <url> webcloring-pdf` + 커밋 (폴더 제자리 → manager 무수정)
5. 검증: `git submodule status`, manager Portal 패널 동작, `git submodule update --init` 재현

## 5. 후속 사이클 권장

| Item | 사이클 | 우선순위 |
|------|--------|---------|
| (사용자) SEPARATION.md outward 단계 실행 | — | 사용자 |
| pytest-timeout dev 의존성 추가 → timeout 마커 실제 강제 | test-timeout-enforce | Low |
| coverage source에 dashboard 추가 + floor 상향 | coverage-source-expansion | Medium |
| R6 린트 램프 (B나머지+SIM) | R6-ruff-bugbear-sim-ramp | Medium |

## 6. Lessons Learned

- **transitive 의존은 수동 삭제 말고 freeze로 판정** — google-auth는 portal(google-api)과 Gemini(google-genai) 양쪽이 의존할 수 있었다. lock 라인을 손으로 지웠으면 Gemini를 깰 뻔. fresh-venv freeze는 "실제 필요한 폐쇄"를 자동 계산한다 — 이게 freeze-기반 lock의 핵심 가치.
- **lock 재생성은 숨은 버전 상향을 동반한다** — freeze가 pytest 9.0.3→9.1.0을 올렸고, 9.1의 strict-markers 강화가 잠복 마커 이슈를 드러냈다. lock 갱신 후엔 "무엇이 같이 올랐나"를 보고 새 동작을 흡수해야 한다. (cleaned venv로 전체 스위트를 돌린 게 이걸 push 전에 잡았다.)
- **비가역·외부 작업은 절차서로 핸드오프** — repo 생성·push는 한 번 하면 되돌리기 어렵고 소유·공개여부 결정이 필요하다. in-repo 준비(가역)와 outward(비가역)를 가르고, 후자는 검증·롤백 포함 절차서로 넘기는 게 안전. 사용자가 통제권을 쥔다.
- **폴더 제자리 submodule** — manager가 경로를 하드코딩한 하위프로세스 실행 구조라, submodule을 같은 경로에 두면 호출부 무수정. 분리의 결합도 비용을 0으로 만드는 패턴.
