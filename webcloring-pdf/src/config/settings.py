"""
전자결재 자동화 시스템 설정 관리
환경변수와 설정 파일을 통한 안전한 설정 관리
"""
import os
import sys
import json
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from utils.logger import logger


class Settings:
    """설정 관리 클래스"""
    
    def __init__(self, config_file: Optional[str] = None):
        # PyInstaller 실행파일에서는 릴리스 패키지의 루트 디렉토리를 base_dir로 사용
        if getattr(sys, 'frozen', False):
            # .exe 파일이 있는 디렉토리를 base_dir로 설정
            self.base_dir = Path(sys.executable).parent
        else:
            # 일반 Python 스크립트인 경우, 이 파일의 위치에서 세 단계 위로 올라가 프로젝트 루트를 찾음
            self.base_dir = Path(__file__).parent.parent.parent
            
        self.config_file = config_file or self.base_dir / "src" / "config" / "config.json"
        
        # 실행파일에서 필요한 디렉토리들 생성
        if getattr(sys, 'frozen', False):
            (self.base_dir / "logs").mkdir(exist_ok=True)
            (self.base_dir / "data" / "PDF").mkdir(parents=True, exist_ok=True)
            (self.base_dir / "data" / "excel").mkdir(parents=True, exist_ok=True)
        
        # 환경변수 로드
        self._load_env_file()
        
        # 설정 파일 로드
        self.config = self._load_config()
    
    def _load_env_file(self):
        """환경변수 파일 로드"""
        env_file = self.base_dir / ".env"
        
        # .env 파일이 없으면 .env.example에서 복사
        if not env_file.exists():
            env_example = self.base_dir / ".env.example"
            if env_example.exists():
                import shutil
                shutil.copy2(env_example, env_file)
                print(f"✅ .env 파일 생성: {env_file}")
        
        if env_file.exists():
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        if '=' in line:
                            key, value = line.split('=', 1)
                            os.environ[key] = value
    
    def _load_config(self) -> Dict[str, Any]:
        """설정 파일 로드"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"설정 파일 로드 실패: {e}")
        
        return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """기본 설정 반환"""
        return {
            "portal": {
                "url": "http://portal.interojo.com/portal/main/portalMain.do",
                "approval_url": "http://portal.interojo.com/approval/main/approvalMain.do",
                "timeout": 30,
                "retry_count": 3
            },
            "worksmobile": {
                "url": "https://talk.worksmobile.com/",
                "timeout": 20
            },
            "search": {
                "start_date": "2025.06.20",
                "keywords": ["자재", "접수"],
                "document_types": ["자재"]
            },
            "output": {
                "excel_file": "data/excel/Material_Release_Request.xlsx",
                "pdf_directory": "data/PDF",
                "backup_directory": "data/excel/backup"
            },
            "automation": {
                "scroll_delay": 2,
                "click_delay": 1,
                "page_load_timeout": 30,
                "implicit_wait": 10,
                "headless": False
            },
            "logging": {
                "level": "INFO",
                "file": "automation.log",
                "format": "%(asctime)s - %(levelname)s - %(message)s"
            }
        }
    
    def save_config(self):
        """설정 파일 저장"""
        os.makedirs(self.config_file.parent, exist_ok=True)
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)

    def save_env_settings(self, settings_dict: Dict[str, Any]):
        """주어진 딕셔너리를 .env 파일에 저장"""
        env_file = self.base_dir / ".env"
        
        # 1. 기존 .env 파일 내용 로드
        env_content = {}
        if env_file.exists():
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        env_content[key.strip()] = value.strip()
        
        # 2. 새로운 설정값으로 업데이트
        for key, value in settings_dict.items():
            env_content[key] = str(value)

        # 3. 파일 저장
        with open(env_file, 'w', encoding='utf-8') as f:
            f.write("# INTEROJO 포털 자동화 설정 (자동 생성됨)\n")
            for key, value in env_content.items():
                f.write(f"{key}={value}\n")
                # 4. 환경변수에도 즉시 반영
                os.environ[key] = str(value)
        
        logger.info(f".env 파일에 {len(settings_dict)}개의 설정 저장 완료")
    
    # 자격증명 관련 (환경변수에서 로드)
    @property
    def portal_username(self) -> str:
        username = os.getenv('PORTAL_USERNAME')
        if not username:
            raise ValueError("PORTAL_USERNAME 환경변수가 설정되지 않았습니다.")
        return username
    
    @property
    def portal_password(self) -> str:
        password = os.getenv('PORTAL_PASSWORD')
        if not password:
            raise ValueError("PORTAL_PASSWORD 환경변수가 설정되지 않았습니다.")
        return password
    
    @property
    def worksmobile_username(self) -> str:
        username = os.getenv('WORKSMOBILE_USERNAME')
        if not username:
            raise ValueError("WORKSMOBILE_USERNAME 환경변수가 설정되지 않았습니다.")
        return username
    
    @property
    def worksmobile_password(self) -> str:
        password = os.getenv('WORKSMOBILE_PASSWORD')
        if not password:
            raise ValueError("WORKSMOBILE_PASSWORD 환경변수가 설정되지 않았습니다.")
        return password
    
    # 포털 설정
    @property
    def portal_url(self) -> str:
        return self.config["portal"]["url"]
    
    @property
    def approval_url(self) -> str:
        return self.config["portal"]["approval_url"]
    
    @property
    def portal_timeout(self) -> int:
        return self.config["portal"]["timeout"]
    
    # WorksMobile 설정
    @property
    def worksmobile_url(self) -> str:
        return self.config["worksmobile"]["url"]
    
    # 검색 설정
    @property
    def search_keyword(self) -> str:
        """검색 키워드 (단일)"""
        return os.getenv('SEARCH_KEYWORD', '자재')

    @property
    def search_start_date(self) -> str:
        return os.getenv('SEARCH_START_DATE', self.config["search"]["start_date"])

    @property
    def search_keywords(self) -> list:
        return self.config["search"]["keywords"]

    @property
    def schedule_time(self) -> str:
        return os.getenv('SCHEDULE_TIME', '09:00')

    @property
    def auto_enabled(self) -> bool:
        return os.getenv('AUTO_ENABLED', 'True').lower() == 'true'

    @property
    def weekdays_only(self) -> bool:
        return os.getenv('WEEKDAYS_ONLY', 'False').lower() == 'true'

    @property
    def dynamic_filtering(self) -> bool:
        return os.getenv('DYNAMIC_FILTERING', 'True').lower() == 'true'

    @property
    def days_back(self) -> int:
        return int(os.getenv('DAYS_BACK', '0'))
    
    # 출력 설정
    @property
    def excel_file_path(self) -> Path:
        return self.base_dir / self.config["output"]["excel_file"]
    
    @property
    def pdf_directory(self) -> Path:
        pdf_dir = self.base_dir / self.config["output"]["pdf_directory"]
        pdf_dir.mkdir(exist_ok=True)
        return pdf_dir

    def get_pdf_directory_by_date(self, date_str: Optional[str] = None) -> Path:
        """날짜별 PDF 디렉토리 반환 (일자별 폴더 구조)

        Args:
            date_str: 날짜 문자열 (YYYY-MM-DD 형식). None이면 오늘 날짜 사용

        Returns:
            Path: 날짜별 PDF 디렉토리 경로 (예: data/PDF/2025-11-27/)
        """
        from datetime import datetime

        if date_str is None:
            date_str = datetime.now().strftime('%Y-%m-%d')

        # 날짜별 하위 폴더 생성
        pdf_dir = self.pdf_directory / date_str
        pdf_dir.mkdir(parents=True, exist_ok=True)

        return pdf_dir
    
    @property
    def screenshot_directory(self) -> Path:
        screenshot_dir = self.base_dir / "data" / "screenshots"
        screenshot_dir.mkdir(exist_ok=True)
        return screenshot_dir
    
    # 자동화 설정
    @property
    def scroll_delay(self) -> float:
        return self.config["automation"]["scroll_delay"]
    
    @property
    def click_delay(self) -> float:
        return self.config["automation"]["click_delay"]
    
    @property
    def page_load_timeout(self) -> int:
        return self.config["automation"]["page_load_timeout"]
    
    @property
    def implicit_wait(self) -> int:
        return self.config["automation"]["implicit_wait"]
    
    # 디버그 모드
    @property
    def debug_mode(self) -> bool:
        return os.getenv('DEBUG_MODE', 'False').lower() == 'true'

    @property
    def headless_mode(self) -> bool:
        return os.getenv('HEADLESS_MODE', str(self.config["automation"].get("headless", False))).lower() == 'true'

    # Notification Settings
    @property
    def smtp_server(self) -> Optional[str]:
        return os.getenv('SMTP_SERVER')

    @property
    def smtp_port(self) -> int:
        return int(os.getenv('SMTP_PORT', 587))

    @property
    def email_user(self) -> Optional[str]:
        return os.getenv('EMAIL_USER')

    @property
    def email_password(self) -> Optional[str]:
        return os.getenv('EMAIL_PASSWORD')

    @property
    def notification_email_to(self) -> Optional[str]:
        return os.getenv('NOTIFICATION_EMAIL_TO')

    @property
    def notification_webhook_url(self) -> Optional[str]:
        return os.getenv('NOTIFICATION_WEBHOOK_URL')

    # Excel 설정
    @property
    def auto_save_interval(self) -> int:
        """Excel 자동 저장 간격 (초 단위)"""
        return self.config.get("excel", {}).get("auto_save_interval", 300)

    # Google Sheets 설정
    @property
    def min_backup_interval(self) -> int:
        """Google Sheets 최소 백업 간격 (초 단위)"""
        return self.config.get("google_sheets", {}).get("min_backup_interval", 60)

    @property
    def batch_processing(self) -> bool:
        """Google Sheets 배치 처리 활성화"""
        return self.config.get("google_sheets", {}).get("batch_processing", True)

    # Pagination 설정
    @property
    def max_pages(self) -> int:
        """최대 처리 페이지 수"""
        return self.config.get("pagination", {}).get("max_pages", 100)

    @property
    def max_consecutive_errors(self) -> int:
        """최대 연속 오류 허용 횟수"""
        return self.config.get("pagination", {}).get("max_consecutive_errors", 3)

    @property
    def page_size(self) -> int:
        """페이지당 표시 문서 수"""
        return self.config.get("pagination", {}).get("page_size", 50)

    def get(self, key_path: str, default=None):
        """점 표기법으로 설정값 가져오기"""
        keys = key_path.split('.')
        value = self.config
        
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default


# 글로벌 설정 인스턴스
settings = Settings()