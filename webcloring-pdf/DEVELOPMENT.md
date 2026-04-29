# 개발 문서 (Development Guide)

> INTEROJO 포털 자동화 시스템 기술 문서

**버전**: 3.1
**최종 업데이트**: 2025-12-03
**Python**: 3.8+

---

## 목차

1. [프로젝트 개요](#프로젝트-개요)
2. [아키텍처](#아키텍처)
3. [주요 기능](#주요-기능)
4. [Google Sheets 통합](#google-sheets-통합)
5. [페이지네이션 계획](#페이지네이션-계획)
6. [개발 환경 설정](#개발-환경-설정)
7. [코드 구조](#코드-구조)
8. [테스트](#테스트)
9. [문제 해결](#문제-해결)

---

## 프로젝트 개요

INTEROJO 포털에서 자재 요청 문서를 자동으로 검색하고, PDF로 저장하며, Excel 파일로 데이터를 정리하는 Python 자동화 시스템입니다.

### 핵심 기술 스택
- **Selenium WebDriver**: 웹 자동화
- **openpyxl**: Excel 파일 처리
- **gspread**: Google Sheets API
- **tkinter**: GUI
- **python-dotenv**: 환경 변수 관리

### 주요 개선 목표
1. **코드베이스 정리**: 불필요한 파일 제거 및 논리적 구조 재편
2. **자동화 견고성 향상**: UI 자동화 안정성과 신뢰도 개선
3. **기능 확장**: 사용자 편의성을 위한 새로운 기능 추가
4. **설정 관리 효율화**: GUI를 통한 설정 변경 및 저장

---

## 아키텍처

### 프로젝트 구조

```
PythonProject5-pdf/
├── src/                        # 소스 코드
│   ├── core/                   # 핵심 로직
│   │   ├── portal_automation.py    # 포털 자동화 메인 클래스
│   │   └── excel_manager.py        # Excel 데이터 관리
│   ├── services/               # 외부 서비스 연동
│   │   └── google_sheets_manager.py    # Google Sheets API
│   ├── gui/                    # GUI 인터페이스
│   │   ├── main_window.py          # 메인 윈도우
│   │   ├── settings_dialog.py      # 설정 창
│   │   └── google_sheets_dialog.py # Google Sheets 설정 창
│   ├── utils/                  # 유틸리티
│   │   ├── logger.py               # 로깅
│   │   └── error_handler.py        # 에러 처리
│   └── config/                 # 설정
│       ├── settings.py             # 설정 로더
│       ├── config.json             # 중앙 설정 파일
│       └── google_sheets_settings.json
├── data/                       # 데이터 출력
│   ├── PDF/                    # PDF 파일 저장
│   └── excel/                  # Excel 파일 저장
├── logs/                       # 로그 파일
├── .env                        # 환경 변수
├── requirements_service.txt    # 패키지 의존성
└── main.py                     # 진입점
```

### 실행 흐름

```
main.py
  ↓
GUI Mode (main_window.py)
  ↓
AutomationController
  ↓
PortalAutomation.run_automation()
  ↓
┌─────────────────────────────────┐
│ 1. setup_driver()               │ - ChromeDriver 설정
│ 2. login_to_portal()            │ - 포털 로그인
│ 3. navigate_to_electronic_approval()  - 전자결재 이동
│ 4. navigate_to_completed_documents()  - 완료문서함 이동
│ 5. search_documents()          │ - 문서 검색
│ 6. change_page_size()          │ - 페이지 크기 50으로 변경
│ 7. process_document_list()     │ - 문서 목록 처리
│    ├── collect_document_list() │   - 문서 정보 수집
│    └── process_document()      │   - 개별 문서 처리
│         ├── PDF 저장           │
│         └── Excel 저장         │
└─────────────────────────────────┘
  ↓
finalize_google_backup()        - Google Sheets 백업
  ↓
driver.quit()                   - 브라우저 종료
```

---

## 주요 기능

### 1. UI 자동화 견고성

#### Before: 고정 지연 시간
```python
time.sleep(5)  # 고정 대기
```

#### After: 동적 대기 조건
```python
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 요소가 클릭 가능할 때까지 대기
element = self.wait.until(
    EC.element_to_be_clickable((By.NAME, "pagePerRecord"))
)
```

#### 적용된 개선 사항

| 메서드 | 개선 내용 |
|--------|-----------|
| `login_to_portal` | URL 변경 또는 특정 요소 출현 대기 |
| `navigate_to_electronic_approval` | 전자결재 페이지 URL 변경 및 핵심 요소 대기 |
| `navigate_to_completed_documents` | 검색 폼 출현 대기 |
| `search_documents` | 결과 테이블 로드 대기 |
| `change_page_size` | 페이지 크기 변경 후 테이블 리로드 대기 |
| `process_document` | 문서 상세 페이지 로딩 및 목록 복귀 대기 |

### 2. 헤드리스 모드

브라우저 창을 띄우지 않고 백그라운드에서 자동화 실행 가능.

**.env 설정**:
```bash
HEADLESS_MODE=True  # 헤드리스 모드 활성화
```

**구현** (`src/core/portal_automation.py`):
```python
def setup_driver(self):
    chrome_options = Options()

    if settings.headless_mode:
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-gpu')

    # ...
```

### 3. 설정 관리

#### 중앙화된 설정 파일 (`src/config/config.json`)

```json
{
  "excel": {
    "auto_save_interval": 300
  },
  "google_sheets": {
    "min_backup_interval": 60,
    "batch_processing": true
  },
  "pagination": {
    "max_pages": 100,
    "max_consecutive_errors": 3,
    "page_size": 50
  }
}
```

#### 설정 접근 (`src/config/settings.py`)

```python
class Settings:
    @property
    def auto_save_interval(self) -> int:
        """Excel 자동 저장 간격 (초)"""
        return self.config.get("excel", {}).get("auto_save_interval", 300)

    @property
    def min_backup_interval(self) -> int:
        """Google Sheets 최소 백업 간격 (초)"""
        return self.config.get("google_sheets", {}).get("min_backup_interval", 60)
```

#### GUI 설정 변경

`src/gui/settings_dialog.py`를 통해 모든 `.env` 설정을 GUI에서 수정 가능:
- 사용자 인증 정보
- 검색 시작 날짜
- 동적 필터링
- 헤드리스 모드
- 스케줄 설정

---

## Google Sheets 통합

### 개요

**버전**: v3.0
**목표**: Excel 데이터를 Google Sheets에 자동 백업

### 주요 특징

#### 1. Lazy Loading
```python
class ExcelManager:
    def __init__(self):
        # 초기화 시 생성하지 않음
        self._google_sheets_manager = None

    @property
    def google_sheets_manager(self):
        """처음 접근 시에만 초기화"""
        if self._google_sheets_manager is None and GOOGLE_SHEETS_AVAILABLE:
            self._google_sheets_manager = GoogleSheetsManager()
        return self._google_sheets_manager
```

**효과**: 초기 로딩 시간 단축

#### 2. 배치 처리 (Batch Processing)

**Before**: 문서당 백업 (100개 문서 = 100회 API 호출)
```python
def save_material_data(self, data):
    # Excel 저장
    self.save_to_excel(data)

    # 매번 백업 (비효율적)
    self.google_sheets_manager.backup_single_row(data)  # ❌
```

**After**: 자동화 종료 시 1회 백업 (2회 API 호출)
```python
def finalize_google_backup(self) -> bool:
    """자동화 종료 시 전체 백업 (배치 처리)"""
    # 1. Excel 강제 저장
    self.force_save()

    # 2. 전체 데이터 백업 (1회)
    self.google_sheets_manager.backup_materials(
        excel_manager=self,
        silent=False
    )
```

**효과**: API 호출 98% 감소

#### 3. Rate Limiting

```python
class GoogleSheetsManager:
    def __init__(self):
        self.last_backup_time = None
        self.min_backup_interval = settings.min_backup_interval  # 60초

    def backup_materials(self, excel_manager, silent=False):
        # 최소 간격 체크
        if self.last_backup_time:
            elapsed = time.time() - self.last_backup_time
            if elapsed < self.min_backup_interval:
                logger.warning(f"백업 간격 부족 ({elapsed:.0f}초)")
                return False
```

**효과**: Google Sheets API 쿼터 초과 방지

#### 4. Threading (GUI 프리징 방지)

```python
def backup_now(self):
    """백업 버튼 클릭 핸들러"""
    def backup_thread():
        # 별도 스레드에서 백업 실행
        excel_manager = ExcelManager()
        success = self.manager.backup_materials(excel_manager)

        # UI 업데이트 (메인 스레드)
        self.root.after(0, lambda: self.show_result(success))

    # 스레드 시작
    threading.Thread(target=backup_thread, daemon=True).start()
```

**효과**: 백업 중에도 GUI 응답 유지

### API 호출 최적화

#### Clear & Update 방식

```python
def _upload_to_sheet(self, data):
    """전체 데이터를 Clear & Update 방식으로 업로드"""
    # 1. 기존 데이터 삭제
    worksheet.clear()  # API Call 1

    # 2. 새 데이터 업로드
    worksheet.update(
        range_name='A1',
        values=data
    )  # API Call 2
```

**총 API 호출**: 2회

### 성능 비교

| 항목 | Before | After | 개선율 |
|------|--------|-------|--------|
| API 호출 (100개 문서) | 100회 | 2회 | 98% ↓ |
| 백업 시간 | ~100초 | ~2초 | 98% ↓ |
| GUI 프리징 | 100초 | 0초 | 100% ↓ |

### 사용 방법

#### 1. Google Cloud Console 설정
1. https://console.cloud.google.com/ 접속
2. 새 프로젝트 생성
3. Google Sheets API 활성화
4. 서비스 계정 생성 (역할: 편집자)
5. JSON 키 파일 다운로드 → `src/config/` 폴더에 저장

#### 2. Google Sheets 준비
1. 새 Google 시트 생성
2. 서비스 계정 이메일을 시트에 "편집자" 권한으로 공유
3. 시트 URL 복사

#### 3. 프로그램 설정
1. GUI 실행: `실행.bat` 또는 `python main.py`
2. "Google Sheets" 버튼 클릭
3. JSON 파일 선택 및 시트 URL 입력
4. "연결 테스트" → 성공 확인
5. "설정 저장"

#### 4. 자동 백업
- 자동화 실행 시 자동으로 백업 (자동화 종료 시 1회)
- 백업 실패해도 Excel 파일은 정상 저장

#### 5. 수동 백업
- "Google Sheets" 버튼 → "지금 백업하기"
- 백업 진행 중에도 GUI 응답 유지

---

## 페이지네이션 계획

> **상태**: 계획 완료, 구현 대기
> **버전**: v2.0
> **목표**: 다중 페이지 자동 처리

### 현재 상태
- 최대 50개 문서 처리 (1페이지)
- 사용자가 수동으로 페이지 이동 필요

### 개선 목표
- 최대 100페이지 자동 처리 (5,000개 문서)
- 10페이지 단위 이동 지원
- 연속 오류 처리 (3회 연속 실패 시 중단)

### 구현 계획

#### 1. 페이지 이동 메서드

```python
def _move_to_next_page(self, target_page: int) -> bool:
    """다음 페이지로 이동

    Args:
        target_page: 이동할 페이지 번호

    Returns:
        bool: 이동 성공 여부
    """
    try:
        # 숫자 버튼으로 이동 시도
        xpath_next_btn = f"//div[contains(@class, 'paging')]//a[contains(text(), '{target_page}')]"
        next_btn = self.driver.find_element(By.XPATH, xpath_next_btn)

        # JavaScript 클릭 (검증된 방식)
        self.driver.execute_script("arguments[0].click();", next_btn)

        # 페이지 로딩 확인
        self._wait_for_page_load(target_page)

        return True

    except NoSuchElementException:
        # 숫자 버튼이 없으면 10페이지 단위 이동
        return self._move_to_next_page_group()
```

#### 2. 다중 페이지 처리

```python
def process_document_list(self):
    """문서 목록 처리 (다중 페이지 지원)"""
    MAX_PAGES = 100
    MAX_CONSECUTIVE_ERRORS = 3

    current_page = 1
    total_processed = 0
    consecutive_errors = 0

    while current_page <= MAX_PAGES:
        try:
            # 1. 현재 페이지 문서 목록 수집
            doc_list = self.collect_document_list()

            # 2. 각 문서 처리
            for doc_info in doc_list:
                self.process_document(doc_info)
                total_processed += 1

            # 3. 다음 페이지로 이동
            if not self._move_to_next_page(current_page + 1):
                break  # 마지막 페이지

            current_page += 1
            consecutive_errors = 0  # 성공 시 리셋

        except Exception as e:
            consecutive_errors += 1
            logger.error(f"페이지 {current_page} 처리 오류: {e}")

            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                logger.error("연속 오류 한계 도달, 처리 중단")
                break

    logger.info(f"총 처리 문서: {total_processed}건, 페이지: {current_page}")
```

### 안정성 개선

1. **무한 루프 방지**: 최대 100페이지 제한
2. **연속 오류 처리**: 3회 연속 실패 시 자동 중단
3. **Stale Element 처리**: 페이지 전환 시 DOM 변경 대응
4. **프레임 관리**: iframe 컨텍스트 유실 방지

### XPath 참고

```xpath
# 현재 활성화된 페이지
//div[contains(@class, 'paging')]//a[contains(@class, 'fColor')]

# 특정 페이지 번호 버튼
//div[contains(@class, 'paging')]//a[contains(text(), '3')]

# 다음 10페이지 버튼
//div[contains(@class, 'paging')]//a[contains(@class, 'next')]
```

### 테스트 계획

- [ ] 1~5페이지 처리 (일반 케이스)
- [ ] 11~20페이지 처리 (10페이지 단위 이동)
- [ ] 최대 페이지 제한 테스트
- [ ] 연속 오류 처리 테스트
- [ ] 엣지 케이스 (문서 0개, 1개, 정확히 50개)

---

## 개발 환경 설정

### 1. 필수 패키지 설치

#### 방법 1: 배치 파일 사용 (권장)
```bash
패키지설치.bat
```

#### 방법 2: 수동 설치
```bash
# 가상환경 생성
python -m venv .venv

# 가상환경 활성화 (Windows)
.venv\Scripts\activate

# 패키지 설치
pip install -r requirements_service.txt
```

### 2. 환경 변수 설정

`.env` 파일 생성:
```bash
# 포털 인증
PORTAL_USERNAME=your_username
PORTAL_PASSWORD=your_password
PORTAL_URL=http://portal.interojo.com/portal/main/portalMain.do

# 검색 설정
SEARCH_START_DATE=2025.01.01
SEARCH_KEYWORD=자재
DYNAMIC_FILTERING=True
DAYS_BACK=0

# 실행 모드
HEADLESS_MODE=False
DEBUG_MODE=False

# 자동화 스케줄
AUTO_ENABLED=False
SCHEDULE_TIME=09:00
WEEKDAYS_ONLY=False
```

### 3. Google Sheets 설정 (선택)

1. 서비스 계정 JSON 키 파일을 `src/config/` 폴더에 저장
2. GUI에서 "Google Sheets" 버튼 클릭하여 설정

### 4. 실행

#### GUI 모드
```bash
실행.bat
# 또는
python main.py
```

#### 콘솔 자동화 모드
```bash
자동화실행.bat
# 또는
python main.py --console
```

#### 빌드 (실행 파일 생성)

**⚠️ 중요: 상세한 빌드 가이드는 [BUILD_GUIDE.md](BUILD_GUIDE.md)를 참조하세요.**

**권장 빌드 방법** (PyInstaller 직접 실행):
```bash
# 1. 이전 빌드 정리
rm -rf build dist

# 2. 빌드 실행
python -m PyInstaller automation.spec --noconfirm --clean

# 3. 결과 확인
ls -lh dist/interojo_automation/
```

**주의사항**:
- ✅ **numpy 포함 필수** - openpyxl 의존성
- ✅ **automation.spec 사용** - 프로젝트 구조 반영
- ⚠️ build.py 사용 시 인코딩 오류 발생 가능

**빌드 결과**:
- 실행 파일: `interojo_automation.exe` (9.5 MB)
- 전체 크기: 99 MB (numpy 포함)
- 위치: `dist/interojo_automation/`

---

## 코드 구조

### 핵심 클래스

#### 1. PortalAutomation (`src/core/portal_automation.py`)

포털 자동화의 메인 클래스.

**주요 메서드**:
- `setup_driver()`: ChromeDriver 설정
- `login_to_portal()`: 포털 로그인
- `search_documents()`: 문서 검색
- `process_document_list()`: 문서 목록 처리
- `process_document(doc_info)`: 개별 문서 처리

**WebDriverWait 사용 예시**:
```python
def search_documents(self):
    # 검색 버튼 클릭
    search_btn = self.wait.until(
        EC.element_to_be_clickable((By.ID, "btnSearch"))
    )
    search_btn.click()

    # 결과 테이블 로드 대기
    self.wait.until(
        EC.presence_of_element_located((By.XPATH, "//tbody//tr"))
    )
```

#### 2. ExcelManager (`src/core/excel_manager.py`)

Excel 파일 관리 클래스.

**주요 메서드**:
- `save_material_data(data)`: 자재 데이터 저장
- `is_document_processed(doc_id)`: 중복 확인
- `force_save()`: 강제 저장
- `finalize_google_backup()`: Google Sheets 백업

**자동 저장**:
```python
def __init__(self):
    self.auto_save_interval = settings.auto_save_interval  # 300초
    self.last_save_time = time.time()

def save_material_data(self, data):
    # 데이터 저장
    # ...

    # 자동 저장 체크
    if time.time() - self.last_save_time >= self.auto_save_interval:
        self.force_save()
```

#### 3. GoogleSheetsManager (`src/services/google_sheets_manager.py`)

Google Sheets API 관리 클래스.

**주요 메서드**:
- `setup_connection()`: Google Sheets 연결
- `backup_materials(excel_manager)`: 배치 백업
- `_prepare_backup_data(excel_manager)`: 데이터 추출
- `_upload_to_sheet(data)`: Clear & Update 업로드

**Rate Limiting**:
```python
def backup_materials(self, excel_manager, silent=False):
    # 최소 간격 체크
    if self.last_backup_time:
        elapsed = time.time() - self.last_backup_time
        if elapsed < self.min_backup_interval:
            return False

    # 백업 실행
    # ...

    self.last_backup_time = time.time()
```

#### 4. MainWindow (`src/gui/main_window.py`)

메인 GUI 클래스.

**주요 기능**:
- 자동화 시작/중지
- 설정 관리
- Google Sheets 설정
- 로그 표시

**스레드 기반 자동화**:
```python
def start_automation(self):
    """자동화 시작 (별도 스레드)"""
    def automation_thread():
        controller = AutomationController()
        controller.run()

    threading.Thread(target=automation_thread, daemon=True).start()
```

---

## 테스트

### 단위 테스트 (향후 계획)

```python
# tests/test_excel_manager.py
import unittest
from src.core.excel_manager import ExcelManager

class TestExcelManager(unittest.TestCase):
    def setUp(self):
        self.manager = ExcelManager()

    def test_save_material_data(self):
        data = {
            'document_id': 'TEST001',
            'title': 'Test Material',
            # ...
        }
        result = self.manager.save_material_data(data)
        self.assertTrue(result)

    def test_is_duplicate(self):
        self.manager.save_material_data({'document_id': 'DUP001'})
        self.assertTrue(self.manager.is_document_processed('DUP001'))
```

### 통합 테스트

```python
# tests/test_integration.py
def test_full_automation():
    """전체 자동화 플로우 테스트"""
    automation = PortalAutomation()

    # 1. 드라이버 설정
    automation.setup_driver()

    # 2. 로그인
    assert automation.login_to_portal()

    # 3. 문서 검색
    assert automation.search_documents()

    # 4. 문서 처리
    assert automation.process_document_list()

    # 5. 정리
    automation.driver.quit()
```

---

## 문제 해결

### 1. Selenium 관련 오류

#### ChromeDriver 버전 불일치
**증상**: `SessionNotCreatedException`

**해결**:
```bash
# 자동으로 ChromeDriver 다운로드 (권장)
pip install webdriver-manager
```

```python
from webdriver_manager.chrome import ChromeDriverManager

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service)
```

#### Stale Element Reference
**증상**: `StaleElementReferenceException`

**원인**: DOM 변경으로 요소 참조 무효화

**해결**:
```python
# 페이지 로딩 대기
self.wait.until(EC.staleness_of(old_element))

# 요소 재검색
new_element = self.driver.find_element(By.ID, "element_id")
```

### 2. Google Sheets API 오류

#### invalid_grant: account not found
**증상**: 인증 실패

**해결**:
1. 올바른 JSON 키 파일 사용 확인
2. 서비스 계정 이메일을 시트에 공유했는지 확인
3. JSON 키 파일이 만료되지 않았는지 확인

#### API quota exceeded
**증상**: `APIError: Quota exceeded`

**해결**:
- Rate Limiting 설정 확인 (`min_backup_interval` ≥ 60초)
- 배치 처리 사용 (자동화 종료 시 1회 백업)

### 3. Excel 파일 오류

#### PermissionError
**증상**: 파일이 다른 프로그램에서 열려 있음

**해결**:
```python
# 파일 닫기 확인
workbook.close()

# 또는 강제 저장
self.force_save()
```

### 4. GUI 프리징

**증상**: 백업 중 GUI 응답 없음

**해결**: Threading 사용
```python
def backup_now(self):
    def backup_thread():
        # 백업 작업
        pass

    threading.Thread(target=backup_thread, daemon=True).start()
```

### 5. 한글 깨짐

**증상**: 로그에 한글이 `???`로 표시

**원인**: Windows 터미널 인코딩 (cp949)

**해결**:
```python
# logger.py
import sys
sys.stdout.reconfigure(encoding='utf-8')
```

또는 터미널 설정:
```bash
chcp 65001  # UTF-8 코드 페이지
```

---

## 참고 자료

### 공식 문서
- **Selenium**: https://www.selenium.dev/documentation/
- **openpyxl**: https://openpyxl.readthedocs.io/
- **gspread**: https://docs.gspread.org/
- **Google Sheets API**: https://developers.google.com/sheets/api

### 프로젝트 문서
- [README.md](README.md) - 사용자 가이드
- [CHANGELOG.md](CHANGELOG.md) - 변경 이력
- [docs/](docs/) - 상세 기술 문서

---

**마지막 업데이트**: 2025-12-03
**작성자**: Development Team
**버전**: 3.1
