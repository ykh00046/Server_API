# webcloring-pdf-separation — Plan

> **Cycle**: webcloring-pdf-separation
> **PDCA Phase**: Plan
> **Date**: 2026-06-15
> **Project**: Production Data Hub
> **Summary**: webcloring-pdf(INTEROJO 포털 자동화, 독립 PySide6 앱)의 git submodule 분리를 **준비**한다 — main `requirements.txt`/`requirements.lock.txt`에서 portal 전용 의존성을 제거(psutil 잔류)하고, 비가역·외부 단계(repo 생성·push·submodule add)는 사용자 실행용 절차서(`SEPARATION.md`)로 핸드오프. **이번 사이클은 in-repo 가역 작업만.**

## 1. Background

2026-05-19 결정([[project_structure_cleanup_202605]]): webcloring-pdf를 **git submodule**로 분리하되 폴더는 `Server_API/webcloring-pdf/` 제자리 유지(manager.py가 하위프로세스 경로 3곳 하드코딩 — 폴더 이동 시 Portal 패널 붕괴). 코드 import 결합 없음. outward 단계는 사용자 몫으로 명시.

2026-06-15 사용자 재확인: **실행 범위 = "준비만, push는 사용자"**. 따라서 이 사이클은 git init/`gh repo create`/push/`submodule add`를 **수행하지 않고** 절차서로만 남긴다.

실측(2026-06-15):
- webcloring-pdf는 별도 repo 아님 — main repo에 **50개 트래킹 파일**(src 30, docs 7, 기타). dist/build/logs/.env는 이미 gitignore(미트래킹).
- webcloring-pdf/.gitignore는 완비(data/logs/build/dist/.env/google 키) — submodule 전환 시 그대로 동반, 하드닝 불필요.
- `src/config/config.json`: 내부 포털 URL·설정만, **시크릿 없음**(이메일/비번 빈 값).
- 의존성 결합: main 앱에서 selenium/google-api 계열 import **0건**(테스트 포함). **psutil만 `shared/process_utils.py`가 사용** → main 잔류 필수. `from google`는 전부 google-genai(Gemini), 별개.
- main `requirements.lock.txt`에 portal 의존성 10줄(직접 5 + 전이 5). `google-auth`는 Gemini도 의존 가능성 → **수동 삭제 금지, freeze 재생성으로 자동 판정**.

## 2. Goal

1. **requirements.txt 정리**: "Portal Automation" 블록의 5개(selenium, webdriver-manager, google-api-python-client, google-auth-httplib2, google-auth-oauthlib) 제거. **psutil은 메인 런타임 의존성으로 재배치**(블록 밖, 주석 정정).
2. **requirements.lock.txt 재생성**: 정리된 requirements로 **임시 py3.12 venv에서 freeze**([[project_ci_env_standardization]] §1.2 절차). Gemini가 google-auth를 필요로 하면 전이로 자동 잔류 — 수동 삭제의 오제거 위험 회피.
3. **SEPARATION.md 절차서**: 사용자가 실행할 outward 단계를 검증 가능한 순서로 문서화(git init → gh repo create → push → 부모 폴더 제거 → submodule add + 롤백/검증).
4. **README 갱신**: webcloring-pdf 설치는 분리된 submodule 기준임을 명시(`git submodule update --init`).
5. **회귀 0**: main 376 테스트 green + ruff + CI green. 정리된 lock으로 설치해도 main 앱 정상.

## 3. Non-Goals (defer / 사용자 실행)

- **outward 단계 전부**: `git init`, `gh repo create`, push, 부모 `git rm --cached webcloring-pdf`, `git submodule add` — 사용자 몫(절차서 제공).
- **webcloring-pdf 내부 코드/구조 변경** — 분리 대상일 뿐, 손대지 않음.
- **manager.py 수정** — 폴더 제자리 유지로 무수정(설계 전제).
- **data/debug_page.html 등 webcloring 트래킹 정리** — submodule 후 그쪽 repo에서.

## 4. Scope

| 구분 | 대상 |
|---|---|
| **수정** | `requirements.txt`(5 제거+psutil 재배치), `requirements.lock.txt`(재생성), `README.md`(submodule 안내) |
| **신규** | `SEPARATION.md`(또는 `docs/webcloring-pdf-separation.md`) 절차서 |
| **불변** | webcloring-pdf/ 내용, manager.py, api/shared/dashboard 코드 |
| **사용자 실행(문서만)** | repo 생성·push·submodule 전환 |

## 5. Acceptance Criteria

| # | Criterion | 측정 |
|---|-----------|---|
| AC1 | requirements.txt에 selenium/webdriver-manager/google-api-python-client/google-auth-httplib2/google-auth-oauthlib 0건, psutil 잔류(블록 밖) | grep |
| AC2 | requirements.lock.txt 재생성 — selenium/webdriver-manager 제거 확인. google-auth는 Gemini 의존 시 잔류(freeze 결과 그대로, 근거 기록) | grep + 설치 검증 |
| AC3 | 정리된 lock으로 임시 venv 설치 후 main import smoke(api.main/shared) 성공 | python -c |
| AC4 | main 376 테스트 green + ruff 클린 + CI green | pytest/Actions |
| AC5 | SEPARATION.md에 outward 5단계 + 검증 + 롤백 절차 기재 | 파일 |
| AC6 | README에 webcloring-pdf submodule 설치 안내 추가 | diff |
| AC7 | gap match rate ≥ 90% | Check |

## 6. Constraints / Risks

- **google-auth 오제거 위험**: Gemini(google-genai)가 google-auth를 전이 의존하면 수동 삭제 시 main 앱 붕괴. → freeze 재생성으로 자동 판정 + AC3 import smoke로 실증.
- **lock 재생성의 transitive churn**: freeze는 전이 핀도 최신으로 갱신될 수 있음 → diff가 portal 제거 외로 번질 수 있음. 임시 venv를 **현 lock 기준 설치 후 5개만 uninstall → freeze** 방식으로 churn 최소화(또는 cleaned requirements 설치 후 diff 검토해 portal 관련만인지 확인).
- **분리 미완료 상태의 일관성**: 이 사이클 후 main repo는 여전히 webcloring-pdf 50파일을 포함하나 requirements는 portal-free. webcloring-pdf는 자체 requirements.txt 보유라 무해. 절차서가 후속 outward 단계를 명확히 가이드.
- 커밋 분리([[feedback_commit_style]]): (a) requirements+lock, (b) SEPARATION.md+README.

## 7. Out-of-band Notes

- outward 단계는 [[feedback_powershell_text_mangling]] 주의(절차서 ASCII/UTF-8).
- 메모리 참조: [[project_structure_cleanup_202605]](분리 결정), [[project_ci_env_standardization]](lock 재생성 절차·psutil), [[feedback_commit_style]]
