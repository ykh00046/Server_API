# Plan: Server API Intake and Documentation Alignment

> PDCA Phase: **Plan**
> Feature: `server-api-intake`
> Created: 2026-03-31
> Status: Draft

---

## 1. Background & Motivation

Server_API 저장소는 기능 문서, 개선 로드맵, 운영 가이드가 여러 차례 누적되면서 문서 위치 규칙이 혼재된 상태다.

- 루트 `README.md`는 일부 레거시 경로(`docs/plans/`)를 계속 참조한다.
- 보드 이슈에서 참조한 계획 문서명과 저장소 내 실제 파일 경로가 일치하지 않는다.
- 현재 heartbeat 환경에서는 핵심 런타임 의존성이 비어 있어, "문서대로 재현 가능" 여부를 코드/문서 기준으로 별도 확인해야 한다.

이 계획은 인수 관점에서 현재 문서 구조를 정리하고, 후속 검증 작업이 어떤 산출물로 남아야 하는지 명확히 고정하는 것을 목표로 한다.

## 2. Goals

| ID | 목표 | 측정 기준 |
|:--:|------|----------|
| G1 | 저장소 문서 구조 기준선 확정 | 계획/리포트/스펙 경로가 루트 문서에 반영됨 |
| G2 | 보드-저장소 참조 불일치 해소 | 보드에서 언급한 계획 항목이 실제 파일로 존재하거나 대체 경로가 명시됨 |
| G3 | 후속 스모크 검증 입력 고정 | 스모크 관련 계획/리포트 경로가 일관되게 연결됨 |

## 3. Scope

### In Scope

| ID | 항목 | 파일 | 난이도 |
|:--:|------|------|:------:|
| I1 | 현재 문서 체계 확인 | `README.md`, `docs/**` | Low |
| I2 | 인수용 계획 문서 작성 | `docs/01-plan/features/server-api-intake.plan.md` | Low |
| I3 | 보드에서 기대하는 후속 계획 위치 정리 | `README.md`, 보드 코멘트/이슈 링크 | Low |

### Out of Scope

- 애플리케이션 기능 구현
- 전체 문서 체계 개편 또는 대규모 파일 이동
- CI/CD 파이프라인 구축

## 4. Detailed Plan

### I1. 문서 구조 기준선 확인

- 루트 `README.md`의 문서 링크 섹션 점검
- `docs/01-plan/features`, `docs/04-report`, `docs/specs`의 현행 산출물 확인
- 보드 이슈 설명에 적힌 계획 파일명이 저장소에 존재하는지 확인

### I2. 인수용 계획 문서 고정

- 본 문서를 인수/정리 관점의 기준 계획으로 추가
- 후속 스모크/정합화 작업은 별도 계획 문서로 연결
- 새 문서명은 기존 `docs/01-plan/features/*.plan.md` 규칙을 따른다

### I3. 보드-저장소 링크 정합화

- `README.md` 문서 섹션에 현재 유효한 계획/리포트 링크 추가
- 레거시 계획 문서는 "legacy" 또는 "기존 로드맵" 성격으로 구분
- 보드에는 실제 저장소 경로를 기준으로 대체 링크를 안내

## 5. Modified Files Summary

| 파일 | 변경 유형 | 항목 |
|------|----------|------|
| `docs/01-plan/features/server-api-intake.plan.md` | 신규 생성 | I2: 인수 기준 계획 문서 |
| `README.md` | Modified | I1, I3: 현행 문서 링크 반영 |
| `docs/04-report/changelog.md` | Modified | I3: 정합화 변경 이력 기록 |

## 6. Verification Plan

1. `README.md`의 문서 섹션에서 계획/리포트 링크가 실제 파일로 열리는지 확인
2. `rg "server-api-intake|server-api-consistency-and-smoke" docs README.md`로 신규 참조가 일관되게 남는지 확인
3. 보드 업데이트 시 저장소 내 실제 경로를 기준으로 코멘트를 남긴다
