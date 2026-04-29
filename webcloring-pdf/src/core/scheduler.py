"""
작업 스케줄링 관리 클래스
실시간 모니터링 서비스의 정기적 작업을 관리합니다.
"""
import time
import threading
from datetime import datetime, timedelta
from typing import Callable, Dict, Any, List
from schedule import Job
import schedule

from utils.logger import logger


class ServiceScheduler:
    """서비스 스케줄링 클래스"""
    
    def __init__(self):
        self.running = False
        self.jobs = []
        self.thread = None
        self.last_run_times = {}
        
    def every(self, interval: int):
        """스케줄링 인터페이스"""
        return ScheduleBuilder(self, interval)
    
    def add_job(self, job_func: Callable, interval_minutes: int, job_name: str = None):
        """작업 추가"""
        job_name = job_name or job_func.__name__
        
        job = schedule.every(interval_minutes).minutes.do(self._safe_job_wrapper, job_func, job_name)
        self.jobs.append({
            'job': job,
            'name': job_name,
            'function': job_func,
            'interval': interval_minutes
        })
        
        logger.info(f"⏰ 작업 등록: {job_name} ({interval_minutes}분 간격)")
    
    def _safe_job_wrapper(self, job_func: Callable, job_name: str):
        """작업 실행 래퍼 (에러 처리 포함)"""
        try:
            start_time = datetime.now()
            logger.debug(f"🔧 작업 시작: {job_name}")
            
            # 작업 실행
            result = job_func()
            
            # 실행 시간 기록
            execution_time = datetime.now() - start_time
            self.last_run_times[job_name] = {
                'start_time': start_time,
                'execution_time': execution_time,
                'success': True,
                'result': result
            }
            
            logger.debug(f"✅ 작업 완료: {job_name} ({execution_time.total_seconds():.2f}초)")
            
        except Exception as e:
            # 실행 시간 기록 (실패)
            execution_time = datetime.now() - start_time
            self.last_run_times[job_name] = {
                'start_time': start_time,
                'execution_time': execution_time,
                'success': False,
                'error': str(e)
            }
            
            logger.error(f"❌ 작업 실패: {job_name} - {e}")
    
    def run_continuously(self):
        """스케줄러 연속 실행"""
        self.running = True
        logger.info("⏰ 스케줄러 시작됨")
        
        while self.running:
            try:
                schedule.run_pending()
                time.sleep(1)  # 1초마다 체크
                
            except Exception as e:
                logger.error(f"스케줄러 오류: {e}")
                time.sleep(5)  # 오류 시 5초 대기
        
        logger.info("⏰ 스케줄러 종료됨")
    
    def start(self):
        """스케줄러 스레드 시작"""
        if not self.running:
            self.thread = threading.Thread(target=self.run_continuously, daemon=True)
            self.thread.start()
            logger.info("🚀 스케줄러 스레드 시작")
    
    def stop(self):
        """스케줄러 중지"""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        logger.info("🛑 스케줄러 중지됨")
    
    def get_job_status(self) -> Dict[str, Any]:
        """작업 상태 정보 반환"""
        status = {
            'running': self.running,
            'total_jobs': len(self.jobs),
            'jobs': []
        }
        
        for job_info in self.jobs:
            job_name = job_info['name']
            last_run = self.last_run_times.get(job_name, {})
            
            job_status = {
                'name': job_name,
                'interval_minutes': job_info['interval'],
                'last_run': last_run.get('start_time'),
                'last_success': last_run.get('success'),
                'last_execution_time': str(last_run.get('execution_time', '')),
                'next_run': job_info['job'].next_run
            }
            
            if not last_run.get('success', True):
                job_status['last_error'] = last_run.get('error')
            
            status['jobs'].append(job_status)
        
        return status
    
    def run_job_now(self, job_name: str) -> bool:
        """특정 작업을 즉시 실행"""
        for job_info in self.jobs:
            if job_info['name'] == job_name:
                try:
                    logger.info(f"🚀 수동 실행: {job_name}")
                    self._safe_job_wrapper(job_info['function'], job_name)
                    return True
                except Exception as e:
                    logger.error(f"수동 실행 실패 {job_name}: {e}")
                    return False
        
        logger.warning(f"작업을 찾을 수 없음: {job_name}")
        return False
    
    def clear_all_jobs(self):
        """모든 작업 제거"""
        schedule.clear()
        self.jobs.clear()
        self.last_run_times.clear()
        logger.info("🧹 모든 스케줄 작업 제거됨")


class ScheduleBuilder:
    """스케줄링 빌더 클래스 (schedule 라이브러리 호환)"""
    
    def __init__(self, scheduler: ServiceScheduler, interval: int):
        self.scheduler = scheduler
        self.interval = interval
    
    @property
    def minutes(self):
        """분 단위 스케줄링"""
        return MinuteScheduler(self.scheduler, self.interval)
    
    @property
    def hours(self):
        """시간 단위 스케줄링"""
        return HourScheduler(self.scheduler, self.interval)
    
    @property
    def day(self):
        """일 단위 스케줄링"""
        return DayScheduler(self.scheduler, self.interval)


class MinuteScheduler:
    """분 단위 스케줄러"""
    
    def __init__(self, scheduler: ServiceScheduler, interval: int):
        self.scheduler = scheduler
        self.interval = interval
    
    def do(self, job_func: Callable, *args, **kwargs):
        """작업 등록"""
        wrapped_func = lambda: job_func(*args, **kwargs)
        wrapped_func.__name__ = job_func.__name__
        
        self.scheduler.add_job(wrapped_func, self.interval, job_func.__name__)
        return self


class HourScheduler:
    """시간 단위 스케줄러"""
    
    def __init__(self, scheduler: ServiceScheduler, interval: int):
        self.scheduler = scheduler
        self.interval = interval * 60  # 분으로 변환
    
    def do(self, job_func: Callable, *args, **kwargs):
        """작업 등록"""
        wrapped_func = lambda: job_func(*args, **kwargs)
        wrapped_func.__name__ = job_func.__name__
        
        self.scheduler.add_job(wrapped_func, self.interval, job_func.__name__)
        return self


class DayScheduler:
    """일 단위 스케줄러"""
    
    def __init__(self, scheduler: ServiceScheduler, interval: int):
        self.scheduler = scheduler
        self.interval = interval * 24 * 60  # 분으로 변환
    
    def at(self, time_str: str):
        """특정 시간에 실행"""
        return TimeScheduler(self.scheduler, self.interval, time_str)
    
    def do(self, job_func: Callable, *args, **kwargs):
        """작업 등록 (매일 같은 시간)"""
        wrapped_func = lambda: job_func(*args, **kwargs)
        wrapped_func.__name__ = job_func.__name__
        
        # schedule 라이브러리 사용
        schedule.every().day.do(self.scheduler._safe_job_wrapper, wrapped_func, job_func.__name__)
        
        self.scheduler.jobs.append({
            'job': schedule.jobs[-1],
            'name': job_func.__name__,
            'function': wrapped_func,
            'interval': 'daily'
        })
        
        logger.info(f"⏰ 일일 작업 등록: {job_func.__name__}")
        return self


class TimeScheduler:
    """특정 시간 스케줄러"""
    
    def __init__(self, scheduler: ServiceScheduler, interval: int, time_str: str):
        self.scheduler = scheduler
        self.interval = interval
        self.time_str = time_str
    
    def do(self, job_func: Callable, *args, **kwargs):
        """특정 시간에 작업 등록"""
        wrapped_func = lambda: job_func(*args, **kwargs)
        wrapped_func.__name__ = job_func.__name__
        
        # schedule 라이브러리 사용
        schedule.every().day.at(self.time_str).do(
            self.scheduler._safe_job_wrapper, 
            wrapped_func, 
            job_func.__name__
        )
        
        self.scheduler.jobs.append({
            'job': schedule.jobs[-1],
            'name': job_func.__name__,
            'function': wrapped_func,
            'interval': f'daily at {self.time_str}'
        })
        
        logger.info(f"⏰ 시간별 작업 등록: {job_func.__name__} (매일 {self.time_str})")
        return self