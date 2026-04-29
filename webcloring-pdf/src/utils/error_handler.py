import time
import functools
from datetime import datetime
from pathlib import Path

from utils.logger import logger
from utils.exceptions import LoginError, NavigationError, AutomationError
from config.settings import settings


# retry 기능은 retry_decorator.py로 통합됨 (중복 제거)
# 기존 호출 코드와의 호환성을 위해 re-export
from utils.retry_decorator import retry as retry_on_failure


def handle_selenium_errors(default_return=None, log_error=True, screenshot_on_error=False):
    """Selenium 관련 오류 처리 데코레이터"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if log_error:
                    logger.error(f"Selenium 오류 in {func.__name__}: {e}")
                
                if screenshot_on_error and len(args) > 0:
                    # 첫 번째 인자가 self이고 driver 속성이 있다면 스크린샷 촬영
                    self_obj = args[0]
                    if hasattr(self_obj, 'driver') and self_obj.driver:
                        take_error_screenshot(self_obj.driver, func.__name__)
                
                if default_return is not None:
                    return default_return
                else:
                    raise AutomationError(f"브라우저 작업 실패: {e}")
        
        return wrapper
    return decorator


def handle_login_errors(system_name):
    """로그인 관련 오류 처리 데코레이터"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"{system_name} 로그인 실패: {e}")
                raise LoginError(system_name, str(e))
        
        return wrapper
    return decorator


def handle_navigation_errors(page_name):
    """페이지 네비게이션 오류 처리 데코레이터"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error(f"{page_name} 페이지 이동 실패: {e}")
                raise NavigationError(page_name, str(e))
        
        return wrapper
    return decorator


def log_execution_time(func):
    """실행 시간 로깅 데코레이터"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = datetime.now()
        try:
            result = func(*args, **kwargs)
            execution_time = datetime.now() - start_time
            logger.debug(f"{func.__name__} 실행 완료 ({execution_time.total_seconds():.2f}초)")
            return result
        except Exception as e:
            execution_time = datetime.now() - start_time
            logger.error(f"{func.__name__} 실행 실패 ({execution_time.total_seconds():.2f}초): {e}")
            raise
    
    return wrapper


def take_error_screenshot(driver, error_type):
    """오류 발생 시 스크린샷 저장"""
    try:
        if driver:
            screenshots_dir = settings.screenshot_directory
            screenshots_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = screenshots_dir / f"error_{error_type}_{timestamp}.png"
            
            driver.save_screenshot(str(screenshot_path))
            logger.info(f"오류 스크린샷 저장: {screenshot_path}")
            
    except Exception as e:
        logger.warning(f"스크린샷 저장 실패: {e}")