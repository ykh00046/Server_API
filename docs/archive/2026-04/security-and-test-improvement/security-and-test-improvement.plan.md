---
template: plan
version: 1.2
feature: security-and-test-improvement
date: 2026-04-14
author: interojo
project: Production Data Hub (Server_API)
version_project: v8
---

# 보안·테스트 개선 Planning Document

> **Summary**: 전체 코드 검토(2026-04-14)에서 도출된 Top 5 이슈(비밀정보 노출, 통합 테스트 부재, Chat 세션 메모리 누수, Custom Query 강화, 대형 함수 분리)를 단일 PDCA 사이클로 해소한다.
>
> **Project**: Production Data Hub
> **Version**: v8
> **Author**: interojo
> **Date**: 2026-04-14
> **Status**: Draft

---

## 1. Overview

### 1.1 Purpose

프로덕션 운영 전 단계에서 **보안 구멍을 막고, 회귀 방지용 테스트 안전망을 확보**하며, **장시간 실행 안정성**을 확보한다. 동시에 일부 대형 함수의 복잡도를 낮춰 유지보수성과 테스트 용이성을 높인다.

### 1.2 Background

2026-04-14 전체 프로젝트 검토 결과 아키텍처·설계 수준은 높으나 다음과 같은 프로덕션 리스크가 식별됨:

- `.env` 내 Gemini API 키 평문 저장 / VCS 유출 가능성
- API 엔드포인트에 대한 통합 테스트 부재 (unit 107개만 존재)
- `api/chat.py` 세션 저장소가 IP 구분 없이 전역 제한만 두어 DoS·메모리 누수 위험
- `execute_custom_query()`의 ATTACH 경로 이스케이프·3초 타임아웃이 프로덕션 쿼리에 부적합
- `chat_with_data()` 350줄, `execute_custom_query()` 145줄 등 단일 책임 위반

### 1.3 Related Documents

- 전체 검토 결과: 대화 내 2026-04-14 리뷰(본 Plan의 상위 컨텍스트)
- README: `/README.md`
- 변경 로그: `docs/04-report/changelog.md`
- 운영 매뉴얼: `docs/specs/operations_manual.md`
- 관련 선행 Plan: `docs/01-plan/features/server-api-consistency-and-smoke.plan.md`, `sql-tests-and-multiturn-chat.plan.md`

---

## 2. Scope

### 2.1 In Scope

- [ ] **S1. 비밀정보 분리**: `.env` 템플릿화(`.env.example`), `.gitignore` 검증, 키 로드 실패 시 명확한 에러
- [ ] **S2. API 통합 테스트**: FastAPI `TestClient` 기반 `/records`, `/summary/*`, `/healthz*`, `/chat/`(Gemini mock) 엔드포인트 회귀 테스트
- [ ] **S3. Chat 세션 누수 차단**: IP당 최대 세션 수 제한, 세션 TTL(예: 30분) 명시, LRU evict 로직 정리
- [ ] **S4. Custom Query 안전장치**: ATTACH 경로를 `sqlite3` URI/파라미터 방식 또는 사전 화이트리스트로 치환, 타임아웃 3→10초 조정, 경로 검증 `pathlib` 기반으로 재작성
- [ ] **S5. 대형 함수 리팩토링**: `chat_with_data()`, `execute_custom_query()` 를 helper로 분리(도구 디스패치, 재시도, 응답 정규화)

### 2.2 Out of Scope

- Cursor Pagination TTL 도입 (별도 Plan 후보로 기록)
- Streamlit 컴포넌트 UI 테스트
- Manager GUI 프로세스 관리 테스트
- Gemini API 모델 업그레이드 / 신규 도구 추가

---

## 3. Requirements

### 3.1 Functional Requirements

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| FR-01 | `.env.example` 제공, 키 미설정 시 서버 기동 시점에 명확한 오류 로그 1회 출력 후 AI 기능만 비활성화 | High | Pending |
| FR-02 | FastAPI `TestClient`로 주요 엔드포인트 happy path + 에러 케이스 테스트(최소 20 케이스) | High | Pending |
| FR-03 | Chat 세션 저장소가 IP당 최대 N개, 전역 최대 1000개, TTL 30분 이후 자동 만료 | High | Pending |
| FR-04 | `execute_custom_query()` 경로 검증을 `validators.validate_db_path()`로 일원화하고 ATTACH 시 SQL 문자열 이스케이프 의존 제거 | High | Pending |
| FR-05 | `chat_with_data()`를 400줄 → 150줄 이하로 축소, 도구 실행 루프 분리 | Medium | Pending |
| FR-06 | `execute_custom_query()` 기본 타임아웃 10초, 환경변수로 조정 가능 | Medium | Pending |

### 3.2 Non-Functional Requirements

| Category | Criteria | Measurement Method |
|----------|----------|-------------------|
| Security | Gemini 키가 저장소 트래킹에서 제외 | `git ls-files | grep .env` 결과 없음 |
| Security | Custom Query ATTACH 경로 주입 차단 | `tests/test_sql_validation.py`에 경로 주입 케이스 추가 |
| Reliability | Chat 세션 10,000회 요청 시 RSS 증가 < 50MB | 부하 스크립트 + `psutil` 측정 |
| Testability | API 통합 테스트 실행 시간 < 30초 | `pytest tests/test_api_integration.py -q` |
| Maintainability | `chat_with_data` / `execute_custom_query` 함수 길이 | `wc -l`, cyclomatic complexity (radon) |

---

## 4. Success Criteria

### 4.1 Definition of Done

- [ ] Top 5 항목(S1~S5) 구현 완료
- [ ] 신규/수정 테스트 통과 (`pytest tests/ -v`)
- [ ] `docs/specs/operations_manual.md`에 `.env` 설정 절차 반영
- [ ] `docs/04-report/changelog.md`에 변경 기록 1줄 추가
- [ ] Gap 분석 Match Rate ≥ 90%

### 4.2 Quality Criteria

- [ ] 테스트 커버리지: API 엔드포인트 happy path 100%
- [ ] 기존 테스트 103개(추정) 모두 green 유지
- [ ] `chat_with_data` 함수 길이 ≤ 150 LOC
- [ ] Slow query 로깅 회귀 없음

---

## 5. Risks and Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Gemini mock 구성 난이도로 Chat 테스트 불완전 | Medium | Medium | `google.generativeai.GenerativeModel` 를 interface로 얇게 감싸 주입 가능하게 하고, 실제 API 호출은 skip 마커로 분리 |
| Custom Query 재설계 시 기존 AI 응답 정확도 저하 | High | Low | 회귀 테스트: 기존 프롬프트 10건 응답 비교(수동) |
| 대형 함수 리팩토링 중 멀티턴 대화 상태 회귀 | High | Medium | 세션 TTL/LRU 테스트를 먼저 작성(테스트 퍼스트) |
| Chat 세션 TTL 도입이 정상 사용자 대화 중단 유발 | Medium | Low | TTL 30분 + touch on access (sliding expiry) |
| Windows-only 환경에서 경로 검증 regex 회귀 | Medium | Medium | `pathlib.Path`로 교체, Windows 드라이브 문자 테스트 추가 |

---

## 6. Architecture Considerations

### 6.1 Project Level Selection

| Level | Characteristics | Recommended For | Selected |
|-------|-----------------|-----------------|:--------:|
| **Starter** | Simple structure | Static sites | ☐ |
| **Dynamic** | Feature-based modules, services layer | Web apps with backend | ☑ |
| **Enterprise** | Strict layer separation, DI | High-traffic systems | ☐ |

현 프로젝트는 이미 `api/ + shared/ + dashboard/ + tools/` 구조로 Dynamic 수준. 본 Plan은 **구조 변경 없이 내부 리팩토링/하드닝**만 수행.

### 6.2 Key Architectural Decisions

| Decision | Options | Selected | Rationale |
|----------|---------|----------|-----------|
| Secrets 관리 | .env / OS env / secret manager | `.env` + `.env.example` 분리 | 단일 기기 운영, 외부 secret manager 과잉 |
| API 테스트 방식 | httpx+TestClient / requests+live / pytest-fastapi | FastAPI `TestClient` | 의존 없이 in-process, CI 친화 |
| Gemini 주입 | 글로벌 싱글톤 / DI / monkeypatch | monkeypatch + adapter | 최소 침습, 테스트 대응 |
| 세션 저장소 | dict+lock / cachetools TTL / redis | `cachetools.TTLCache` | 이미 유사 패턴 사용, 외부 의존 회피 |
| Custom Query 경로 | ATTACH 문자열 / URI / 화이트리스트 | 경로 화이트리스트 + `pathlib` | 주입 면적 제거 |

### 6.3 Clean Architecture Approach

```
Selected Level: Dynamic (변경 없음)

영향 경계:
┌─────────────────────────────────────────────┐
│ api/main.py         ← 통합 테스트 추가        │
│ api/chat.py         ← 세션 TTL + 함수 분리     │
│ api/tools.py        ← custom query 재설계     │
│ shared/validators   ← 경로 검증 일원화         │
│ tests/              ← integration 테스트 신설 │
└─────────────────────────────────────────────┘
```

---

## 7. Convention Prerequisites

### 7.1 Existing Project Conventions

- [x] `README.md`에 프로젝트 구조 서술
- [x] `docs/specs/operations_manual.md` 존재
- [ ] `CLAUDE.md` 별도 컨벤션 섹션 (해당 없음)
- [x] `requirements.txt` / `requirements-smoke.txt` 분리
- [ ] lint / formatter 설정(없음, 본 Plan에서 미도입)

### 7.2 Conventions to Define/Verify

| Category | Current State | To Define | Priority |
|----------|---------------|-----------|:--------:|
| 환경 변수 로드 | `.env` 단일 파일 | `.env.example` + 키 누락 시 동작 규약 | High |
| 테스트 네이밍 | `tests/test_*.py` | `tests/test_api_integration.py` 신설 규칙 | High |
| 세션 상태 저장 | 전역 dict | `cachetools.TTLCache` 패턴으로 통일 | Medium |
| 쿼리 타임아웃 | 3초 하드코딩 | `CUSTOM_QUERY_TIMEOUT_SEC` 환경변수 | Medium |

### 7.3 Environment Variables Needed

| Variable | Purpose | Scope | To Be Created |
|----------|---------|-------|:-------------:|
| `GEMINI_API_KEY` | Gemini 인증 (기존) | Server | ☐ (유지) |
| `CHAT_SESSION_TTL_SEC` | Chat 세션 만료 시간 (기본 1800) | Server | ☑ |
| `CHAT_SESSION_MAX_PER_IP` | IP당 최대 세션 수 (기본 20) | Server | ☑ |
| `CUSTOM_QUERY_TIMEOUT_SEC` | Custom SQL 타임아웃 (기본 10) | Server | ☑ |
| `ARCHIVE_DB_WHITELIST` | ATTACH 허용 DB 경로 목록 | Server | ☑ |

### 7.4 Pipeline Integration

본 Plan은 기존 시스템 유지보수 성격으로 9-phase pipeline에 편입하지 않음.

---

## 8. Next Steps

1. [ ] Design 문서 작성: `docs/02-design/features/security-and-test-improvement.design.md`
2. [ ] 각 항목 상세 설계(특히 S3 세션 스토어, S4 경로 화이트리스트 인터페이스)
3. [ ] `/pdca do security-and-test-improvement`로 구현 착수
4. [ ] 구현 후 `/pdca analyze`로 Gap 분석
5. [ ] Match Rate ≥ 90% 시 `/pdca report`

---

## 9. Top 5 Issue Mapping (참고)

| # | 이슈 | 관련 파일 | Requirement |
|---|---|---|---|
| 1 | `.env` 비밀정보 | 루트 `.env` | FR-01 |
| 2 | API 통합 테스트 부재 | `api/main.py`, `tests/` | FR-02 |
| 3 | Chat 세션 누수 | `api/chat.py:119, 178-192` | FR-03 |
| 4 | Custom Query 경로/타임아웃 | `api/tools.py:519-664` | FR-04, FR-06 |
| 5 | 대형 함수 | `api/chat.py:311-470`, `api/tools.py:519-664` | FR-05 |

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 0.1 | 2026-04-14 | 초기 드래프트 — 전체 코드 리뷰 Top 5 기반 | interojo |
