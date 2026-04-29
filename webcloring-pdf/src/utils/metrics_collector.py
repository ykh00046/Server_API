"""
실시간 메트릭 수집 모듈

자동화 실행 중 주요 성능 지표를 수집하고 통계를 생성합니다.
"""
import psutil
import time
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path

from utils.logger import logger


class MetricsCollector:
    """실시간 메트릭 수집 및 통계 생성 클래스
    
    자동화 실행 중 다음 지표를 수집합니다:
    - 처리 문서 수 (성공/실패/스킵)
    - 처리 시간 (전체, 문서당, PDF, Excel)
    - 시스템 리소스 (메모리, 디스크)
    
    Attributes:
        metrics (dict): 수집된 메트릭 데이터
        current_doc_start (float): 현재 문서 처리 시작 시간
    """
    
    def __init__(self):
        """초기화"""
        self.metrics = {
            'start_time': None,
            'end_time': None,
            'total_documents': 0,
            'success_count': 0,
            'failed_count': 0,
            'skipped_count': 0,
            'processing_times': [],  # 문서당 처리 시간 (초)
            'pdf_times': [],         # PDF 생성 시간 (초)
            'excel_times': [],       # Excel 저장 시간 (초)
            'memory_samples': [],    # 메모리 사용량 샘플 (MB)
            'disk_usage': [],        # 디스크 사용량 샘플 (GB)
            'errors': []             # 오류 메시지 목록
        }
        self.current_doc_start = None
        self.process = psutil.Process()
        
        logger.debug("MetricsCollector 초기화")
    
    def start_run(self):
        """자동화 실행 시작 기록"""
        self.metrics['start_time'] = datetime.now()
        self.sample_system_metrics()
        logger.info("📊 메트릭 수집 시작")
    
    def end_run(self):
        """자동화 실행 종료 기록"""
        self.metrics['end_time'] = datetime.now()
        self.sample_system_metrics()
        logger.info("📊 메트릭 수집 종료")
    
    def start_document(self):
        """문서 처리 시작 기록"""
        self.current_doc_start = time.time()
    
    def end_document(self, status: str):
        """문서 처리 종료 기록
        
        Args:
            status: 처리 상태 ('success', 'failed', 'skipped')
        """
        # 처리 시간 기록
        if self.current_doc_start is not None:
            elapsed = time.time() - self.current_doc_start
            self.metrics['processing_times'].append(elapsed)
            self.current_doc_start = None
        
        # 카운트 증가
        self.metrics['total_documents'] += 1
        
        if status == 'success':
            self.metrics['success_count'] += 1
        elif status == 'failed':
            self.metrics['failed_count'] += 1
        elif status == 'skipped':
            self.metrics['skipped_count'] += 1
        
        # 주기적으로 시스템 메트릭 샘플링 (10개 문서마다)
        if self.metrics['total_documents'] % 10 == 0:
            self.sample_system_metrics()
    
    def record_pdf_time(self, elapsed: float):
        """PDF 생성 시간 기록
        
        Args:
            elapsed: 소요 시간 (초)
        """
        self.metrics['pdf_times'].append(elapsed)
        logger.debug(f"PDF 생성 시간: {elapsed:.2f}초")
    
    def record_excel_time(self, elapsed: float):
        """Excel 저장 시간 기록
        
        Args:
            elapsed: 소요 시간 (초)
        """
        self.metrics['excel_times'].append(elapsed)
        logger.debug(f"Excel 저장 시간: {elapsed:.2f}초")
    
    def record_error(self, error_message: str):
        """오류 메시지 기록
        
        Args:
            error_message: 오류 메시지
        """
        self.metrics['errors'].append({
            'timestamp': datetime.now().isoformat(),
            'message': error_message
        })
    
    def sample_system_metrics(self):
        """시스템 메트릭 샘플링
        
        메모리 및 디스크 사용량을 현재 시점에서 측정합니다.
        """
        try:
            # 메모리 사용량 (MB)
            memory_mb = self.process.memory_info().rss / 1024 / 1024
            self.metrics['memory_samples'].append(memory_mb)
            
            # 디스크 사용량 (GB) - 현재 디렉토리 기준
            disk_usage = psutil.disk_usage('.')
            disk_used_gb = disk_usage.used / 1024 / 1024 / 1024
            self.metrics['disk_usage'].append(disk_used_gb)
            
            logger.debug(f"시스템 메트릭: 메모리={memory_mb:.1f}MB, 디스크={disk_used_gb:.1f}GB")
            
        except Exception as e:
            logger.warning(f"시스템 메트릭 샘플링 실패: {e}")
    
    def get_current_stats(self) -> Dict:
        """현재 통계 조회 (실시간)
        
        Returns:
            현재까지의 통계 딕셔너리
        """
        return {
            'total_documents': self.metrics['total_documents'],
            'success_count': self.metrics['success_count'],
            'failed_count': self.metrics['failed_count'],
            'skipped_count': self.metrics['skipped_count'],
            'success_rate': self._calculate_success_rate(),
            'current_memory_mb': self.metrics['memory_samples'][-1] if self.metrics['memory_samples'] else 0
        }
    
    def get_summary(self) -> Dict:
        """실행 요약 통계 생성
        
        자동화 완료 후 전체 실행에 대한 요약 통계를 반환합니다.
        
        Returns:
            요약 통계 딕셔너리
        """
        # 실행 시간 계산
        duration = None
        if self.metrics['start_time'] and self.metrics['end_time']:
            duration = (self.metrics['end_time'] - self.metrics['start_time']).total_seconds()
        
        # 평균 처리 시간
        avg_processing_time = self._calculate_average(self.metrics['processing_times'])
        avg_pdf_time = self._calculate_average(self.metrics['pdf_times'])
        avg_excel_time = self._calculate_average(self.metrics['excel_times'])
        
        # 메모리 통계
        avg_memory = self._calculate_average(self.metrics['memory_samples'])
        peak_memory = max(self.metrics['memory_samples']) if self.metrics['memory_samples'] else 0
        
        # 성공률
        success_rate = self._calculate_success_rate()
        
        summary = {
            'start_time': self.metrics['start_time'].isoformat() if self.metrics['start_time'] else None,
            'end_time': self.metrics['end_time'].isoformat() if self.metrics['end_time'] else None,
            'duration_seconds': round(duration, 1) if duration else 0,
            'total_documents': self.metrics['total_documents'],
            'success_count': self.metrics['success_count'],
            'failed_count': self.metrics['failed_count'],
            'skipped_count': self.metrics['skipped_count'],
            'success_rate': success_rate,
            'avg_processing_time': avg_processing_time,
            'avg_pdf_time': avg_pdf_time,
            'avg_excel_time': avg_excel_time,
            'avg_memory_mb': avg_memory,
            'peak_memory_mb': peak_memory,
            'error_count': len(self.metrics['errors'])
        }
        
        logger.info(f"📊 요약 통계: {summary}")
        return summary
    
    def _calculate_average(self, values: List[float]) -> float:
        """평균 계산 헬퍼 메서드
        
        Args:
            values: 값 리스트
            
        Returns:
            평균값 (소수점 2자리)
        """
        if not values:
            return 0.0
        return round(sum(values) / len(values), 2)
    
    def _calculate_success_rate(self) -> float:
        """성공률 계산
        
        Returns:
            성공률 퍼센트 (0-100)
        """
        if self.metrics['total_documents'] == 0:
            return 0.0
        
        rate = (self.metrics['success_count'] / self.metrics['total_documents']) * 100
        return round(rate, 2)
    
    def export_to_dict(self) -> Dict:
        """전체 메트릭 데이터 내보내기
        
        Returns:
            모든 메트릭 데이터를 포함한 딕셔너리
        """
        return {
            'summary': self.get_summary(),
            'raw_metrics': {
                'processing_times': self.metrics['processing_times'],
                'pdf_times': self.metrics['pdf_times'],
                'excel_times': self.metrics['excel_times'],
                'memory_samples': self.metrics['memory_samples'],
                'errors': self.metrics['errors']
            }
        }
    
    def reset(self):
        """메트릭 초기화
        
        새로운 실행을 위해 모든 메트릭을 초기 상태로 리셋합니다.
        """
        self.__init__()
        logger.info("메트릭 초기화 완료")


if __name__ == "__main__":
    # 간단한 테스트
    print("MetricsCollector 테스트\n")
    
    collector = MetricsCollector()
    
    # 실행 시작
    collector.start_run()
    
    # 문서 처리 시뮬레이션
    for i in range(5):
        collector.start_document()
        time.sleep(0.1)  # 처리 시뮬레이션
        
        status = 'success' if i < 4 else 'failed'
        collector.end_document(status)
        
        collector.record_pdf_time(0.05)
        collector.record_excel_time(0.03)
    
    # 실행 종료
    collector.end_run()
    
    # 요약 출력
    summary = collector.get_summary()
    print("\n=== 요약 통계 ===")
    for key, value in summary.items():
        print(f"{key}: {value}")
    
    print("\n✅ 테스트 완료")
