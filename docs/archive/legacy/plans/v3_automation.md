# Production Data Hub - Phase 3: 자동화 운영 및 안정성 강화 계획

## 1. 개요
본 계획은 ERP의 DB 갱신에 대응하여 시스템이 스스로 최적의 상태(인덱스 유지, 최신 데이터 반영)를 유지하도록 **Manager v2**와 **App Cache Strategy**를 구현하는 것을 목표로 합니다.

**핵심 철학:** "사람의 개입 없이, 시스템이 스스로 변경을 감지하고 안전하게 복구한다."

---

## 2. Manager v2 (지능형 DB 감시자)

### 2.1 아키텍처: 스레드 안전성 확보
- **Watcher Thread**: 백그라운드에서 파일 감시 및 DB 작업을 수행. UI를 직접 건드리지 않고 결과만 Queue에 넣음.
- **Main Thread (UI)**: `root.after()`를 통해 주기적으로 Queue를 확인하고 화면을 갱신. (크래시 방지)

### 2.2 감지 및 복구 로직 (디바운스 적용)
ERP의 파일 쓰기가 완료될 때까지 기다리는 "안정화" 로직을 필수로 적용합니다.

1.  **감지:** 1시간 주기(또는 설정된 주기)로 `production_analysis.db`의 `mtime`(수정 시간)과 `size`를 확인.
2.  **디바운스(안정화):**
    - 변화가 감지되면 즉시 실행하지 않음.
    - 5초 간격으로 3회(약 15초) 재확인하여 `mtime`과 `size`가 더 이상 변하지 않을 때 "갱신 완료"로 판단.
3.  **복구 실행 (Self-Healing):**
    - SQLite 연결 (Timeout 10초).
    - 인덱스 존재 여부 확인 (`PRAGMA index_list`).
    - **인덱스 유실 시:** `CREATE INDEX IF NOT EXISTS` 실행. (실패 시 3회 재시도)
4.  **로깅:** "인덱스 복구됨", "DB 갱신 감지됨" 등 중요 이벤트만 로그에 기록.

### 2.3 UI 변경 (DB 관리 패널 추가)
기존 대시보드/API 패널 하단에 **[🔧 DB Auto-Management]** 패널을 신설합니다.

- **상태 모니터링:**
    - `Last DB Update`: 마지막으로 감지된 ERP 갱신 시간.
    - `Last Index Check`: 마지막 인덱스 점검 시간 및 결과 (성공/실패).
    - `Next Check`: 다음 자동 점검 예정 시간.
- **제어:**
    - `[🛠️ Run Check Now]`: 즉시 점검 및 인덱스 생성 버튼.
    - `[✅ Auto Mode]`: 자동 감시 켜기/끄기 토글.

---

## 3. Dashboard/API 캐시 전략 (Smart Caching)

Manager가 억지로 캐시를 지우는 대신, Streamlit/FastAPI가 **스스로 데이터 변경을 인지**하도록 만듭니다.

### 3.1 Streamlit Cache Invalidation
- **원리:** 캐시 키(Cache Key)에 "DB 파일의 수정 시간(`mtime`)"을 포함시킵니다.
- **구현:**
  ```python
  def get_db_mtime():
      return os.path.getmtime(DB_FILE)

  @st.cache_data
  def load_records(..., db_ver):
      # db_ver(mtime)가 바뀌면 이 함수는 자동으로 재실행됨
      ...
  
  # 호출 시
  load_records(..., db_ver=get_db_mtime())
  ```
- **효과:** ERP가 파일을 갱신하면 `mtime`이 바뀌고, 다음 조회 시 Streamlit이 알아서 캐시를 버리고 새로 읽어옵니다.

---

## 4. 상세 구현 스텝 (Action Plan)

### Step 1: `dashboard/app.py` & `api/main.py` 수정
- `get_db_mtime()` 헬퍼 함수 추가.
- 모든 캐시 함수(`load_records`, `load_item_list` 등)에 `db_ver` 인자 추가.

### Step 2: `manager.py` 리팩토링 (v2)
- `customtkinter` UI 구조 확장 (3단 레이아웃: Web / API / DB).
- `DBWatcher` 클래스 구현 (디바운스, 스레드, 큐 로직 포함).
- 메인 루프에 `check_queue` 콜백 등록.

### Step 3: 테스트 시나리오
1.  서버 실행 중 DB 파일 임의 교체 (ERP 갱신 시뮬레이션).
2.  Manager가 15초(디바운스) 후 "감지 및 점검" 로그 출력 확인.
3.  대시보드 새로고침 시 최신 데이터 반영 확인.
