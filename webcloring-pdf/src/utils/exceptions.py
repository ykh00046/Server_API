"""
사용자 정의 예외 클래스들
전자결재 자동화 시스템에서 사용하는 예외 정의
"""


class AutomationError(Exception):
    """자동화 관련 기본 예외"""
    pass


class LoginError(AutomationError):
    """로그인 관련 예외"""
    pass


class NavigationError(AutomationError):
    """페이지 네비게이션 관련 예외"""
    pass


class DataExtractionError(AutomationError):
    """데이터 추출 관련 예외"""
    pass


class FileProcessingError(AutomationError):
    """파일 처리 관련 예외"""
    pass


class BrowserError(AutomationError):
    """브라우저 관련 예외"""
    pass


class ConfigurationError(AutomationError):
    """설정 관련 예외"""
    pass