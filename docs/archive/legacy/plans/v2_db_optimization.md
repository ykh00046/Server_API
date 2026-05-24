# Production Data Hub - Phase 2: DB 분리 및 성능 최적화 계획

## 1. 배경 및 분석

### 1.1 현재 상황 분석
- **ERP 데이터 연동 방식**: 파일 생성 날짜는 변하지 않으나, 내부적으로 **기존 데이터 삭제 후 전체 재입력(Truncate & Insert)**하는 "논리적 덮어쓰기" 방식임이 확인됨.
- **리스크**:
    1. **데이터 유실 위험**: 매일 전체 데이터를 다시 쓰기 때문에, 전송 중 오류 발생 시 과거 데이터(2025년 등)까지 손상될 위험 존재.
    2. **성능 저하**: 데이터가 누적될수록 ERP의 전송 시간(Write)과 대시보드의 조회 시간(Read)이 모두 비례하여 증가함.
    3. **인덱스 유지 불확실성**: 만약 ERP가 테이블을 DROP하고 다시 생성(Case B)하거나 파일을 교체(Case C)한다면 인덱스도 함께 삭제됨.

### 1.2 개선 목표
- **DB 분리 (Archiving)**: 확정된 과거 데이터(2025년)를 별도 파일로 분리하여 보존.
- **성능 최적화 (Indexing)**: 조회 속도 향상을 위해 인덱스 적용.
- **하이브리드 조회**: `ATTACH DATABASE`를 활용하여 두 DB를 하나의 쿼리로 조회(성능 최적화).

---

## 2. 아키텍처 변경

### 2.1 폴더 및 파일 구조
```text
C:\X\Server_v1\database\
├── archive_2025.db         # [신규] 2025년 데이터 전용 (Read-Only, 영구 인덱스)
└── production_analysis.db  # [기존] 2026년 이후 데이터 (ERP가 매일 덮어쓰기 수행)
```

### 2.2 데이터베이스 역할 정의
| DB 파일 | 역할 | 특징 | 인덱스 전략 |
| :--- | :--- | :--- | :--- |
| **archive_2025.db** | 2025년 과거 데이터 보관 | 절대 변하지 않음 (Static) | **영구 인덱스 생성** |
| **production_analysis.db** | 2026년~현재 데이터 | 매일 ERP가 갱신 (Dynamic) | ERP 갱신 직후 인덱스 재생성 스크립트 구동 권장 |

> **중요**: Live DB(`production_analysis.db`)에 2025년 데이터가 여전히 포함되어 들어올 수 있음. 따라서 앱 레벨에서 **중복 방지 필터**(`WHERE production_date >= '2026-01-01'`)를 반드시 적용해야 함.

---

## 3. 상세 코드 구현 계획

### 3.1 DB Router 및 통합 조회 (ATTACH 방식)

Pandas `concat` 대신 SQLite의 `ATTACH DATABASE` 기능을 사용하여 DB 레벨에서 통합 조회를 수행합니다. 이는 메모리 사용량을 줄이고 정렬/페이징 성능을 극대화합니다.

```python
def get_records_query(date_from, date_to, limit, offset):
    """
    ATTACH DATABASE를 활용한 통합 조회 쿼리 생성
    """
    # 기본: Live DB만 조회
    sql = "SELECT * FROM production_records WHERE production_date >= '2026-01-01'"
    
    # 2025년 데이터가 필요한 경우 Archive DB 연결
    if date_from < date(2026, 1, 1):
        # ATTACH 구문은 연결 시 수행
        # UNION ALL로 Archive(2025) + Live(2026~) 통합
        sql = f"""
        SELECT * FROM archive.production_records 
        WHERE production_date < '2026-01-01'
        UNION ALL
        SELECT * FROM production_records 
        WHERE production_date >= '2026-01-01'
        """
        
    # 필터 조건 추가
    # ...
    
    sql += " ORDER BY production_date DESC, id DESC LIMIT ? OFFSET ?"
    return sql
```

### 3.2 성능 최적화: 인덱스(Index) 전략

**[효과 큼]**
- `production_date`: 범위 검색 속도 향상 (필수)
- `item_code`: 특정 제품 조회 속도 향상

**[효과 제한적]**
- `item_name`, `lot_number`: `LIKE '%...%'` 검색 시 인덱스 효과 미미함. (Full Text Search 도입 전까지는 감수)

**[운영 전략]**
- **Archive DB**: 마이그레이션 시 1회 생성.
- **Live DB**: ERP 갱신 스케줄(예: 07:00) 직후에 실행되는 **인덱스 점검 스크립트** 배치.

### 3.3 마이그레이션 스크립트 (`tools/migrate_2025.py`)

안전성을 최우선으로 하는 분리 절차입니다.

1.  **복제**: `production_analysis.db` → `archive_2025.db` (OS Copy)
2.  **정제 (Archive)**:
    - `DELETE FROM production_records WHERE production_date >= '2026-01-01'`
    - `COMMIT`
    - 연결 종료 후 재연결 -> `VACUUM` (파일 크기 축소)
    - 인덱스 생성
3.  **검증**:
    - Archive DB에 2026년 데이터가 0건인지 확인.
    - 파일 속성을 Read-Only로 변경 (OS 레벨 보호).

---

## 4. 실행 전략 (Action Plan)

1.  **도구 개발**: `tools/migrate_2025.py` 작성.
2.  **DB 분리 실행**: 스크립트 실행하여 `archive_2025.db` 생성.
3.  **앱 수정**:
    - `dashboard/app.py`: `get_db_connection`에 `ATTACH` 로직 추가.
    - `api/main.py`: 동일하게 `ATTACH` 로직 적용.
4.  **테스트**: 2025년, 2026년, 걸친 기간 조회 시 데이터 정합성 확인.

## 5. 향후 과제 (Phase 2.5)
만약 ERP가 파일을 통째로 교체(Case C)하여 인덱스 유지가 불가능하다면, **Hub DB 전략**(별도 DB에 증분 적재)으로 전환을 고려해야 함.