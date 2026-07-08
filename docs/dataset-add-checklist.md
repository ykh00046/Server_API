# 신규 수집 데이터셋 추가 체크리스트 (roadmap-2026h2 B-4)

멀티키워드 대칭 작업 모델에서 새 검색 키워드(데이터셋)를 추가할 때의
3점 체크리스트. materials(자재)/binder(액상바인더출고)가 선례다.

## 1. Server_API (이 저장소)

- [ ] `api/materials/datasets.py` registry에 `Dataset` 1줄 추가
      (key, prefix, title, keywords, table, runs_table)
      → 라우터/스키마/마이그레이션은 팩토리가 자동 처리 (`make_router`,
      `(doc_number, seq)` 복합 PK 멱등 마이그레이션 포함)
- [ ] `dashboard/views/{key}.py` 생성 — `dataset_page.render()` 호출
      (binder.py 복사, prefix/title/icon/sheet_name/file_base/empty_msg 교체.
      컬럼 헤더 의미가 자재와 다르면 `columns=` 파라미터로 교체)
- [ ] `dashboard/app.py` `st.navigation`에 `st.Page` 1줄 추가

## 2. webcloring-pdf (봇 서브모듈)

- [ ] `config.json` `search.jobs`에 `{keyword, times}` 추가
- [ ] `dataset_routes` 라우팅에 키워드 → API prefix 매핑 추가
      (키워드별 Excel/PDF/처리이력 분리는 자동)

## 3. 운영 반영

- [ ] 서브모듈 포인터 커밋 + 루트 push
- [ ] 운영 PC: update + **매니저 통째 재시작** (서비스만 재기동하면
      매니저의 "수집 작업" UI가 구 config를 봄)
- [ ] 매니저 "수집 작업" UI에서 신규 키워드 확인, Run Now 1회 스모크
- [ ] 대시보드 신규 페이지에서 백업 수신(runs에 backup 행) 확인

## 검증 게이트

- `pytest -q` 전체 + `ruff check .` — registry 추가만으로 기존
  테스트가 신규 prefix를 자동 커버하지는 않으므로, 필요 시
  `test_materials.py`의 dataset 파라미터라이즈에 key 추가.
