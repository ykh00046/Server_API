"""
로깅 유틸리티
전자결재 자동화 시스템의 통합 로깅 관리
"""
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


class AutomationLogger:
    """자동화 전용 로거 클래스"""
    
    def __init__(self, name: str = "interojo_automation", log_file: Optional[str] = None):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        # 중복 핸들러 방지
        if not self.logger.handlers:
            self._setup_handlers(log_file)
    
    def _setup_handlers(self, log_file: Optional[str]):
        """로깅 핸들러 설정"""
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 콘솔 핸들러
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # 파일 핸들러 (로테이션 지원)
        if log_file:
            try:
                from logging.handlers import RotatingFileHandler

                log_path = Path(log_file)
                log_path.parent.mkdir(parents=True, exist_ok=True)

                # 로테이팅 파일 핸들러: 최대 10MB, 최대 10개 백업 파일
                file_handler = RotatingFileHandler(
                    log_path,
                    maxBytes=10*1024*1024,  # 10MB
                    backupCount=10,
                    encoding='utf-8'
                )
                file_handler.setLevel(logging.DEBUG)
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)
            except Exception as e:
                self.logger.warning(f"파일 로깅 설정 실패: {e}")
    
    def info(self, message: str):
        """정보 로그"""
        self.logger.info(message)
    
    def debug(self, message: str):
        """디버그 로그"""
        self.logger.debug(message)
    
    def warning(self, message: str):
        """경고 로그"""
        self.logger.warning(message)
    
    def error(self, message: str):
        """오류 로그"""
        self.logger.error(message)
    
    def critical(self, message: str):
        """심각한 오류 로그"""
        self.logger.critical(message)
    
    def step(self, action: str, detail: str = ""):
        """단계별 작업 로그"""
        if detail:
            self.info(f"📍 {action}: {detail}")
        else:
            self.info(f"📍 {action}")
    
    def automation_start(self, process_name: str):
        """자동화 프로세스 시작 로그"""
        self.info(f"🚀 {process_name} 시작")
    
    def automation_end(self, process_name: str, success: bool = True):
        """자동화 프로세스 종료 로그"""
        status = "성공" if success else "실패"
        icon = "✅" if success else "❌"
        self.info(f"{icon} {process_name} {status}")
    
    def login_attempt(self, username: str, system: str):
        """로그인 시도 로그"""
        self.info(f"🔐 {system} 로그인 시도: {username}")
    
    def login_success(self, system: str):
        """로그인 성공 로그"""
        self.info(f"✅ {system} 로그인 성공")
    
    def login_failed(self, system: str, reason: str):
        """로그인 실패 로그"""
        self.error(f"❌ {system} 로그인 실패: {reason}")
    
    def data_extracted(self, count: int, data_type: str):
        """데이터 추출 완료 로그"""
        self.info(f"📊 {data_type} 추출 완료: {count}건")
    
    def file_saved(self, file_path: str, file_type: str):
        """파일 저장 완료 로그"""
        self.info(f"💾 {file_type} 파일 저장: {file_path}")
    
    def browser_action(self, action: str, target: str = ""):
        """브라우저 액션 로그"""
        if target:
            self.debug(f"🌐 브라우저: {action} - {target}")
        else:
            self.debug(f"🌐 브라우저: {action}")
    
    def set_level(self, level: str):
        """로그 레벨 설정"""
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        
        if level.upper() in level_map:
            self.logger.setLevel(level_map[level.upper()])
            self.info(f"로그 레벨 변경: {level.upper()}")


# 전역 로거 인스턴스
import sys

# PyInstaller 실행파일에서는 실행파일 위치 기준으로 로그 저장
if getattr(sys, 'frozen', False):
    # PyInstaller로 빌드된 실행파일인 경우
    project_root = Path(sys.executable).parent
else:
    # 일반 Python 스크립트인 경우
    project_root = Path(__file__).parent.parent

log_file = project_root / "logs" / f"automation_{datetime.now().strftime('%Y%m%d')}.log"
logger = AutomationLogger(log_file=str(log_file))