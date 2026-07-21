# materials-tombstone-v1 — 삭제 문서 부활 방지 (tombstone)

- 상태: 구현 중 (2026-07-21)
- 브랜치: `feat/materials-tombstone-v1`
- 관련: materials-datasets-v1, 삭제 기능(9921a03)

## 배경 / 문제

봇(webcloring-pdf)의 API 백업은 증분이 아니라 **키워드별 Excel 전체를 매 실행 1 POST(upsert)** 한다
(`ApiBackupManager._prepare_rows`가 워크시트 전 행 순회, `run_automation`의 `finally`에서 호출 —
실패 실행·신규 0건에서도 전송). 따라서 서버에서 `DELETE /{prefix}/{doc_number}`로 지운 문서가
Excel에 남아 있는 한 **다음 자동화 실행 때 통째로 부활**한다. 봇 이력 DB(dedup)는 재스크랩만 막을
뿐 백업 전송과 무관하다. 2026-07-21 binder(액상바인더출고)에서 실사례 확인.

## 설계

서버 측 tombstone: 삭제된 doc_number를 기록해 두고, backup upsert가 해당 문서 행을 건너뛴다.
봇은 무수정(전체 Excel 백업의 유실 복구 장점 유지).

### 스키마 (materials.db)

```sql
CREATE TABLE IF NOT EXISTS deleted_documents (
    table_name TEXT NOT NULL,   -- 데이터셋 테이블 (registry 신뢰 식별자)
    doc_number TEXT NOT NULL,
    deleted_at TEXT NOT NULL,
    PRIMARY KEY (table_name, doc_number)
);
```

단일 공용 테이블, 데이터셋 격리는 `table_name` 컬럼으로. `_ensure_schema`에서 생성.

### store (api/materials/store.py)

- `delete_document`: 실제 삭제(rowcount>0) 시 같은 커밋에서 tombstone `INSERT OR REPLACE`.
- `upsert_materials`: 배치 내 dedupe 후, 이 테이블에 tombstone이 있는 doc_number의 행을 제외.
  제외 행 수를 `BackupResult.skipped`(신규, 기본 0 — 봇 계약 불변)로 반환.
- `restore_document(doc_number, table) -> int`: tombstone 제거(복원 허용). 다음 백업 때 재유입.
- `list_tombstones(table) -> list[dict]`: `{doc_number, deleted_at}` 최신순.

### 라우터 (make_router — 모든 데이터셋 공통)

- `GET {prefix}/tombstones` → tombstone 목록 (`/{doc_number}` 캡처 회피 위해 먼저 등록).
- `POST {prefix}/{doc_number}/restore` → tombstone 제거, 없으면 404.
- `_backup_body`: skipped 로그·실행 이력 반영.

### 대시보드 (dataset_page.py)

- 삭제 expander 문구 갱신: 삭제 = tombstone 등록이라 봇 백업에서도 제외됨(부활 없음),
  복원 시 다음 백업 때 재유입. placeholder를 실제 문서번호 형식으로.
- tombstone 목록 표시 + 복원 버튼.

## 운영 시맨틱

- **삭제**(대시보드/DELETE): 행 제거 + tombstone → 봇이 계속 전송해도 서버에 재유입 없음.
- **복원**(restore): tombstone만 제거 → 봇 Excel에 행이 남아 있으면 다음 백업 때 자동 복구.
- 봇 Excel 정리는 이제 선택 사항(권장이지만 부활 방지에 필수 아님).

## 검증

- 단위: delete→upsert skip(skipped 카운트)·restore→재유입·데이터셋 격리·404 경로.
- 게이트: 전체 pytest + ruff(F/BLE001/I/UP/B/SIM/E501/C901).
