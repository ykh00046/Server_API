"""
재시도 데코레이터

Exponential Backoff 전략을 사용한 재시도 로직을 제공합니다.
일시적 네트워크 오류나 타임아웃 등에 대한 자동 복구를 지원합니다.
"""
import time
import functools
from typing import Callable, Tuple, Type
import sys
from pathlib import Path

from utils.logger import logger


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,)
):
    """재시도 데코레이터
    
    지정된 예외가 발생하면 자동으로 재시도합니다.
    Exponential Backoff 전략을 사용하여 대기 시간을 점진적으로 증가시킵니다.
    
    사용 예시:
        @retry(max_attempts=3, delay=2.0, exceptions=(TimeoutException,))
        def unstable_network_call():
            # 네트워크 호출 코드
            pass
    
    Args:
        max_attempts: 최대 시도 횟수 (기본값: 3)
        delay: 초기 대기 시간 초 단위 (기본값: 1.0)
        backoff: 대기 시간 증가 배율 (기본값: 2.0, Exponential Backoff)
        exceptions: 재시도할 예외 타입 튜플 (기본값: 모든 예외)
    
    Returns:
        데코레이터 함수
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 1
            current_delay = delay
            
            while attempt <= max_attempts:
                try:
                    return func(*args, **kwargs)
                    
                except exceptions as e:
                    if attempt == max_attempts:
                        # 최대 재시도 횟수 도달
                        logger.error(
                            f"{func.__name__} 최대 재시도 횟수 도달 "
                            f"({max_attempts}회): {e}"
                        )
                        raise
                    
                    # 재시도 로그
                    logger.warning(
                        f"{func.__name__} 실패 (시도 {attempt}/{max_attempts}), "
                        f"{current_delay:.1f}초 후 재시도: {e}"
                    )
                    
                    # 대기
                    time.sleep(current_delay)
                    
                    # Exponential Backoff
                    current_delay *= backoff
                    attempt += 1
            
        return wrapper
    return decorator


def retry_with_cleanup(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    cleanup_func: Callable = None
):
    """정리 작업을 포함한 재시도 데코레이터
    
    각 재시도 전에 cleanup_func을 실행하여 상태를 초기화합니다.
    
    사용 예시:
        def cleanup():
            driver.refresh()
        
        @retry_with_cleanup(max_attempts=3, cleanup_func=cleanup)
        def navigate_to_page():
            # 페이지 이동 코드
            pass
    
    Args:
        max_attempts: 최대 시도 횟수
        delay: 초기 대기 시간
        backoff: 대기 시간 증가 배율
        exceptions: 재시도할 예외 타입 튜플
        cleanup_func: 재시도 전 실행할 정리 함수
    
    Returns:
        데코레이터 함수
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 1
            current_delay = delay
            
            while attempt <= max_attempts:
                try:
                    return func(*args, **kwargs)
                    
                except exceptions as e:
                    if attempt == max_attempts:
                        logger.error(
                            f"{func.__name__} 최대 재시도 횟수 도달 "
                            f"({max_attempts}회): {e}"
                        )
                        raise
                    
                    logger.warning(
                        f"{func.__name__} 실패 (시도 {attempt}/{max_attempts}), "
                        f"{current_delay:.1f}초 후 재시도: {e}"
                    )
                    
                    # 정리 작업 실행
                    if cleanup_func:
                        try:
                            logger.debug(f"정리 작업 실행: {cleanup_func.__name__}")
                            cleanup_func()
                        except Exception as cleanup_error:
                            logger.warning(f"정리 작업 실패: {cleanup_error}")
                    
                    time.sleep(current_delay)
                    current_delay *= backoff
                    attempt += 1
            
        return wrapper
    return decorator


if __name__ == "__main__":
    # 간단한 테스트
    print("재시도 데코레이터 테스트\n")
    
    # 테스트 1: 성공하는 함수
    @retry(max_attempts=3, delay=0.5)
    def successful_function():
        print("  ✅ 함수 실행 성공")
        return "OK"
    
    print("1. 성공 케이스:")
    result = successful_function()
    print(f"  결과: {result}\n")
    
    # 테스트 2: 2번 실패 후 성공
    attempt_counter = 0
    
    @retry(max_attempts=3, delay=0.5)
    def unstable_function():
        global attempt_counter
        attempt_counter += 1
        print(f"  시도 {attempt_counter}")
        
        if attempt_counter < 3:
            raise ValueError("일시적 오류")
        return "성공"
    
    print("2. 재시도 후 성공:")
    try:
        result = unstable_function()
        print(f"  최종 결과: {result}\n")
    except:
        print("  실패\n")
    
    # 테스트 3: 완전 실패
    @retry(max_attempts=2, delay=0.5)
    def failing_function():
        print("  ❌ 함수 실행 실패")
        raise RuntimeError("복구 불가능한 오류")
    
    print("3. 완전 실패 케이스:")
    try:
        failing_function()
    except RuntimeError as e:
        print(f"  예외 발생: {e}\n")
    
    print("✅ 테스트 완료")
