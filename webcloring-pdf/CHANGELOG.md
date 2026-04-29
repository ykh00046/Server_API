# 변경 이력 (Changelog)

## [2025-12-03] - 프로젝트 정리 및 최적화

### 추가됨 (Added)
- **설정 파일 통합**: `src/config/config.json` 생성
  - Excel 자동 저장 간격 설정
  - Google Sheets 백업 간격 설정
  - 페이지네이션 설정 (최대 페이지 수, 최대 연속 오류, 페이지 크기)
- **배치 파일**: Windows 사용자를 위한 간편 실행 스크립트
  - `실행.bat` - GUI 모드 실행
  - `자동화실행.bat` - 콘솔 자동화 모드 실행
  - `빌드.bat` - 실행 파일 빌드
  - `패키지설치.bat` - 패키지 설치 (가상환경 지원)
- **설정 속성 추가** (`src/config/settings.py`):
  - `auto_save_interval` - Excel 자동 저장 간격
  - `min_backup_interval` - Google Sheets 최소 백업 간격
  - `max_pages` - 최대 처리 페이지 수
  - `max_consecutive_errors` - 최대 연속 오류 허용 횟수
  - `page_size` - 페이지당 문서 수

### 변경됨 (Changed)
- **Google Sheets 인증**:
  - 올바른 서비스 계정 키 파일로 업데이트
  - 경로: `src/config/tough-timing-465404-a2-062bb3be4278.json`
  - 서비스 계정: `id-697@tough-timing-465404-a2.iam.gserviceaccount.com`
- **하드코딩 제거**:
  - `src/core/excel_manager.py`: `auto_save_interval` 설정 파일에서 로드
  - `src/services/google_sheets_manager.py`: `min_backup_interval` 설정 파일에서 로드
- **디버그 모드 비활성화**:
  - `.env`: `DEBUG_MODE=false` 설정
  - 브라우저 자동 종료 활성화

### 수정됨 (Fixed)
- **GUI 백업 버튼 오류 수정** (`src/gui/main_window.py:434`):
  - 문제: GoogleSheetsDialog 호출 시 excel_manager 매개변수 누락
  - 해결: ExcelManager 인스턴스 생성 후 전달
  - 증상: "ExcelManager가 초기화되지 않았습니다" 오류
  - 결과: 수동 백업 정상 작동 확인

### 제거됨 (Removed)
- **빌드 아티팩트** (~442MB):
  - `build/` 폴더
  - `dist/` 폴더
  - `automation.spec` 파일
- **테스트 파일**:
  - `test_*.py` 파일들
  - `debug_*.py` 파일들
  - `*_debug.html` 파일들
- **중복 파일**:
  - 구 Google Sheets 키 파일 (`google_sheets_key.json`)
  - `chromedriver.exe` (자동 관리됨)
- **Python 캐시**:
  - `__pycache__/` 폴더들

### 보안 (Security)
- `.gitignore` 업데이트:
  - Google Sheets 키 파일 제외 (단, `src/config/` 내부는 예외)
  - 테스트 파일 패턴 추가
  - 디버그 파일 패턴 추가

---

## [2025-12-02] - Google Sheets 통합 (v3.0)

### 추가됨 (Added)
- **Google Sheets 통합 모듈**:
  - `src/services/google_sheets_manager.py` - API 관리 및 백업 로직
  - `src/config/google_sheets_config.py` - 설정 관리
  - `src/gui/google_sheets_dialog.py` - 설정 GUI
- **배치 백업 기능**:
  - 자동화 종료 시 전체 데이터 1회 백업
  - API 호출 최적화: 100회 → 2회 (98% 감소)
- **GUI 개선**:
  - "Google Sheets" 설정 버튼 추가
  - 스레드 기반 비동기 백업 (프리징 방지)
  - 백업 상태 표시 (성공/실패 횟수, 마지막 백업 시간)

### 변경됨 (Changed)
- **ExcelManager** (`src/core/excel_manager.py`):
  - Lazy Loading 패턴으로 GoogleSheetsManager 초기화
  - `finalize_google_backup()` 메서드 추가
  - `workbook` 속성에 대한 `wb` 별칭 추가
- **PortalAutomation** (`src/core/portal_automation.py`):
  - `run_automation()` finally 블록에 백업 로직 추가
  - 자동화 종료 시 자동 백업 실행

### 특징 (Features)
- **Lazy Loading**: 초기 로딩 시간 단축
- **배치 처리**: API 호출 98% 감소
- **Rate Limiting**: 60초 최소 간격
- **Fail-Safe**: 백업 실패해도 Excel 저장은 정상 진행
- **Threading**: GUI 프리징 방지

---

## [2025-12-01] - 페이지네이션 개선 계획 (v2.0)

### 계획됨 (Planned)
- **다중 페이지 처리 지원**:
  - 최대 100페이지 자동 처리
  - 10페이지 단위 이동 지원
  - 연속 오류 처리 (3회 연속 실패 시 중단)
- **안정성 개선**:
  - 무한 루프 방지
  - Stale Element 처리
  - 프레임 관리 개선
- **새 메서드 추가 계획**:
  - `_move_to_next_page()` - 페이지 이동
  - `_move_to_next_page_group()` - 10페이지 단위 이동
  - `_wait_for_page_load()` - 로딩 대기
  - `_get_current_page_number()` - 현재 페이지 확인
  - `_return_to_document_list()` - 문서 목록 복귀
  - `_recover_to_document_list()` - 복구 로직

---

## [2025-11-XX] - 프로젝트 구조 개선

### 추가됨 (Added)
- **헤드리스 모드 지원**:
  - `.env`: `HEADLESS_MODE` 설정
  - 백그라운드 실행 가능
- **GUI 설정 관리**:
  - `src/gui/settings_dialog.py` 개선
  - 모든 .env 설정을 GUI에서 수정 가능

### 변경됨 (Changed)
- **프로젝트 구조 재편**:
  - `src/` 디렉토리 생성 및 소스 코드 이동
  - `data/` 디렉토리 생성 (PDF, Excel 출력)
  - 논리적 폴더 구조: `core/`, `utils/`, `gui/`, `services/`, `config/`
- **UI 자동화 견고성 향상**:
  - `time.sleep()` → `WebDriverWait` 전환
  - 동적 대기 조건 적용
  - 오류 처리 로직 개선

### 수정됨 (Fixed)
- **Selenium 오류 수정**:
  - `AttributeError` 및 `SyntaxError` 수정
  - XPath 오류 수정 (`starts-with()` 활용)
  - 검색 결과 없음 처리

---

## 프로젝트 통계

### 크기 최적화
- **이전**: 445MB
- **이후**: 3.7MB
- **감소율**: 99%

### Google Sheets API 최적화
- **이전**: 100개 문서 = 100회 API 호출
- **이후**: 100개 문서 = 2회 API 호출
- **개선율**: 98%

### 설정 파일
- **중앙화**: 하드코딩 제거, `config.json` 통합
- **보안**: 인증 정보 `.env` 관리
- **유지보수성**: GUI를 통한 설정 변경

---

## 다음 계획

### Phase 2 (향후)
- [ ] 페이지네이션 구현 (계획 완료, 구현 대기)
- [ ] Google Sheets Incremental Update
- [ ] 단위 테스트 작성
- [ ] 로그 가독성 향상
- [ ] 에러 발생 시 알림 기능 (이메일, 메신저)
- [ ] PDF 저장 재시도 로직

---

**마지막 업데이트**: 2025-12-03
**버전**: 3.1
