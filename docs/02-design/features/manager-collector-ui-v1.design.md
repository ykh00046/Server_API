# manager-collector-ui-v1 — 매니저 수집 작업 UI 확장 (패턴 편집 + 일시정지)

- 작성일: 2026-08-06
- 상태: 설계 확정 (구현 위임용 지시서)
- 관련 저장소: **Server_API** (manager.py, portal_settings_dialog.py) + **webcloring-pdf** (main.py, src/config/settings.py)

## 1. 배경

수집 패턴(materials=완료문서함·양식명 검색 / binder=부서공개함·기안자·문서제목 검색)은
`config.json`의 `search.collectors`에만 존재하고 매니저 UI에 노출되지 않는다. 그 결과:

- 작업을 "잠시 멈출" 방법이 없어 삭제로 우회 → 재등록 시 키워드 오타면 **조용히 materials로 폴백**
  (collectors·dataset_routes가 exact match라서), 사용자는 패턴 설정이 사라진 것으로 오인.
- 시각 하나 바꾸려 해도 삭제→재추가만 가능.
- 새 binder류 키워드 추가는 config.json 손편집 3곳(jobs/collectors/dataset_routes) 필요 — 불일치 사고 위험.

## 2. 목표 / 비목표

**목표**
1. 작업별 `enabled` 토글(일시정지) — 스케줄만 제외, 스펙·이력 보존, 수동 Run Now는 허용.
2. 작업 리스트에 수집 패턴 배지 표시(폴백 여부 시각화).
3. 작업 추가/편집 모달 — 키워드·시각·활성화·패턴·부서공개함 옵션·서버 데이터셋을 한 번에 저장
   (jobs + collectors + dataset_routes 동시 기록 → 3곳 불일치 원천 차단).
4. 죽은 전역 설정 `WEEKDAYS_ONLY` 스위치 제거.

**비목표**
- 서버(Server_API api/) 데이터셋 registry 및 대시보드는 변경하지 않는다. 새 데이터셋 추가는
  필요 시점에 별도 작업 (`api/materials/datasets.py` 참조).
- config.json 스키마의 collectors-v1 형태 자체는 유지한다 (키워드 키 exact match, materials 폴백).

## 3. UI 스펙

### 3.1 수집 작업 리스트 (portal_settings_dialog 본문)

```
🗂️ 수집 작업 (키워드별)
┌──────────────────────────────────────────────────────┐
│ ⏻  자재        [완료문서함(기본)]  21:00        ✏️  ✕ │
│ ⏻  PBHAv1.0   [부서공개함·평일]   22:00        ✏️  ✕ │
│ ⏸  예시키워드  [완료문서함(기본)]  (수동 전용)   ✏️  ✕ │  ← 비활성: 흐리게
└──────────────────────────────────────────────────────┘
                                        [+ 작업 추가]
```

- 행 구성: `[enabled 스위치] [키워드(bold)] [패턴 배지] [시각 or "(수동 전용)"] [✏️] [✕]`.
- **enabled 스위치**: 토글 즉시 `_persist_jobs()`로 저장. 꺼진 행은 텍스트를 muted 색으로.
- **패턴 배지** (collectors 조회 결과로 결정):
  - collectors에 entry 있고 `type=="binder"` → `부서공개함`, `weekdays`면 `부서공개함·평일`. 강조색.
  - collectors에 entry 있고 `type=="materials"` → `완료문서함`.
  - collectors에 entry 없음(폴백) → `완료문서함(기본)`, muted 색 — 조용한 폴백을 눈에 보이게.
- **✏️**: 편집 모달(3.2)을 해당 작업 값으로 프리필해 연다.
- **✕**: 확인 다이얼로그 후 jobs에서만 제거. **collectors·dataset_routes 스펙은 보존**(현행 유지).
  확인 문구에 "수집 패턴 설정은 남겨둡니다 — 같은 키워드로 재등록하면 다시 연결됩니다." 명시.
- 기존 인라인 추가 행(ent_job_keyword/ent_job_times + 추가 버튼)은 **제거**하고
  `[+ 작업 추가]` 버튼 하나로 대체(모달 열기). 리스트 프레임 height 110 → 140 권장.
- 안내 라벨 문구는 "추가/편집/일시정지는 즉시 저장되며, 실행 중인 스케줄에는 봇 재시작 후
  적용됩니다."로 갱신.

### 3.2 작업 추가/편집 모달 (신규 CTkToplevel)

`manager.py`의 `_pick_keyword_dialog`와 같은 계열(transient + grab_set, 부모 중앙 배치).

```
┌─ 수집 작업 추가/편집 ───────────────────────────┐
│  키워드        [ PBHAv1.0          ]            │
│  실행 시각     [ 22:00             ]            │
│                (쉼표로 여러 개, 비우면 수동 전용) │
│  [⏻] 활성화                                     │
│  ── 수집 패턴 ─────────────────────────────     │
│  (•) 완료문서함 — 양식명 검색 (자재 방식)        │
│  ( ) 부서공개함 — 기안자/문서제목 검색 (PBHA 방식)│
│  ┌ 부서공개함 옵션 (binder 선택 시에만 표시) ┐   │
│  │  기안자         [ 김지훈  ]                  │
│  │  문서제목 포함   [ PBHA   ]                  │
│  │  [⏻] 평일만 실행                            │
│  └────────────────────────────────────────┘    │
│  서버 데이터셋   [ binder ▾ ]                    │
│                 (패턴 선택 시 자동 지정, 변경 가능)│
│              [ 취소 ]        [ 저장 ]           │
└────────────────────────────────────────────────┘
```

- 패턴: `CTkRadioButton` 2개. 선택 변경 시 부서공개함 옵션 박스 show/hide + 데이터셋 드롭다운
  기본값 자동 전환(materials→`/materials`, binder→`/binder`). 사용자가 드롭다운을 직접 바꾼
  뒤에는 자동 전환으로 덮어쓰지 않는다.
- 데이터셋 드롭다운(`CTkOptionMenu`): 항목 `["/materials", "/binder"]` 정적 리스트
  (서버 `api/materials/datasets.py` registry와 일치— 코드 주석으로 동기화 의무 명시).
- 편집 모드에서 키워드를 변경하면 **rename**으로 처리: jobs 항목 교체 + collectors·
  dataset_routes의 구 키 entry를 새 키로 **이동**(orphan 스펙을 남기지 않음).

**검증 규칙 (저장 버튼)**
1. 키워드 필수, 중복 금지(편집 중인 자기 자신 제외). 저장 전 `strip()`.
2. 시각: `HH:MM` 쉼표 구분, 기존 `_add_job`의 정규식·범위 검사 재사용. 비면 수동 전용.
3. binder 선택 시 기안자·문서제목 **둘 다 비면 거부** (검색 조건 없는 전체 스캔 방지).
4. 실패 시 messagebox 경고 + 모달 유지.

### 3.3 실행 옵션 섹션

- `WEEKDAYS_ONLY` 스위치(`sw_weekdays`) 및 `_save()`의 해당 키 기록을 **제거**.
  근거: 봇 스케줄러는 `main.py:124`에서 `collector_for(keyword)["weekdays"]`만 사용하며
  `settings.weekdays_only` property는 호출부가 없다(죽은 설정). .env에 남은 키는 무해하므로
  마이그레이션 불필요. 봇 저장소의 `settings.weekdays_only` property도 제거.

## 4. 데이터 모델 / 저장 매핑

`config.json` (봇 `src/config/config.json`) — 모달 저장 시 세 곳을 원자적으로(한 번의
json.dump로) 기록:

| 모달 필드 | 저장 위치 | 비고 |
|---|---|---|
| 키워드, 실행 시각, 활성화 | `search.jobs[]` = `{"keyword", "times", "enabled"}` | `enabled` 신규, 기본 true |
| 패턴, 기안자, 문서제목, 평일만 | `search.collectors[키워드]` = `{"type", "box", "drafter", "title", "weekdays"}` | `box`는 패턴에서 유도: materials→`"completed"`, binder→`"dept_open"` (UI 미노출) |
| 서버 데이터셋 | `api_backup.dataset_routes[키워드]` | `/materials`(폴백 기본값)이면 entry를 **쓰지 않고, 있으면 삭제** — config 최소 유지 |

collectors 기록 규칙: binder면 항상 기록. materials면 **기존 entry가 있을 때만**
`type:"materials"`로 갱신하고, 없으면 기록하지 않는다(폴백 유지, 현 파일 형태 보존).

### `enabled` 하위 호환

- 필드 부재 = `true` (기존 config 그대로 동작).
- **양쪽 정규화 코드가 현재 keyword/times만 보존하므로 반드시 함께 수정**:
  - 봇 `settings.search_jobs` (settings.py:220-228) / `save_search_jobs` (:249-265)
  - 매니저 `_read_jobs` (portal_settings_dialog.py:219-247) / `_write_jobs` (:249-264)

## 5. 봇 동작 변경 (webcloring-pdf)

1. `main.py run_scheduled()` (:117-133): `job.get("enabled", True)`가 False면 스케줄 등록을
   건너뛰고 `print(f"   - (일시정지)  🔑 {keyword}")` 표시. registered 카운트 제외.
2. 수동 실행(`--auto --keyword`)은 enabled와 무관하게 허용 (변경 없음 — 현행이 이미 그러함).
3. `settings.weekdays_only` property 제거 (§3.3).

## 6. 매니저 동작 변경 (Server_API)

1. `manager.py _keywords_from_config()` (:861-888): Run Now 키워드 목록에 **비활성 작업도
   포함**(수동 실행 허용 정책). 변경 불필요하면 그대로 두되 enabled 필드가 생겨도 깨지지
   않는지 확인.
2. `portal_settings_dialog.py`: §3 전체. 즉시 저장(`_persist_jobs`) 패턴 유지 — 실패 시
   `_read_jobs()`로 롤백하는 기존 로직 보존.
3. 색·폰트는 `manager_theme.py` 기존 토큰(TEXT_MUTED, btn_* 헬퍼) 사용. 새 색상 하드코딩 금지.

## 7. 검증 게이트

- **봇 (webcloring-pdf)**: pytest 전체 + 신규 테스트 —
  - `search_jobs`가 enabled를 보존/기본값 처리하는지
  - `save_search_jobs` 왕복 후 enabled 유지
  - `run_scheduled` 스케줄 등록 로직: disabled 작업 제외 (schedule 등록 함수를 분리하거나
    기존 테스트 패턴을 따라 검증)
- **매니저 (Server_API)**: ruff 게이트(F/BLE001/I/UP/B/SIM/E501/C901≤10) + pytest 전체 +
  위젯 스모크 패턴(기존 매니저 GUI 검증 방식): 모달 생성→필드 입력→저장→config.json 내용
  assert. Tk 없는 CI 환경이면 로직 함수(검증·직렬화)를 위젯에서 분리해 단위 테스트.
- 수동 시나리오 3종:
  1. PBHAv1.0 편집 열기 → binder 라디오·기안자 김지훈·제목 PBHA·평일 ON·데이터셋 /binder로
     프리필되는지.
  2. 일시정지 토글 → config.json에 enabled:false → 봇 재시작 로그에 "(일시정지)" 표시.
  3. 신규 binder 키워드 추가 → collectors·dataset_routes 동시 기록 확인.

## 8. 브랜치 / 커밋 / 배포

- 착수 전 `git branch -a`로 기존 브랜치 확인 (양 저장소).
- 브랜치: Server_API `feat/manager-collector-ui`, webcloring-pdf `feat/jobs-enabled`.
- 커밋 분리(논리 단위): ① 봇 enabled+정규화 ② 매니저 리스트(배지·토글·삭제 문구)
  ③ 매니저 모달 ④ WEEKDAYS_ONLY 제거.
- 게이트 통과 후 main 병합·푸시까지 한 흐름으로 (브랜치 방치 금지).
- **push ≠ 운영 반영**: 운영 PC에서 update.bat + 매니저 재시작 별도 필요. 완료 보고에 명시할 것.
