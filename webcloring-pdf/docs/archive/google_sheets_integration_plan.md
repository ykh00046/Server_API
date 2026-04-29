# INTEROJO 프로젝트 - 구글 시트 통합 계획서

**작성일**: 2025-12-01
**버전**: 1.0
**통합 방식**: 옵션 A - 단계적 통합 (안정적이고 기능 풍부)

---

## 📋 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [현재 상황 분석](#2-현재-상황-분석)
3. [PythonProject3 구글 시트 기능 상세 분석](#3-pythonproject3-구글-시트-기능-상세-분석)
4. [INTEROJO와의 차이점](#4-interojo와의-차이점)
5. [통합 아키텍처](#5-통합-아키텍처)
6. [단계별 구현 계획](#6-단계별-구현-계획)
7. [파일별 상세 변경 사항](#7-파일별-상세-변경-사항)
8. [데이터 구조 매핑](#8-데이터-구조-매핑)
9. [의존성 및 환경 설정](#9-의존성-및-환경-설정)
10. [테스트 계획](#10-테스트-계획)
11. [예상 문제점 및 해결 방안](#11-예상-문제점-및-해결-방안)
12. [배포 및 사용자 가이드](#12-배포-및-사용자-가이드)

---

## 1. 프로젝트 개요

### 1.1 목적
INTEROJO 포털 자동화 시스템에 구글 시트 백업 기능을 추가하여:
- Excel 파일 외에 구글 시트로도 데이터 실시간 백업
- 여러 사용자가 동시에 데이터 조회 가능
- 클라우드 기반 데이터 보관으로 유실 방지
- 외부에서도 데이터 접근 가능

### 1.2 통합 범위
- **재사용**: PythonProject3의 검증된 백업 로직 (google_sheets_backup.py, google_sheets_config.py)
- **새로 작성**: tkinter 기반 UI (PyQt5 → tkinter 변환)
- **확장**: ExcelManager에 구글 시트 동기화 기능 추가
- **통합**: settings.py에 구글 시트 설정 추가

---

## 2. 현재 상황 분석

### 2.1 INTEROJO 프로젝트 구조

```
C:\X\PythonProject\PythonProject5-pdf\
├── src/
│   ├── core/
│   │   ├── excel_manager.py          # Excel 파일 관리 (563줄)
│   │   ├── portal_automation.py      # 포털 자동화 로직 (450줄)
│   │   └── scheduler.py              # 스케줄링
│   ├── gui/
│   │   ├── main_window.py            # tkinter 메인 윈도우 (433줄)
│   │   └── settings_dialog.py        # tkinter 설정 다이얼로그 (326줄)
│   ├── config/
│   │   └── settings.py               # .env 기반 설정 관리 (326줄)
│   ├── utils/
│   │   └── logger.py                 # 로깅 유틸리티
│   └── services/                     # (신규 생성 필요)
├── data/
│   ├── excel/
│   │   └── Material_Release_Request.xlsx
│   └── PDF/
├── main.py                           # 진입점
├── automation.spec                   # PyInstaller 설정
└── .env                              # 환경변수 설정
```

### 2.2 주요 특징
- **GUI 프레임워크**: tkinter (PythonProject3은 PyQt5)
- **설정 방식**: .env 파일 + JSON config (PythonProject3은 JSON만)
- **데이터 구조**: 자재 요청 데이터 (9개 컬럼)
- **Excel 컬럼**:
  ```
  순번, 자재코드, 품명, 요청수량(g단위), 사유, 요청부서, 기안자, 문서번호, 처리일시
  ```

### 2.3 ExcelManager 핵심 기능 분석

#### 2.3.1 초기화 및 워크북 관리
```python
# excel_manager.py:25-43
def __init__(self, file_path: Optional[str] = None):
    self.file_path = Path(file_path) if file_path else settings.excel_file_path
    self.workbook = None
    self.worksheet = None
    self.current_row = 1
    self.columns = ["순번", "자재코드", "품명", "요청수량(g단위)",
                   "사유", "요청부서", "기안자", "문서번호", "처리일시"]
    self.processed_documents = set()  # 중복 방지
    self.last_save_time = None
    self.auto_save_interval = 300  # 5분마다 자동 저장
```

#### 2.3.2 데이터 추가 메서드
```python
# excel_manager.py:125-167
def add_row(self, data: Dict[str, str]):
    """새 행 추가 - 구글 시트와 동일한 데이터를 받아야 함"""

# excel_manager.py:483-552
def save_material_data(self, table_rows, drafter, document_number, department):
    """자재 데이터 저장 (portal_automation.py에서 호출)"""
    # 이 메서드에서 구글 시트 백업을 트리거해야 함
```

#### 2.3.3 중복 방지 및 추적
```python
# excel_manager.py:299-311
def _load_processed_documents(self):
    """기존 파일에서 처리된 문서 ID 로드"""
    # 구글 시트에서도 동일한 중복 방지 필요
```

---

## 3. PythonProject3 구글 시트 기능 상세 분석

### 3.1 google_sheets_backup.py (325줄)

#### 3.1.1 클래스 구조
```python
class GoogleSheetsBackup:
    """구글 시트 백업 클래스 - INTEROJO로 포팅 필요"""

    def __init__(self):
        self.client = None          # gspread 클라이언트
        self.spreadsheet = None     # 스프레드시트 객체
        self.worksheet = None       # 워크시트 객체
        self.is_connected = False   # 연결 상태
        self.config = GoogleSheetsConfig()  # 설정 관리자
```

#### 3.1.2 핵심 메서드 분석

**1) 연결 설정 (setup_connection)**
```python
# google_sheets_backup.py:28-69
def setup_connection(self, credentials_file: str, spreadsheet_url: str) -> bool:
    """
    Service Account JSON 파일로 구글 시트 연결

    Args:
        credentials_file: Service Account JSON 파일 경로
        spreadsheet_url: 구글 스프레드시트 URL

    Returns:
        bool: 연결 성공 여부

    구현 로직:
    1. OAuth2 Credentials 생성 (spreadsheets scope)
    2. gspread 클라이언트 생성 및 인증
    3. 스프레드시트 열기 (URL 기반)
    4. 첫 번째 워크시트 선택
    5. 설정 저장 (GoogleSheetsConfig)
    """
    scope = ['https://www.googleapis.com/auth/spreadsheets']
    credentials = Credentials.from_service_account_file(credentials_file, scopes=scope)
    self.client = gspread.authorize(credentials)
    self.spreadsheet = self.client.open_by_url(spreadsheet_url)
    self.worksheet = self.spreadsheet.sheet1

    # 설정 저장
    self.config.set_credentials_file(credentials_file)
    self.config.set_spreadsheet_url(spreadsheet_url)
    self.config.set_backup_enabled(True)
```

**2) 데이터 백업 (backup_mixing_records)**
```python
# google_sheets_backup.py:71-132
def backup_mixing_records(self, data_manager, silent: bool = False) -> bool:
    """
    배합 기록을 구글 시트에 백업

    INTEROJO 적용 시:
    - data_manager → ExcelManager 인스턴스
    - mixing_records → 자재 요청 데이터

    백업 프로세스:
    1. 데이터 로드 (DataFrame 형식)
    2. 헤더 + 데이터 준비
    3. 시트 전체 클리어
    4. 배치 업데이트 (한 번에 업로드)
    5. 헤더 포맷팅 (굵게, 배경색)
    6. 백업 통계 업데이트
    """
    records_df = data_manager.load_records()

    # 헤더 준비
    headers = list(records_df.columns)

    # 데이터 준비
    data_rows = records_df.values.tolist()

    # 전체 데이터 (헤더 + 데이터)
    all_data = [headers] + data_rows

    # 시트 클리어 후 업데이트
    self.worksheet.clear()
    self.worksheet.update(range_name='A1', values=all_data)

    # 헤더 포맷팅
    self._format_header()
```

**3) 연결 테스트 (test_connection)**
```python
# google_sheets_backup.py:134-167
def test_connection(self) -> Dict[str, Any]:
    """
    구글 시트 연결 테스트

    Returns:
        {
            'success': True/False,
            'spreadsheet_name': '스프레드시트 이름',
            'worksheet_name': '워크시트 이름',
            'message': '상태 메시지'
        }
    """
```

**4) 샘플 데이터 생성 (create_sample_data)**
```python
# google_sheets_backup.py:169-201
def create_sample_data(self) -> bool:
    """테스트용 샘플 데이터 생성"""
    # INTEROJO에서는 자재 요청 샘플 데이터로 변경 필요
```

#### 3.1.3 헤더 포맷팅
```python
# google_sheets_backup.py:203-241
def _format_header(self):
    """
    헤더 행 포맷팅
    - 굵은 글씨
    - 배경색 (파란색)
    - 텍스트 가운데 정렬
    """
    header_format = {
        'backgroundColor': {'red': 0.2, 'green': 0.4, 'blue': 0.6},
        'textFormat': {'bold': True, 'foregroundColor': {'red': 1, 'green': 1, 'blue': 1}},
        'horizontalAlignment': 'CENTER'
    }
```

### 3.2 google_sheets_config.py (168줄)

#### 3.2.1 설정 파일 관리
```python
class GoogleSheetsConfig:
    """JSON 기반 설정 관리"""

    def __init__(self):
        self.config_file = 'config/google_sheets_settings.json'
        self.config = {
            'credentials_file': '',      # Service Account JSON 경로
            'spreadsheet_url': '',       # 구글 시트 URL
            'last_backup_time': None,    # 마지막 백업 시간
            'backup_enabled': False,     # 백업 활성화 여부
            'auto_backup_on_save': True, # 저장 시 자동 백업
            'backup_success_count': 0,   # 성공 횟수
            'backup_failure_count': 0    # 실패 횟수
        }
```

#### 3.2.2 휴대용 실행파일 지원
```python
# google_sheets_config.py:55-86
def get_credentials_file(self) -> str:
    """
    인증 파일 경로 반환 (휴대용 실행파일 지원)

    경로 우선순위:
    1. 절대 경로가 존재하면 반환
    2. config 폴더에서 상대 경로로 찾기
    3. 실행파일 디렉토리의 config 폴더에서 찾기

    INTEROJO에 적용:
    - PyInstaller 실행파일에서도 JSON 파일 찾을 수 있도록
    - settings.py의 base_dir 로직과 통합 필요
    """
```

#### 3.2.3 백업 통계 추적
```python
# google_sheets_config.py:131-160
def increment_backup_success(self):
    """백업 성공 횟수 증가 및 저장"""

def increment_backup_failure(self):
    """백업 실패 횟수 증가 및 저장"""

def get_backup_status_text(self) -> str:
    """백업 상태 텍스트 반환 (UI 표시용)"""
    # 예: "마지막 백업: 2025-12-01 14:30:00 (성공:15, 실패:2)"
```

### 3.3 google_sheets_dialog.py (383줄, PyQt5)

#### 3.3.1 UI 구성 요소
```python
class GoogleSheetsSetupDialog(QDialog):
    """
    구글 시트 설정 다이얼로그 (PyQt5)

    INTEROJO 변환 필요:
    PyQt5 → tkinter
    QDialog → tk.Toplevel
    QLineEdit → ttk.Entry
    QPushButton → ttk.Button
    QProgressBar → ttk.Progressbar
    """
```

#### 3.3.2 주요 기능
1. **JSON 인증 파일 선택** (browse_credentials_file)
2. **구글 시트 URL 입력**
3. **연결 테스트** (test_connection)
4. **전체 백업 실행** (run_backup)
5. **샘플 데이터 생성** (create_sample_data)
6. **설정 가이드 보기** (show_setup_guide)

---

## 4. INTEROJO와의 차이점

### 4.1 기술 스택 차이

| 항목 | PythonProject3 | INTEROJO | 통합 방법 |
|------|----------------|----------|-----------|
| GUI | PyQt5 | tkinter | tkinter로 재작성 |
| 설정 저장 | JSON만 | .env + JSON | .env에 통합 |
| 로깅 | logger.py | logger.py | 동일하게 사용 |
| 데이터 구조 | 배합 기록 (DataFrame) | 자재 요청 (Dict 리스트) | 매핑 필요 |

### 4.2 데이터 구조 차이

#### PythonProject3 (배합 기록)
```python
columns = [
    "날짜", "시간", "배합번호", "제품명", "수량(kg)",
    "원료1", "원료2", "원료3", "비고"
]
```

#### INTEROJO (자재 요청)
```python
columns = [
    "순번", "자재코드", "품명", "요청수량(g단위)",
    "사유", "요청부서", "기안자", "문서번호", "처리일시"
]
```

### 4.3 설정 관리 차이

#### PythonProject3
```json
// google_sheets_settings.json
{
    "credentials_file": "config/credentials.json",
    "spreadsheet_url": "https://docs.google.com/...",
    "backup_enabled": true,
    "auto_backup_on_save": true
}
```

#### INTEROJO (목표)
```env
# .env 파일에 추가
GOOGLE_SHEETS_ENABLED=true
GOOGLE_SHEETS_CREDENTIALS=config/google_sheets_credentials.json
GOOGLE_SHEETS_URL=https://docs.google.com/spreadsheets/d/...
GOOGLE_SHEETS_AUTO_BACKUP=true
```

---

## 5. 통합 아키텍처

### 5.1 새로운 폴더 구조
```
C:\X\PythonProject\PythonProject5-pdf\
├── src/
│   ├── services/                     # 신규 생성
│   │   ├── __init__.py
│   │   └── google_sheets_manager.py  # PythonProject3 로직 포팅
│   ├── gui/
│   │   ├── main_window.py
│   │   ├── settings_dialog.py        # 수정: 구글 시트 섹션 추가
│   │   └── google_sheets_dialog.py   # 신규: tkinter로 재작성
│   ├── config/
│   │   ├── settings.py               # 수정: 구글 시트 설정 추가
│   │   ├── config.json
│   │   ├── google_sheets_settings.json  # 신규: 구글 시트 전용 설정
│   │   └── google_sheets_credentials.json  # 사용자 제공 (gitignore)
│   └── core/
│       └── excel_manager.py          # 수정: 구글 시트 동기화 추가
├── .env                              # 수정: 구글 시트 환경변수 추가
├── .gitignore                        # 수정: credentials.json 제외
├── requirements.txt                  # 수정: gspread 추가
└── automation.spec                   # 수정: 구글 관련 모듈 추가
```

### 5.2 클래스 다이어그램
```
┌─────────────────────────────────────────────────────────────┐
│                    AutomationGUI (main_window.py)           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  - run_now()                                         │   │
│  │  - open_settings()                                   │   │
│  │  - open_google_sheets_settings()  (신규)            │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │
                            ↓
        ┌───────────────────────────────────────┐
        │   SettingsDialog (settings_dialog.py) │
        │  ┌─────────────────────────────────┐  │
        │  │  - 로그인 정보                  │  │
        │  │  - 검색 설정                    │  │
        │  │  - 자동 실행 스케줄             │  │
        │  │  - 구글 시트 설정 (신규)        │  │
        │  └─────────────────────────────────┘  │
        └───────────────────────────────────────┘
                            │
                            ↓
        ┌──────────────────────────────────────────────────┐
        │  GoogleSheetsDialog (google_sheets_dialog.py)    │
        │  ┌────────────────────────────────────────────┐  │
        │  │  - browse_credentials_file()              │  │
        │  │  - test_connection()                      │  │
        │  │  - run_backup()                           │  │
        │  │  - show_setup_guide()                     │  │
        │  └────────────────────────────────────────────┘  │
        └──────────────────────────────────────────────────┘
                            │
                            ↓
┌─────────────────────────────────────────────────────────────┐
│   GoogleSheetsManager (google_sheets_manager.py)            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  - setup_connection(credentials_file, sheet_url)    │   │
│  │  - backup_materials(excel_manager, silent=False)    │   │
│  │  - test_connection() -> dict                        │   │
│  │  - create_sample_data() -> bool                     │   │
│  │  - is_connected: bool                               │   │
│  │  - config: GoogleSheetsConfig                       │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │
                            ↓
        ┌───────────────────────────────────────┐
        │  GoogleSheetsConfig                   │
        │  ┌─────────────────────────────────┐  │
        │  │  - credentials_file             │  │
        │  │  - spreadsheet_url              │  │
        │  │  - backup_enabled               │  │
        │  │  - auto_backup_on_save          │  │
        │  │  - backup_success_count         │  │
        │  │  - backup_failure_count         │  │
        │  └─────────────────────────────────┘  │
        └───────────────────────────────────────┘
                            │
                            ↓
        ┌───────────────────────────────────────┐
        │  ExcelManager (excel_manager.py)      │
        │  ┌─────────────────────────────────┐  │
        │  │  - google_sheets: GoogleSheets  │  │
        │  │    Manager (신규 속성)          │  │
        │  │                                 │  │
        │  │  save_material_data():          │  │
        │  │    1. Excel 저장                │  │
        │  │    2. 구글 시트 자동 백업       │  │
        │  │       (설정 시)                 │  │
        │  └─────────────────────────────────┘  │
        └───────────────────────────────────────┘
```

### 5.3 데이터 흐름
```
Portal Automation
        │
        ↓
    자재 데이터 추출
        │
        ↓
ExcelManager.save_material_data()
        │
        ├──→ Excel 파일 저장 (기존)
        │
        └──→ GoogleSheetsManager.backup_materials() (신규)
                │
                ├──→ 데이터 변환 (Dict → gspread 형식)
                │
                ├──→ 구글 시트 업데이트
                │
                └──→ 백업 통계 업데이트
```

---

## 6. 단계별 구현 계획

### Phase 1: 백엔드 구축 (2-3시간)

#### Step 1.1: GoogleSheetsManager 클래스 생성
**파일**: `src/services/google_sheets_manager.py`

```python
"""
구글 시트 백업 관리자
PythonProject3의 google_sheets_backup.py를 INTEROJO에 맞게 포팅
"""
import gspread
from google.oauth2.service_account import Credentials
from typing import Dict, List, Any, Optional
from pathlib import Path
import json
from datetime import datetime

from config.settings import settings
from utils.logger import logger


class GoogleSheetsConfig:
    """구글 시트 설정 관리"""

    def __init__(self):
        # INTEROJO 설정 파일 위치
        self.config_file = settings.base_dir / 'config' / 'google_sheets_settings.json'
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """설정 파일 로드"""
        default_config = {
            'credentials_file': '',
            'spreadsheet_url': '',
            'last_backup_time': None,
            'backup_enabled': False,
            'auto_backup_on_save': True,
            'backup_success_count': 0,
            'backup_failure_count': 0
        }

        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    default_config.update(loaded_config)
                    logger.info("구글 시트 설정 로드 완료")
        except Exception as e:
            logger.error(f"구글 시트 설정 로드 실패: {e}")

        return default_config

    def save_config(self) -> bool:
        """설정 파일 저장"""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            logger.info("구글 시트 설정 저장 완료")
            return True
        except Exception as e:
            logger.error(f"구글 시트 설정 저장 실패: {e}")
            return False

    def get_credentials_file(self) -> str:
        """인증 파일 경로 반환 (휴대용 실행파일 지원)"""
        file_path = self.config.get('credentials_file', '')

        if not file_path:
            return ''

        # 절대 경로가 존재하면 반환
        if Path(file_path).is_absolute() and Path(file_path).exists():
            return file_path

        # 상대 경로 시도
        config_dir = settings.base_dir / 'config'
        relative_path = config_dir / Path(file_path).name
        if relative_path.exists():
            logger.info(f"JSON 파일 찾음: {relative_path}")
            return str(relative_path)

        # 실행파일 경로에서 찾기
        import sys
        if getattr(sys, 'frozen', False):
            exe_config_path = Path(sys.executable).parent / 'config' / Path(file_path).name
            if exe_config_path.exists():
                logger.info(f"실행파일 경로에서 JSON 파일 찾음: {exe_config_path}")
                return str(exe_config_path)

        logger.warning(f"JSON 파일을 찾을 수 없음: {file_path}")
        return file_path

    def set_credentials_file(self, file_path: str):
        """인증 파일 경로 설정"""
        self.config['credentials_file'] = file_path
        self.save_config()

    def get_spreadsheet_url(self) -> str:
        """스프레드시트 URL 반환"""
        return self.config.get('spreadsheet_url', '')

    def set_spreadsheet_url(self, url: str):
        """스프레드시트 URL 설정"""
        self.config['spreadsheet_url'] = url
        self.save_config()

    def is_backup_enabled(self) -> bool:
        """백업 활성화 상태"""
        return self.config.get('backup_enabled', False)

    def set_backup_enabled(self, enabled: bool):
        """백업 활성화 설정"""
        self.config['backup_enabled'] = enabled
        self.save_config()

    def is_auto_backup_on_save(self) -> bool:
        """저장 시 자동 백업 상태"""
        return self.config.get('auto_backup_on_save', True)

    def set_auto_backup_on_save(self, enabled: bool):
        """저장 시 자동 백업 설정"""
        self.config['auto_backup_on_save'] = enabled
        self.save_config()

    def get_last_backup_time(self) -> Optional[str]:
        """마지막 백업 시간"""
        return self.config.get('last_backup_time')

    def set_last_backup_time(self, backup_time: Optional[str] = None):
        """마지막 백업 시간 설정"""
        if backup_time is None:
            backup_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.config['last_backup_time'] = backup_time
        self.save_config()

    def increment_backup_success(self):
        """백업 성공 횟수 증가"""
        self.config['backup_success_count'] = self.config.get('backup_success_count', 0) + 1
        self.save_config()

    def increment_backup_failure(self):
        """백업 실패 횟수 증가"""
        self.config['backup_failure_count'] = self.config.get('backup_failure_count', 0) + 1
        self.save_config()

    def get_backup_status_text(self) -> str:
        """백업 상태 텍스트"""
        if not self.is_backup_enabled():
            return "백업 미설정"

        last_backup = self.get_last_backup_time()
        if last_backup:
            success = self.config.get('backup_success_count', 0)
            failure = self.config.get('backup_failure_count', 0)
            return f"마지막: {last_backup} (성공:{success}, 실패:{failure})"
        else:
            return "백업 설정됨 (기록 없음)"

    def is_configured(self) -> bool:
        """설정 완료 여부"""
        credentials_file = self.get_credentials_file()
        return (credentials_file and
                Path(credentials_file).exists() and
                self.get_spreadsheet_url() and
                self.is_backup_enabled())


class GoogleSheetsManager:
    """구글 시트 백업 관리자"""

    def __init__(self):
        self.client = None
        self.spreadsheet = None
        self.worksheet = None
        self.is_connected = False
        self.config = GoogleSheetsConfig()

        # 설정이 완료되어 있으면 자동 연결 시도
        if self.config.is_configured():
            try:
                self.setup_connection(
                    self.config.get_credentials_file(),
                    self.config.get_spreadsheet_url()
                )
            except Exception as e:
                logger.warning(f"구글 시트 자동 연결 실패: {e}")

    def setup_connection(self, credentials_file: str, spreadsheet_url: str) -> bool:
        """구글 시트 연결 설정"""
        try:
            # Service Account 인증
            scope = ['https://www.googleapis.com/auth/spreadsheets']
            credentials = Credentials.from_service_account_file(
                credentials_file,
                scopes=scope
            )

            # gspread 클라이언트 생성
            self.client = gspread.authorize(credentials)

            # 스프레드시트 열기
            self.spreadsheet = self.client.open_by_url(spreadsheet_url)

            # 첫 번째 워크시트 선택
            self.worksheet = self.spreadsheet.sheet1

            # 연결 상태 업데이트
            self.is_connected = True

            # 설정 저장
            self.config.set_credentials_file(credentials_file)
            self.config.set_spreadsheet_url(spreadsheet_url)
            self.config.set_backup_enabled(True)

            logger.info(f"구글 시트 연결 성공: {self.spreadsheet.title}")
            return True

        except FileNotFoundError:
            logger.error(f"인증 파일을 찾을 수 없음: {credentials_file}")
            self.is_connected = False
            return False
        except Exception as e:
            logger.error(f"구글 시트 연결 실패: {e}")
            self.is_connected = False
            return False

    def backup_materials(self, excel_manager, silent: bool = False) -> bool:
        """
        자재 요청 데이터를 구글 시트에 백업

        Args:
            excel_manager: ExcelManager 인스턴스
            silent: True이면 성공/실패 시 로그만 남기고 알림 안 함

        Returns:
            bool: 백업 성공 여부
        """
        if not self.is_connected:
            logger.error("구글 시트에 연결되지 않음")
            return False

        try:
            # Excel에서 데이터 가져오기
            existing_data = excel_manager.get_existing_data()

            if not existing_data:
                logger.warning("백업할 데이터가 없음")
                if not silent:
                    self.config.increment_backup_failure()
                return False

            # 헤더 준비
            headers = excel_manager.columns

            # 데이터 준비 (Dict → List 변환)
            data_rows = []
            for record in existing_data:
                row = [record.get(col, '') for col in headers]
                data_rows.append(row)

            # 전체 데이터 (헤더 + 데이터)
            all_data = [headers] + data_rows

            # 시트 업데이트
            logger.info(f"구글 시트 백업 시작: {len(data_rows)}행")

            # 기존 데이터 클리어
            self.worksheet.clear()

            # 배치 업데이트 (한 번에)
            self.worksheet.update(range_name='A1', values=all_data)

            # 헤더 포맷팅
            self._format_header(len(headers))

            # 백업 성공 기록
            self.config.set_last_backup_time()
            self.config.increment_backup_success()

            logger.info(f"구글 시트 백업 완료: {len(data_rows)}행")
            return True

        except Exception as e:
            logger.error(f"구글 시트 백업 실패: {e}")
            if not silent:
                self.config.increment_backup_failure()
            return False

    def _format_header(self, column_count: int):
        """헤더 행 포맷팅"""
        try:
            # 헤더 범위
            header_range = f'A1:{chr(64 + column_count)}1'

            # 포맷 요청
            format_request = {
                'repeatCell': {
                    'range': {
                        'sheetId': self.worksheet.id,
                        'startRowIndex': 0,
                        'endRowIndex': 1,
                        'startColumnIndex': 0,
                        'endColumnIndex': column_count
                    },
                    'cell': {
                        'userEnteredFormat': {
                            'backgroundColor': {
                                'red': 0.2,
                                'green': 0.4,
                                'blue': 0.6
                            },
                            'textFormat': {
                                'bold': True,
                                'foregroundColor': {
                                    'red': 1,
                                    'green': 1,
                                    'blue': 1
                                }
                            },
                            'horizontalAlignment': 'CENTER'
                        }
                    },
                    'fields': 'userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)'
                }
            }

            # 배치 업데이트 실행
            self.spreadsheet.batch_update({'requests': [format_request]})
            logger.debug("헤더 포맷팅 완료")

        except Exception as e:
            logger.warning(f"헤더 포맷팅 실패: {e}")

    def test_connection(self) -> Dict[str, Any]:
        """연결 테스트"""
        if not self.is_connected:
            return {
                'success': False,
                'message': '연결되지 않음'
            }

        try:
            spreadsheet_name = self.spreadsheet.title
            worksheet_name = self.worksheet.title

            return {
                'success': True,
                'spreadsheet_name': spreadsheet_name,
                'worksheet_name': worksheet_name,
                'message': '연결 성공'
            }
        except Exception as e:
            self.is_connected = False
            return {
                'success': False,
                'message': str(e)
            }

    def create_sample_data(self) -> bool:
        """샘플 데이터 생성 (테스트용)"""
        if not self.is_connected:
            logger.error("구글 시트에 연결되지 않음")
            return False

        try:
            # INTEROJO 자재 요청 샘플 데이터
            headers = ["순번", "자재코드", "품명", "요청수량(g단위)",
                      "사유", "요청부서", "기안자", "문서번호", "처리일시"]

            sample_data = [
                ["1", "MAT001", "볼트 M8x20", "500", "생산용", "제조부", "홍길동",
                 "DOC20251201001", "2025-12-01 10:00:00"],
                ["2", "MAT002", "너트 M8", "500", "생산용", "제조부", "홍길동",
                 "DOC20251201001", "2025-12-01 10:00:00"],
                ["3", "MAT003", "와셔 8mm", "1000", "재고 보충", "자재부", "김철수",
                 "DOC20251201002", "2025-12-01 11:30:00"]
            ]

            all_data = [headers] + sample_data

            # 시트 클리어 및 업데이트
            self.worksheet.clear()
            self.worksheet.update(range_name='A1', values=all_data)

            # 헤더 포맷팅
            self._format_header(len(headers))

            logger.info("샘플 데이터 생성 완료")
            return True

        except Exception as e:
            logger.error(f"샘플 데이터 생성 실패: {e}")
            return False


def create_credentials_guide() -> str:
    """구글 API 설정 가이드 텍스트 반환"""
    return """
# 구글 시트 API 설정 가이드

## 1단계: Google Cloud Console 프로젝트 생성

1. https://console.cloud.google.com/ 접속
2. 새 프로젝트 생성 또는 기존 프로젝트 선택
3. 프로젝트 이름: "INTEROJO 자동화" (예시)

## 2단계: Google Sheets API 활성화

1. 왼쪽 메뉴에서 "API 및 서비스" > "라이브러리" 선택
2. "Google Sheets API" 검색
3. "사용" 버튼 클릭

## 3단계: Service Account 생성

1. "API 및 서비스" > "사용자 인증 정보" 선택
2. "사용자 인증 정보 만들기" > "서비스 계정" 선택
3. 서비스 계정 이름 입력 (예: interojo-sheets-backup)
4. "만들기 및 계속하기" 클릭
5. 역할: "편집자" 선택
6. "완료" 클릭

## 4단계: JSON 키 파일 다운로드

1. 생성된 서비스 계정 클릭
2. "키" 탭 선택
3. "키 추가" > "새 키 만들기" 선택
4. 키 유형: JSON 선택
5. "만들기" 클릭 (자동으로 JSON 파일 다운로드됨)

## 5단계: 구글 시트 생성 및 공유

1. https://sheets.google.com/ 에서 새 스프레드시트 생성
2. 스프레드시트 이름: "INTEROJO 자재요청 백업" (예시)
3. 오른쪽 상단 "공유" 버튼 클릭
4. JSON 파일에서 "client_email" 값 복사
   (예: interojo-sheets-backup@project-id.iam.gserviceaccount.com)
5. 해당 이메일을 "편집자" 권한으로 추가
6. 스프레드시트 URL 복사 (예: https://docs.google.com/spreadsheets/d/...)

## 6단계: INTEROJO에 설정

1. 다운로드한 JSON 파일을 프로젝트 config 폴더에 복사
   예: C:\\X\\PythonProject\\PythonProject5-pdf\\config\\google_sheets_credentials.json
2. INTEROJO 설정 다이얼로그에서:
   - JSON 인증 파일: 위 경로 선택
   - 구글 시트 URL: 5단계에서 복사한 URL 입력
3. "연결 테스트" 버튼으로 확인

## 주의사항

- JSON 키 파일은 절대로 공유하거나 Git에 커밋하지 마세요
- 서비스 계정 이메일은 반드시 스프레드시트에 공유되어야 합니다
- 스프레드시트는 "링크가 있는 모든 사용자"로 공유하지 마세요
"""
```

#### Step 1.2: `__init__.py` 생성
**파일**: `src/services/__init__.py`

```python
"""
서비스 모듈
백업, 알림 등의 서비스 기능 제공
"""
from .google_sheets_manager import GoogleSheetsManager, GoogleSheetsConfig, create_credentials_guide

__all__ = ['GoogleSheetsManager', 'GoogleSheetsConfig', 'create_credentials_guide']
```

---

### Phase 2: ExcelManager 통합 (1시간)

#### Step 2.1: ExcelManager에 구글 시트 통합
**파일**: `src/core/excel_manager.py`

**변경 위치 1: import 추가**
```python
# excel_manager.py 상단에 추가
from services.google_sheets_manager import GoogleSheetsManager
```

**변경 위치 2: __init__ 메서드 수정**
```python
# excel_manager.py:25-43
def __init__(self, file_path: Optional[str] = None):
    self.file_path = Path(file_path) if file_path else settings.excel_file_path
    self.workbook = None
    self.worksheet = None
    self.current_row = 1

    self.columns = settings.get("excel.columns", [
        "순번", "자재코드", "품명", "요청수량(g단위)",
        "사유", "요청부서", "기안자", "문서번호", "처리일시"
    ])

    self.processed_documents = set()
    self.last_save_time = None
    self.auto_save_interval = 300

    # 구글 시트 매니저 초기화 (신규)
    try:
        self.google_sheets = GoogleSheetsManager()
        if self.google_sheets.is_connected:
            logger.info("구글 시트 백업 기능 활성화됨")
    except Exception as e:
        logger.warning(f"구글 시트 초기화 실패 (Excel만 사용): {e}")
        self.google_sheets = None

    self._initialize_workbook()
    self._load_processed_documents()
```

**변경 위치 3: save_material_data 메서드 수정**
```python
# excel_manager.py:483-552 수정
def save_material_data(self, table_rows, drafter, document_number, department):
    """자재 데이터 저장 (기존 portal_automation.py 호환용)"""
    try:
        logger.info(f"자재 데이터 저장 시작: 문서번호 {document_number}, {len(table_rows)}행")

        # 중복 문서 확인
        if document_number in self.processed_documents:
            logger.debug(f"이미 처리된 문서 무시: {document_number}")
            return

        # 각 자재 행을 Excel에 추가
        for row_data in table_rows:
            # ... (기존 로직 동일)
            self.add_row(material_data)

        # 처리된 문서로 표시
        self.processed_documents.add(document_number)

        # Excel 즉시 저장
        self.save(backup=False)

        # 구글 시트 자동 백업 (신규)
        if self.google_sheets and self.google_sheets.is_connected:
            if self.google_sheets.config.is_auto_backup_on_save():
                try:
                    logger.info("구글 시트 자동 백업 시작...")
                    success = self.google_sheets.backup_materials(self, silent=True)
                    if success:
                        logger.info("구글 시트 자동 백업 완료")
                    else:
                        logger.warning("구글 시트 자동 백업 실패")
                except Exception as e:
                    logger.error(f"구글 시트 자동 백업 오류: {e}")

        logger.info(f"자재 데이터 저장 완료: 문서번호 {document_number}")

    except Exception as e:
        logger.error(f"자재 데이터 저장 실패: {e}")
        raise
```

**변경 위치 4: 수동 백업 메서드 추가**
```python
# excel_manager.py 끝에 추가
def backup_to_google_sheets(self, silent: bool = False) -> bool:
    """
    수동으로 구글 시트에 백업

    Args:
        silent: True이면 알림 없이 로그만

    Returns:
        bool: 백업 성공 여부
    """
    if not self.google_sheets or not self.google_sheets.is_connected:
        logger.warning("구글 시트에 연결되지 않음")
        return False

    try:
        logger.info("수동 구글 시트 백업 시작...")
        success = self.google_sheets.backup_materials(self, silent=silent)

        if success:
            logger.info("수동 구글 시트 백업 완료")
        else:
            logger.error("수동 구글 시트 백업 실패")

        return success

    except Exception as e:
        logger.error(f"수동 구글 시트 백업 오류: {e}")
        return False
```

---

### Phase 3: GUI 구현 (2-3시간)

#### Step 3.1: 구글 시트 설정 다이얼로그 (tkinter)
**파일**: `src/gui/google_sheets_dialog.py`

```python
"""
구글 시트 백업 설정 다이얼로그 (tkinter)
PythonProject3의 PyQt5 UI를 tkinter로 재작성
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
from pathlib import Path
import sys

# 프로젝트 루트 경로 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from services.google_sheets_manager import GoogleSheetsManager, create_credentials_guide
from utils.logger import logger


class GoogleSheetsDialog:
    """구글 시트 설정 다이얼로그"""

    def __init__(self, parent, excel_manager=None):
        """
        Args:
            parent: 부모 윈도우
            excel_manager: ExcelManager 인스턴스 (백업 실행용)
        """
        self.parent = parent
        self.excel_manager = excel_manager
        self.result = False

        # 구글 시트 매니저
        if excel_manager and hasattr(excel_manager, 'google_sheets'):
            self.backup_manager = excel_manager.google_sheets
        else:
            self.backup_manager = GoogleSheetsManager()

        # 다이얼로그 생성
        self.create_dialog()

    def create_dialog(self):
        """다이얼로그 창 생성"""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("구글 시트 백업 설정")
        self.dialog.geometry("600x550")
        self.dialog.resizable(False, False)
        self.dialog.transient(self.parent)
        self.dialog.grab_set()

        # 중앙 정렬
        self.dialog.geometry(f"+{self.parent.winfo_rootx()+50}+{self.parent.winfo_rooty()+50}\"")

        self.create_widgets()

        # 현재 설정 로드
        self.load_current_settings()

        # 모달 대화상자
        self.dialog.wait_window()

    def create_widgets(self):
        """위젯 생성"""
        main_frame = ttk.Frame(self.dialog, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 제목
        title_label = ttk.Label(main_frame, text="📊 구글 시트 백업 설정",
                               font=("Arial", 14, "bold"))
        title_label.pack(pady=(0, 10))

        # 연결 설정 섹션
        setup_frame = ttk.LabelFrame(main_frame, text="연결 설정", padding="10")
        setup_frame.pack(fill=tk.X, pady=(0, 10))

        # JSON 인증 파일
        ttk.Label(setup_frame, text="JSON 인증 파일:").grid(row=0, column=0, sticky=tk.W, padx=(0, 10))

        cred_frame = ttk.Frame(setup_frame)
        cred_frame.grid(row=0, column=1, sticky=(tk.W, tk.E))

        self.credentials_entry = ttk.Entry(cred_frame, width=35)
        self.credentials_entry.grid(row=0, column=0, sticky=(tk.W, tk.E))

        ttk.Button(cred_frame, text="찾아보기", command=self.browse_credentials).grid(row=0, column=1, padx=(5, 0))

        cred_frame.columnconfigure(0, weight=1)

        # 구글 시트 URL
        ttk.Label(setup_frame, text="구글 시트 URL:").grid(row=1, column=0, sticky=tk.W, padx=(0, 10), pady=(10, 0))
        self.url_entry = ttk.Entry(setup_frame, width=50)
        self.url_entry.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=(10, 0))

        setup_frame.columnconfigure(1, weight=1)

        # 연결 테스트 버튼
        test_btn_frame = ttk.Frame(setup_frame)
        test_btn_frame.grid(row=2, column=0, columnspan=2, pady=(10, 0))

        self.test_btn = ttk.Button(test_btn_frame, text="🔍 연결 테스트", command=self.test_connection)
        self.test_btn.pack()

        # 연결 상태 표시
        self.status_label = ttk.Label(setup_frame, text="연결 상태: 미연결", foreground="red")
        self.status_label.grid(row=3, column=0, columnspan=2, pady=(5, 0))

        # 백업 실행 섹션
        backup_frame = ttk.LabelFrame(main_frame, text="백업 실행", padding="10")
        backup_frame.pack(fill=tk.X, pady=(0, 10))

        info_label = ttk.Label(backup_frame, text="💡 현재 Excel 파일의 모든 자재 요청 데이터를 구글 시트에 백업합니다.",
                              foreground="gray")
        info_label.pack(pady=(0, 10))

        # 백업 버튼
        btn_frame = ttk.Frame(backup_frame)
        btn_frame.pack()

        self.backup_btn = ttk.Button(btn_frame, text="📤 전체 백업 실행",
                                     command=self.run_backup, state='disabled')
        self.backup_btn.grid(row=0, column=0, padx=5)

        self.sample_btn = ttk.Button(btn_frame, text="📝 샘플 데이터 테스트",
                                     command=self.create_sample_data)
        self.sample_btn.grid(row=0, column=1, padx=5)

        # 가이드 섹션
        guide_frame = ttk.LabelFrame(main_frame, text="설정 가이드", padding="10")
        guide_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(guide_frame, text="📖 구글 API 설정 가이드 보기",
                  command=self.show_setup_guide).pack()

        # 하단 버튼
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X, pady=(10, 0))

        ttk.Button(bottom_frame, text="닫기", command=self.close).pack(side=tk.RIGHT)

    def load_current_settings(self):
        """현재 설정값 로드"""
        try:
            credentials_file = self.backup_manager.config.get_credentials_file()
            spreadsheet_url = self.backup_manager.config.get_spreadsheet_url()

            if credentials_file:
                self.credentials_entry.insert(0, credentials_file)
            if spreadsheet_url:
                self.url_entry.insert(0, spreadsheet_url)

            # 연결 상태 확인
            if self.backup_manager.is_connected:
                test_result = self.backup_manager.test_connection()
                if test_result['success']:
                    self.status_label.config(
                        text=f"✅ 연결됨: {test_result['spreadsheet_name']}",
                        foreground="green"
                    )
                    self.backup_btn.config(state='normal')
                else:
                    self.status_label.config(
                        text=f"❌ 연결 실패: {test_result['message']}",
                        foreground="red"
                    )

        except Exception as e:
            logger.error(f"설정 로드 오류: {e}")

    def browse_credentials(self):
        """JSON 인증 파일 선택"""
        file_path = filedialog.askopenfilename(
            title="JSON 인증 파일 선택",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )

        if file_path:
            self.credentials_entry.delete(0, tk.END)
            self.credentials_entry.insert(0, file_path)

    def test_connection(self):
        """연결 테스트"""
        credentials_file = self.credentials_entry.get().strip()
        sheet_url = self.url_entry.get().strip()

        if not credentials_file or not sheet_url:
            messagebox.showwarning("입력 오류", "JSON 파일과 구글 시트 URL을 모두 입력해주세요.")
            return

        # 연결 시도
        self.status_label.config(text="연결 중...", foreground="orange")
        self.dialog.update()

        success = self.backup_manager.setup_connection(credentials_file, sheet_url)

        if success:
            test_result = self.backup_manager.test_connection()
            if test_result['success']:
                self.status_label.config(
                    text=f"✅ 연결 성공: {test_result['spreadsheet_name']}",
                    foreground="green"
                )
                self.backup_btn.config(state='normal')

                messagebox.showinfo(
                    "연결 성공",
                    f"구글 시트 연결에 성공했습니다!\n\n"
                    f"스프레드시트: {test_result['spreadsheet_name']}\n"
                    f"워크시트: {test_result['worksheet_name']}"
                )
            else:
                self.status_label.config(
                    text=f"❌ 연결 실패: {test_result['message']}",
                    foreground="red"
                )
        else:
            self.status_label.config(text="❌ 연결 실패", foreground="red")
            messagebox.showerror("연결 실패", "구글 시트 연결에 실패했습니다.\n설정을 확인해주세요.")

    def run_backup(self):
        """백업 실행"""
        if not self.backup_manager.is_connected:
            messagebox.showwarning("연결 오류", "먼저 구글 시트에 연결해주세요.")
            return

        if not self.excel_manager:
            messagebox.showerror("오류", "Excel 매니저가 초기화되지 않았습니다.")
            return

        # 확인 메시지
        reply = messagebox.askyesno(
            "백업 확인",
            "모든 자재 요청 데이터를 구글 시트에 백업하시겠습니까?\n\n"
            "기존 시트의 데이터는 모두 삭제되고 새로운 데이터로 대체됩니다."
        )

        if not reply:
            return

        # 백업 실행
        try:
            self.backup_btn.config(state='disabled', text="백업 중...")
            self.dialog.update()

            success = self.backup_manager.backup_materials(self.excel_manager)

            if success:
                messagebox.showinfo(
                    "백업 완료",
                    "자재 요청 데이터가 구글 시트에 성공적으로 백업되었습니다!"
                )
            else:
                messagebox.showerror(
                    "백업 실패",
                    "백업 중 오류가 발생했습니다.\n로그를 확인해주세요."
                )

        except Exception as e:
            messagebox.showerror("백업 오류", f"백업 중 오류가 발생했습니다:\n{str(e)}")
            logger.error(f"백업 오류: {e}")

        finally:
            self.backup_btn.config(state='normal', text="📤 전체 백업 실행")

    def create_sample_data(self):
        """샘플 데이터 생성"""
        if not self.backup_manager.is_connected:
            messagebox.showwarning("연결 오류", "먼저 구글 시트에 연결해주세요.")
            return

        success = self.backup_manager.create_sample_data()

        if success:
            messagebox.showinfo(
                "샘플 데이터 생성",
                "샘플 데이터가 구글 시트에 생성되었습니다!\n연결 테스트가 완료되었습니다."
            )
        else:
            messagebox.showerror(
                "샘플 데이터 실패",
                "샘플 데이터 생성에 실패했습니다."
            )

    def show_setup_guide(self):
        """설정 가이드 표시"""
        guide_window = tk.Toplevel(self.dialog)
        guide_window.title("구글 API 설정 가이드")
        guide_window.geometry("700x600")

        # 가이드 텍스트
        text_area = scrolledtext.ScrolledText(guide_window, wrap=tk.WORD,
                                              font=("Consolas", 10))
        text_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        text_area.insert(tk.END, create_credentials_guide())
        text_area.config(state='disabled')

        # 닫기 버튼
        ttk.Button(guide_window, text="닫기", command=guide_window.destroy).pack(pady=10)

    def close(self):
        """다이얼로그 닫기"""
        self.dialog.destroy()


if __name__ == "__main__":
    # 테스트용
    root = tk.Tk()
    root.withdraw()
    dialog = GoogleSheetsDialog(root)
    root.destroy()
```

#### Step 3.2: 메인 윈도우에 버튼 추가
**파일**: `src/gui/main_window.py`

**변경 위치 1: import 추가**
```python
# main_window.py 상단에 추가
from gui.google_sheets_dialog import GoogleSheetsDialog
```

**변경 위치 2: 관리 버튼 프레임에 버튼 추가**
```python
# main_window.py:88-93 수정
manage_frame = ttk.Frame(main_frame)
manage_frame.grid(row=3, column=0, columnspan=2, pady=5)

ttk.Button(manage_frame, text="설정", command=self.open_settings, width=12).grid(row=0, column=0, padx=5)
ttk.Button(manage_frame, text="구글 시트", command=self.open_google_sheets, width=12).grid(row=0, column=1, padx=5)  # 신규
ttk.Button(manage_frame, text="로그 보기", command=self.show_logs, width=12).grid(row=0, column=2, padx=5)
ttk.Button(manage_frame, text="Excel 열기", command=self.open_excel, width=12).grid(row=0, column=3, padx=5)
```

**변경 위치 3: open_google_sheets 메서드 추가**
```python
# main_window.py 끝에 추가
def open_google_sheets(self):
    """구글 시트 설정 창 열기"""
    try:
        # ExcelManager 인스턴스 가져오기
        if hasattr(self, 'automation') and self.automation:
            excel_manager = self.automation.excel_manager
        else:
            # 자동화가 실행되지 않았으면 임시 ExcelManager 생성
            from core.excel_manager import ExcelManager
            excel_manager = ExcelManager()

        dialog = GoogleSheetsDialog(self.root, excel_manager)

    except Exception as e:
        messagebox.showerror("오류", f"구글 시트 설정을 열 수 없습니다:\n{e}")
        logger.error(f"구글 시트 다이얼로그 오류: {e}")
```

#### Step 3.3: settings_dialog.py에 구글 시트 섹션 추가 (선택사항)
**파일**: `src/gui/settings_dialog.py`

settings_dialog.py는 로그인 정보와 자동 실행 스케줄을 관리하므로, 구글 시트 설정은 별도 다이얼로그로 분리하는 것이 깔끔합니다. 따라서 이 파일은 수정하지 않아도 됩니다.

만약 통합하고 싶다면:
```python
# settings_dialog.py:186 뒤에 추가
# 구글 시트 백업 섹션
google_sheets_frame = ttk.LabelFrame(main_frame, text="구글 시트 백업", padding="10")
google_sheets_frame.pack(fill=tk.X, pady=(0, 10))

ttk.Button(google_sheets_frame, text="구글 시트 설정 열기",
          command=self.open_google_sheets_dialog).pack()

# 백업 상태 표시
if hasattr(self.parent, 'automation') and self.parent.automation:
    excel_manager = self.parent.automation.excel_manager
    if excel_manager and excel_manager.google_sheets:
        status_text = excel_manager.google_sheets.config.get_backup_status_text()
        ttk.Label(google_sheets_frame, text=status_text, foreground="gray").pack(pady=(5, 0))
```

---

### Phase 4: 설정 및 의존성 (30분)

#### Step 4.1: .env 파일에 환경변수 추가
**파일**: `.env`

```env
# .env 파일에 추가
# 구글 시트 백업 설정
GOOGLE_SHEETS_ENABLED=false
GOOGLE_SHEETS_CREDENTIALS=config/google_sheets_credentials.json
GOOGLE_SHEETS_URL=
GOOGLE_SHEETS_AUTO_BACKUP=true
```

#### Step 4.2: settings.py에 구글 시트 설정 추가
**파일**: `src/config/settings.py`

```python
# settings.py 끝에 추가
@property
def google_sheets_enabled(self) -> bool:
    """구글 시트 백업 활성화 여부"""
    return os.getenv('GOOGLE_SHEETS_ENABLED', 'False').lower() == 'true'

@property
def google_sheets_credentials(self) -> str:
    """구글 시트 인증 파일 경로"""
    cred_path = os.getenv('GOOGLE_SHEETS_CREDENTIALS', '')
    if cred_path:
        return str(self.base_dir / cred_path)
    return ''

@property
def google_sheets_url(self) -> str:
    """구글 시트 URL"""
    return os.getenv('GOOGLE_SHEETS_URL', '')

@property
def google_sheets_auto_backup(self) -> bool:
    """저장 시 자동 백업 여부"""
    return os.getenv('GOOGLE_SHEETS_AUTO_BACKUP', 'True').lower() == 'true'
```

#### Step 4.3: requirements.txt 업데이트
**파일**: `requirements.txt`

```txt
# 기존 의존성
python-dotenv==1.0.0
selenium==4.15.2
openpyxl==3.1.2
webdriver-manager==4.0.1
schedule==1.2.0
psutil==5.9.6
Pillow==10.1.0
python-dateutil==2.8.2

# 구글 시트 백업 추가
gspread==6.2.1
google-auth==2.25.2
google-auth-oauthlib==1.2.0
google-auth-httplib2==0.2.0
```

#### Step 4.4: automation.spec 업데이트
**파일**: `automation.spec`

```python
# automation.spec:48-106 hiddenimports에 추가
hiddenimports=[
    # ... (기존 모듈들)

    # 구글 시트 백업 (신규)
    'gspread',
    'gspread.auth',
    'gspread.spreadsheet',
    'gspread.worksheet',
    'google.auth',
    'google.auth.transport',
    'google.auth.transport.requests',
    'google.oauth2',
    'google.oauth2.service_account',
],
```

#### Step 4.5: .gitignore 업데이트
**파일**: `.gitignore`

```gitignore
# .gitignore에 추가
# 구글 시트 인증 파일 (보안)
config/google_sheets_credentials.json
config/*_credentials.json
config/google_sheets_settings.json
```

---

## 7. 파일별 상세 변경 사항

### 7.1 신규 생성 파일

| 파일 경로 | 라인 수 | 설명 |
|----------|--------|------|
| `src/services/__init__.py` | 10 | 서비스 모듈 초기화 |
| `src/services/google_sheets_manager.py` | 500+ | 구글 시트 백업 로직 (PythonProject3 포팅) |
| `src/gui/google_sheets_dialog.py` | 350+ | tkinter 설정 다이얼로그 (PyQt5 재작성) |
| `config/google_sheets_settings.json` | 자동 생성 | 구글 시트 설정 저장 |
| `config/google_sheets_credentials.json` | 사용자 제공 | Service Account JSON |
| `docs/google_sheets_integration_plan.md` | 본 문서 | 통합 계획서 |

### 7.2 수정 파일

| 파일 경로 | 변경 사항 | 변경 라인 수 |
|----------|----------|-------------|
| `src/core/excel_manager.py` | 구글 시트 통합 | +40줄 |
| `src/gui/main_window.py` | 구글 시트 버튼 추가 | +20줄 |
| `src/config/settings.py` | 구글 시트 환경변수 추가 | +20줄 |
| `.env` | 구글 시트 설정 추가 | +4줄 |
| `.gitignore` | 인증 파일 제외 | +3줄 |
| `requirements.txt` | gspread 의존성 추가 | +4줄 |
| `automation.spec` | 구글 모듈 hiddenimports | +10줄 |

---

## 8. 데이터 구조 매핑

### 8.1 Excel → 구글 시트 매핑

#### Excel 컬럼 (ExcelManager)
```python
columns = [
    "순번",              # A열
    "자재코드",          # B열
    "품명",             # C열
    "요청수량(g단위)",   # D열
    "사유",             # E열
    "요청부서",          # F열
    "기안자",           # G열
    "문서번호",          # H열
    "처리일시"          # I열
]
```

#### 구글 시트 레이아웃
```
┌─────┬──────────┬────────┬──────────────┬──────┬──────────┬────────┬────────────┬─────────────────┐
│  A  │    B     │   C    │      D       │  E   │    F     │   G    │     H      │       I         │
├─────┼──────────┼────────┼──────────────┼──────┼──────────┼────────┼────────────┼─────────────────┤
│순번 │ 자재코드 │  품명  │요청수량(g단위)│ 사유 │ 요청부서 │ 기안자 │  문서번호  │   처리일시      │
├─────┼──────────┼────────┼──────────────┼──────┼──────────┼────────┼────────────┼─────────────────┤
│  1  │ MAT001   │ 볼트   │     500      │ 생산 │  제조부  │ 홍길동 │ DOC2025... │ 2025-12-01 ...  │
│  2  │ MAT002   │ 너트   │     500      │ 생산 │  제조부  │ 홍길동 │ DOC2025... │ 2025-12-01 ...  │
└─────┴──────────┴────────┴──────────────┴──────┴──────────┴────────┴────────────┴─────────────────┘
```

### 8.2 데이터 변환 로직

```python
# ExcelManager.get_existing_data() 반환 형식
[
    {
        '순번': '1',
        '자재코드': 'MAT001',
        '품명': '볼트 M8x20',
        '요청수량(g단위)': '500',
        '사유': '생산용',
        '요청부서': '제조부',
        '기안자': '홍길동',
        '문서번호': 'DOC20251201001',
        '처리일시': '2025-12-01 10:00:00'
    },
    # ...
]

# GoogleSheetsManager.backup_materials()에서 변환
headers = ["순번", "자재코드", "품명", ...]  # List[str]

data_rows = [
    ['1', 'MAT001', '볼트 M8x20', '500', '생산용', '제조부', '홍길동', 'DOC20251201001', '2025-12-01 10:00:00'],
    ['2', 'MAT002', '너트 M8', '500', '생산용', '제조부', '홍길동', 'DOC20251201001', '2025-12-01 10:00:00'],
    # ...
]  # List[List[str]]

all_data = [headers] + data_rows  # gspread.update() 형식
```

---

## 9. 의존성 및 환경 설정

### 9.1 Python 패키지

#### 새로 추가되는 패키지
```bash
pip install gspread==6.2.1
pip install google-auth==2.25.2
pip install google-auth-oauthlib==1.2.0
pip install google-auth-httplib2==0.2.0
```

#### 의존성 트리
```
gspread 6.2.1
├── google-auth >= 1.12.0
├── google-auth-oauthlib >= 0.4.1
└── requests >= 2.2.1

google-auth 2.25.2
├── cachetools >= 2.0.0, < 6.0
├── pyasn1-modules >= 0.2.1
├── rsa >= 3.1.4, < 5
└── urllib3 < 2.0

google-auth-oauthlib 1.2.0
├── google-auth >= 2.15.0
└── requests-oauthlib >= 0.7.0

google-auth-httplib2 0.2.0
├── google-auth
└── httplib2 >= 0.19.0
```

### 9.2 구글 API 설정

#### Service Account 생성 단계
1. Google Cloud Console 프로젝트 생성
2. Google Sheets API 활성화
3. Service Account 생성 (역할: 편집자)
4. JSON 키 다운로드
5. 구글 시트에 Service Account 이메일 공유

#### 필요한 OAuth Scope
```python
scope = ['https://www.googleapis.com/auth/spreadsheets']
```

### 9.3 PyInstaller 번들링

#### spec 파일 설정
```python
# automation.spec
datas=[
    ('.env', '.'),
    ('chromedriver.exe', '.'),
    ('config/google_sheets_credentials.json', 'config'),  # 신규
    ('data/excel', 'data/excel'),
    # ...
],

hiddenimports=[
    # 구글 관련 모듈
    'gspread',
    'gspread.auth',
    'google.auth',
    'google.auth.transport.requests',
    'google.oauth2.service_account',
    # ...
],
```

#### 번들 크기 예상
- 기존 빌드: ~22 MB
- 구글 라이브러리 추가 후: **~28 MB** (약 6MB 증가)

---

## 10. 테스트 계획

### 10.1 단위 테스트

#### Test 1: GoogleSheetsConfig
```python
# 테스트 항목:
- JSON 설정 파일 로드/저장
- 인증 파일 경로 찾기 (절대/상대 경로)
- 백업 통계 증가
- 설정 완료 여부 확인
```

#### Test 2: GoogleSheetsManager
```python
# 테스트 항목:
- Service Account 인증
- 스프레드시트 연결
- 샘플 데이터 생성
- 연결 테스트
```

#### Test 3: ExcelManager 통합
```python
# 테스트 항목:
- 구글 시트 매니저 초기화
- save_material_data 후 자동 백업
- backup_to_google_sheets 수동 백업
- 백업 실패 시 Excel은 정상 저장
```

### 10.2 통합 테스트

#### Scenario 1: 신규 설치 사용자
```
1. INTEROJO 첫 실행
2. "구글 시트" 버튼 클릭
3. "설정 가이드" 읽고 Service Account 생성
4. JSON 파일 업로드 및 URL 입력
5. "연결 테스트" 성공 확인
6. "샘플 데이터 테스트" 실행
7. 구글 시트에서 샘플 데이터 확인
8. 설정 저장
```

#### Scenario 2: 기존 Excel 데이터 백업
```
1. INTEROJO에 기존 Excel 파일 존재 (100행)
2. "구글 시트" 설정 완료
3. "전체 백업 실행" 클릭
4. 구글 시트에 100행 데이터 확인
5. 헤더 포맷팅 확인 (파란색 배경, 흰색 글씨)
```

#### Scenario 3: 자동화 실행 + 자동 백업
```
1. 자동 백업 옵션 활성화
2. "지금 실행하기" 클릭
3. 포털에서 자재 데이터 수집 (5건)
4. Excel 저장 후 자동으로 구글 시트 백업
5. 구글 시트에 5건 추가 확인
6. 백업 통계 업데이트 확인
```

#### Scenario 4: 오프라인 동작
```
1. 인터넷 연결 없음
2. 자동화 실행
3. Excel은 정상 저장
4. 구글 시트 백업은 실패 (로그 기록)
5. 백업 실패 횟수 증가
6. 프로그램은 정상 종료
```

#### Scenario 5: 실행파일 (PyInstaller)
```
1. build.py 또는 PyInstaller로 빌드
2. dist/interojo_automation/ 폴더에서 실행
3. config 폴더에 JSON 파일 복사
4. 구글 시트 설정 및 연결 테스트
5. 자동화 실행 및 백업 확인
```

### 10.3 에러 핸들링 테스트

#### Error 1: 잘못된 JSON 파일
```
- 입력: 일반 JSON 파일 (Service Account 아님)
- 예상: "인증 실패" 오류 메시지
- 동작: Excel 저장은 정상, 구글 시트 연결 실패
```

#### Error 2: 잘못된 스프레드시트 URL
```
- 입력: 존재하지 않는 URL
- 예상: "스프레드시트를 찾을 수 없음" 오류
- 동작: 연결 실패, 백업 비활성화
```

#### Error 3: Service Account 권한 없음
```
- 입력: 스프레드시트에 공유되지 않은 Service Account
- 예상: "권한 거부" 오류
- 동작: 가이드에 공유 방법 안내
```

#### Error 4: 네트워크 오류
```
- 상황: 백업 중 인터넷 연결 끊김
- 예상: "네트워크 오류" 로그 기록
- 동작: Excel 저장 완료, 백업 실패 통계 증가
```

---

## 11. 예상 문제점 및 해결 방안

### 11.1 기술적 문제

#### 문제 1: 대용량 데이터 백업 지연
**상황**: Excel 파일에 10,000행 이상의 데이터가 있을 때 백업 시간이 오래 걸림

**원인**: gspread API는 배치 업데이트에도 시간이 소요됨 (네트워크 I/O)

**해결 방안**:
```python
# 백업 전 데이터 크기 확인 및 경고
def backup_materials(self, excel_manager, silent: bool = False) -> bool:
    existing_data = excel_manager.get_existing_data()

    # 5000행 이상이면 경고
    if len(existing_data) > 5000:
        logger.warning(f"대용량 데이터 백업 ({len(existing_data)}행): 시간이 소요될 수 있습니다")
        if not silent:
            # UI에 진행률 표시 (ttk.Progressbar)
            pass

    # 백업 실행...
```

#### 문제 2: API Rate Limit
**상황**: 짧은 시간에 여러 번 백업 시 구글 API Rate Limit 초과

**원인**: Google Sheets API는 분당 100 requests 제한

**해결 방안**:
```python
# 백업 간격 제한
class GoogleSheetsManager:
    def __init__(self):
        self.last_backup_time = None
        self.min_backup_interval = 60  # 최소 60초 간격

    def backup_materials(self, excel_manager, silent: bool = False) -> bool:
        # 백업 간격 확인
        if self.last_backup_time:
            elapsed = (datetime.now() - self.last_backup_time).total_seconds()
            if elapsed < self.min_backup_interval:
                logger.info(f"백업 간격 제한: {self.min_backup_interval - elapsed:.0f}초 후 재시도")
                return False

        # 백업 실행...
        self.last_backup_time = datetime.now()
```

#### 문제 3: PyInstaller 경로 문제
**상황**: 실행파일에서 JSON 파일을 찾지 못함

**원인**: 상대 경로 처리 오류

**해결 방안**:
```python
# GoogleSheetsConfig.get_credentials_file()에서 이미 구현됨
# 추가로 spec 파일에서 명시적으로 포함
datas=[
    ('config/google_sheets_credentials.json', 'config'),  # 사용자가 직접 복사해야 함
],
```

### 11.2 사용자 경험 문제

#### 문제 4: 설정이 복잡함
**상황**: 사용자가 구글 API 설정 방법을 모름

**해결 방안**:
1. 상세한 가이드 제공 (`create_credentials_guide()`)
2. UI에 단계별 안내 표시
3. 스크린샷 포함 PDF 가이드 제공 (별도 문서)
4. 설정 대행 서비스 제공 (IT 담당자)

#### 문제 5: 백업 실패를 인지하지 못함
**상황**: 자동 백업 실패 시 사용자가 알 수 없음

**해결 방안**:
```python
# 메인 윈도우에 백업 상태 표시
class AutomationGUI:
    def __init__(self):
        # ...
        self.backup_status_label = ttk.Label(status_frame, text="구글 시트: 미설정")
        self.backup_status_label.grid(row=3, column=0, sticky=tk.W)

    def update_status(self):
        # ...
        # 구글 시트 백업 상태 업데이트
        if self.automation and self.automation.excel_manager:
            gs = self.automation.excel_manager.google_sheets
            if gs and gs.is_connected:
                status_text = gs.config.get_backup_status_text()
                self.backup_status_label.config(text=f"구글 시트: {status_text}")
            else:
                self.backup_status_label.config(text="구글 시트: 미설정")
```

### 11.3 보안 문제

#### 문제 6: JSON 인증 파일 유출
**상황**: Service Account JSON 파일이 공개 저장소에 업로드됨

**해결 방안**:
1. `.gitignore`에 명시적으로 추가
2. 파일명 패턴 제외 (`*_credentials.json`)
3. 빌드 시 경고 메시지
4. README에 보안 주의사항 명시

```python
# build.py에 추가
def check_sensitive_files():
    """민감한 파일 확인"""
    sensitive_patterns = [
        '*_credentials.json',
        '*_key.json',
        '*.pem'
    ]

    found_files = []
    for pattern in sensitive_patterns:
        found_files.extend(PROJECT_ROOT.rglob(pattern))

    if found_files:
        print_warning(f"민감한 파일 발견: {len(found_files)}개")
        for file in found_files:
            print(f"  - {file}")
        print("\n빌드에 포함하지 않도록 주의하세요!")
```

---

## 12. 배포 및 사용자 가이드

### 12.1 배포 체크리스트

#### Phase 1: 개발 완료
- [ ] 모든 코드 작성 완료
- [ ] 단위 테스트 통과
- [ ] 통합 테스트 통과
- [ ] 에러 핸들링 검증
- [ ] 로깅 메시지 검토

#### Phase 2: 문서화
- [ ] 통합 계획서 작성 (본 문서)
- [ ] 사용자 가이드 작성
- [ ] API 설정 가이드 스크린샷 포함 PDF
- [ ] README 업데이트
- [ ] CHANGELOG 작성

#### Phase 3: 빌드 및 테스트
- [ ] 의존성 설치 확인 (`pip install -r requirements.txt`)
- [ ] PyInstaller 빌드 성공
- [ ] 실행파일 테스트 (구글 시트 연결)
- [ ] 백업 기능 테스트
- [ ] 오프라인 동작 테스트

#### Phase 4: 배포 준비
- [ ] 민감한 파일 제외 확인 (`.gitignore`)
- [ ] 버전 번호 업데이트 (`automation.spec`, `README`)
- [ ] 릴리스 노트 작성
- [ ] 배포 패키지 생성 (ZIP)

### 12.2 사용자 가이드 (요약)

#### 초기 설정 단계

**1단계: 구글 API 설정 (최초 1회)**
1. https://console.cloud.google.com/ 접속
2. 새 프로젝트 생성: "INTEROJO 자동화"
3. Google Sheets API 활성화
4. Service Account 생성 (역할: 편집자)
5. JSON 키 다운로드

**2단계: 구글 시트 준비**
1. https://sheets.google.com/ 에서 새 시트 생성
2. 시트 이름: "INTEROJO 자재요청 백업"
3. 공유 버튼 클릭
4. Service Account 이메일 추가 (JSON 파일 참조)
5. 권한: "편집자"
6. URL 복사

**3단계: INTEROJO 설정**
1. INTEROJO 실행
2. "구글 시트" 버튼 클릭
3. "찾아보기"로 JSON 파일 선택
4. 구글 시트 URL 붙여넣기
5. "연결 테스트" 클릭
6. 성공 메시지 확인

**4단계: 백업 실행**
1. "전체 백업 실행" 클릭
2. 구글 시트에서 데이터 확인
3. 자동 백업 활성화 (선택사항)

#### 일상적 사용

**자동 백업 활성화 시**:
- 자동화 실행 시 Excel 저장 후 구글 시트 자동 업데이트
- 별도 작업 불필요

**수동 백업**:
1. "구글 시트" 버튼 클릭
2. "전체 백업 실행" 클릭

#### 트러블슈팅

**연결 실패**:
- JSON 파일 경로 확인
- Service Account가 시트에 공유되었는지 확인
- 인터넷 연결 확인

**백업 실패**:
- 로그 파일 확인 (`logs/automation_YYYYMMDD.log`)
- 구글 시트 URL이 정확한지 확인
- 스프레드시트가 삭제되지 않았는지 확인

### 12.3 릴리스 노트 (예시)

```markdown
# INTEROJO 자동화 v2.2.0 - 2025-12-01

## 새로운 기능

### 구글 시트 백업 기능 추가
- 자재 요청 데이터를 구글 시트에 실시간 백업
- 클라우드 기반 데이터 보관으로 유실 방지
- 여러 사용자가 동시에 데이터 조회 가능
- 외부에서도 데이터 접근 가능

#### 주요 특징:
- **자동 백업**: Excel 저장 시 자동으로 구글 시트 업데이트
- **수동 백업**: "구글 시트" 버튼으로 즉시 백업
- **연결 테스트**: 설정 완료 후 즉시 연결 확인
- **샘플 데이터**: 테스트용 샘플 데이터 생성
- **백업 통계**: 성공/실패 횟수 추적

#### 설정 방법:
1. 구글 API 설정 가이드 참조
2. INTEROJO "구글 시트" 버튼 클릭
3. JSON 인증 파일 및 시트 URL 입력
4. 연결 테스트 후 백업 실행

## 개선 사항

- ExcelManager에 구글 시트 동기화 기능 추가
- 메인 윈도우에 "구글 시트" 버튼 추가
- 설정 파일에 구글 시트 옵션 추가

## 의존성 업데이트

- gspread 6.2.1 추가
- google-auth 2.25.2 추가
- google-auth-oauthlib 1.2.0 추가
- google-auth-httplib2 0.2.0 추가

## 알려진 이슈

- 대용량 데이터(5000행 이상) 백업 시 시간 소요 가능
- 분당 100회 백업 제한 (Google API Rate Limit)

## 업그레이드 방법

1. 새 버전 다운로드 및 압축 해제
2. 기존 .env 파일 백업
3. 기존 data/ 폴더 백업
4. 새 버전으로 덮어쓰기
5. .env 파일 복원
6. 구글 시트 설정 (신규 기능)

## 도움말

- 구글 시트 설정 가이드: "구글 시트" → "설정 가이드 보기"
- 문제 발생 시: logs/ 폴더의 로그 파일 확인
- 기술 지원: IT 담당자 문의
```

---

## 부록

### A. PythonProject3 vs INTEROJO 비교표

| 항목 | PythonProject3 | INTEROJO | 비고 |
|------|----------------|----------|------|
| GUI | PyQt5 | tkinter | tkinter로 재작성 필요 |
| 데이터 | DataFrame (pandas) | Dict 리스트 | 매핑 변환 필요 |
| 설정 | JSON만 | .env + JSON | .env 통합 |
| 백업 메서드 | backup_mixing_records | backup_materials | 이름 변경 |
| 컬럼 수 | 9개 (배합 기록) | 9개 (자재 요청) | 동일 |

### B. 구글 시트 API 참고 자료

- **gspread 공식 문서**: https://docs.gspread.org/
- **Google Sheets API**: https://developers.google.com/sheets/api
- **Service Account 가이드**: https://cloud.google.com/iam/docs/service-accounts
- **OAuth 2.0 Scopes**: https://developers.google.com/identity/protocols/oauth2/scopes

### C. 예상 타임라인

| Phase | 작업 내용 | 예상 시간 | 담당자 |
|-------|----------|----------|--------|
| 1 | 백엔드 구축 | 2-3시간 | 개발자 |
| 2 | ExcelManager 통합 | 1시간 | 개발자 |
| 3 | GUI 구현 | 2-3시간 | 개발자 |
| 4 | 설정 및 의존성 | 30분 | 개발자 |
| 5 | 테스트 | 2시간 | 개발자 + QA |
| 6 | 문서화 | 1시간 | 개발자 |
| 7 | 빌드 및 배포 | 1시간 | 개발자 |
| **총계** | | **10-12시간** | |

---

## 마무리

본 통합 계획서는 PythonProject3의 검증된 구글 시트 백업 기능을 INTEROJO 프로젝트에 안정적으로 통합하기 위한 상세한 로드맵을 제공합니다.

**핵심 원칙**:
1. **재사용**: 검증된 코드 최대한 활용
2. **안정성**: 기존 기능 유지하며 추가
3. **사용자 친화성**: 쉬운 설정 및 사용
4. **보안**: 인증 파일 보호
5. **문서화**: 상세한 가이드 제공

**다음 단계**:
1. 본 계획서 검토 및 승인
2. Phase 1부터 순차적 구현
3. 각 Phase별 테스트 및 검증
4. 최종 배포 및 사용자 교육

**문의사항**:
- 기술 문의: 개발팀
- 사용자 지원: IT 담당자

---

**문서 버전**: 1.0
**최종 업데이트**: 2025-12-01
**작성자**: Claude (AI Assistant)
**검토자**: (검토 후 기입)
**승인자**: (승인 후 기입)
