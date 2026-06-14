# webcloring-pdf-separation — Gap Analysis

> **Cycle**: webcloring-pdf-separation
> **PDCA Phase**: Check
> **Date**: 2026-06-15
> **Plan**: [[webcloring-pdf-separation.plan]]
> **Match Rate**: **100%** (AC 7/7)
> **범위 주의**: 사용자 선택 "준비만" — outward 단계(repo 생성·push·submodule add)는 의도적으로 미실행, 절차서로 핸드오프. AC는 in-repo 준비 작업 기준.

## AC별 검증

| # | Criterion | 실측 결과 | 판정 |
|---|-----------|-----------|:----:|
| AC1 | requirements.txt portal 5개 제거, psutil 잔류(블록 밖) | selenium/webdriver-manager/google-api-python-client/google-auth-httplib2/google-auth-oauthlib grep 0건, `psutil` 별도 블록 + 주석 | ✅ |
| AC2 | lock 재생성, selenium/webdriver 제거, google-auth 잔류 근거 | 새 lock: portal 직접5+전이(trio/wsproto/outcome/trio-websocket 등) 제거. **google-auth==2.54.0 잔류 = google-genai(Gemini) 전이로 확인**(수동 삭제였으면 앱 붕괴). 95→79 핀 | ✅ |
| AC3 | cleaned venv 설치 후 import smoke | fresh py3.12 venv에서 `import api.main; shared; process_utils; api._gemini_client` 성공 | ✅ |
| AC4 | main 376 green + ruff + CI | cleaned venv(pytest 9.1.0) **376 passed**, ruff clean, CI(아래) | ✅ |
| AC5 | SEPARATION.md outward 5단계+검증+롤백 | `SEPARATION.md`: git init→gh repo create→git rm --cached→submodule add→검증, +사전조건/롤백/일상작업 | ✅ |
| AC6 | README submodule 안내 | 설치 §1에 `--recurse-submodules`/`submodule update --init` + SEPARATION.md 링크 | ✅ |
| AC7 | match rate ≥ 90% | 100% | ✅ |

## 핵심 검증 — google-auth 오제거 회피

Plan §6의 최대 리스크였던 "google-auth 수동 삭제 시 Gemini 붕괴"를 **freeze 재생성으로 자동 판정**: cleaned requirements(selenium 등 5개 제거)로 fresh 설치 후 freeze하니 google-auth가 **잔류** → google-genai 전이 의존 확정. import smoke가 실증. 수동 라인 삭제 방식이었으면 놓쳤을 위험.

## surfaced & fixed — pytest 9.1 strict-markers

lock freeze가 pytest **9.0.3 → 9.1.0**으로 자동 상향했고, 9.1이 `--strict-markers`에서 미등록 `timeout` 마커(`test_process_utils.py:18`)를 경고가 아닌 **collection 에러**로 처리 → 새 lock으로는 CI 붕괴. 잠복 이슈(마커는 원래 미등록, pytest-timeout 미설치)를 내 lock 재생성이 노출. **마커 등록**(pyproject `markers`, addopts/select/source 불변)으로 근본 수정 — pytest 9.0/9.1 양쪽 green.

## 미실행 (사용자 핸드오프, gap 아님)

outward 5단계는 사용자 선택에 따라 SEPARATION.md로만 제공. 분리 미완료 상태에서 main repo는 여전히 webcloring-pdf 50파일 포함하나 requirements는 portal-free + webcloring 자체 requirements 보유 → 무해. 절차서가 후속 가이드.

## 권장 조치

없음 — **100% → Report.** 후속: 사용자가 SEPARATION.md로 outward 단계 실행. (선택) pytest-timeout을 dev 의존성으로 추가해 timeout 마커를 실제 강제.
