"""
시스템 헬스 체크 모듈

자동화 시스템의 주요 구성 요소 상태를 점검하고,
문제를 조기에 발견하여 장애를 예방합니다.
"""
import requests
import psutil
import time
import sys
import platform
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

from config.settings import settings
from utils.logger import logger


class HealthChecker:
    """시스템 헬스 체크 클래스
    
    자동화 시스템의 핵심 구성 요소 상태를 점검합니다:
    - 포털 접속 가능 여부
    - Google Sheets 연결 상태
    - 디스크 여유 공간
    - Excel 파일 쓰기 권한
    
    Attributes:
        last_check_time (datetime): 마지막 점검 시간
    """
    
    def __init__(self):
        """초기화"""
        self.last_check_time = None
        logger.debug("HealthChecker 초기화")
    
    def check_portal_connectivity(self) -> Dict:
        """포털 접속 가능 여부 확인
        
        HTTP GET 요청을 통해 포털이 응답하는지 확인합니다.
        
        Returns:
            {
                'status': bool,           # 접속 성공 여부
                'message': str,           # 상세 메시지
                'response_time': float,   # 응답 시간 (초)
                'timestamp': str          # 점검 시각
            }
        """
        try:
            start = time.time()
            response = requests.get(
                settings.portal_url,
                timeout=10,
                verify=False  # SSL 검증 비활성화 (내부 포털용)
            )
            elapsed = time.time() - start
            
            is_ok = response.status_code == 200
            
            result = {
                'status': is_ok,
                'message': f'응답 코드: {response.status_code}',
                'response_time': round(elapsed, 2),
                'timestamp': datetime.now().isoformat()
            }
            
            if is_ok:
                logger.debug(f"포털 접속 정상 ({elapsed:.2f}초)")
            else:
                logger.warning(f"포털 응답 이상: {response.status_code}")
            
            return result
            
        except requests.Timeout:
            logger.warning("포털 접속 타임아웃 (10초)")
            return {
                'status': False,
                'message': '타임아웃 (10초 초과)',
                'response_time': None,
                'timestamp': datetime.now().isoformat()
            }
        except requests.ConnectionError:
            logger.error("포털 접속 불가 - 네트워크 오류")
            return {
                'status': False,
                'message': '네트워크 연결 오류',
                'response_time': None,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"포털 접속 점검 오류: {e}")
            return {
                'status': False,
                'message': f'오류: {str(e)}',
                'response_time': None,
                'timestamp': datetime.now().isoformat()
            }
    
    def check_google_sheets_connection(self) -> Dict:
        """Google Sheets 연결 상태 확인
        
        Google Sheets API 인증 및 접근 권한을 테스트합니다.
        
        Returns:
            {
                'status': bool,      # 연결 성공 여부
                'message': str,      # 상세 메시지
                'timestamp': str     # 점검 시각
            }
        """
        try:
            from services.google_sheets_manager import GoogleSheetsManager
            
            manager = GoogleSheetsManager()
            
            # 연결 테스트
            success = manager.test_connection()
            
            result = {
                'status': success,
                'message': '연결 성공' if success else '연결 실패',
                'timestamp': datetime.now().isoformat()
            }
            
            if success:
                logger.debug("Google Sheets 연결 정상")
            else:
                logger.warning("Google Sheets 연결 실패")
            
            return result
            
        except ImportError:
            logger.warning("Google Sheets 모듈 없음 (선택 기능)")
            return {
                'status': True,  # 선택 기능이므로 전체 상태에는 영향 없음
                'message': 'Google Sheets 모듈 없음 (선택 사항)',
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Google Sheets 연결 점검 오류: {e}")
            return {
                'status': False,
                'message': f'오류: {str(e)}',
                'timestamp': datetime.now().isoformat()
            }
    
    def check_disk_space(self, min_gb: float = 1.0) -> Dict:
        """디스크 여유 공간 확인
        
        작업 디렉토리의 디스크 여유 공간을 점검합니다.
        
        Args:
            min_gb: 최소 여유 공간 (GB, 기본값 1.0)
            
        Returns:
            {
                'status': bool,          # 충분한 공간 여부
                'message': str,          # 상세 메시지
                'free_gb': float,        # 여유 공간 (GB)
                'used_percent': float,   # 사용률 (%)
                'timestamp': str         # 점검 시각
            }
        """
        try:
            disk = psutil.disk_usage('.')
            free_gb = disk.free / 1024 / 1024 / 1024
            used_percent = disk.percent
            
            is_ok = free_gb >= min_gb
            
            result = {
                'status': is_ok,
                'message': f'여유: {free_gb:.2f}GB / 사용률: {used_percent}%',
                'free_gb': round(free_gb, 2),
                'used_percent': used_percent,
                'timestamp': datetime.now().isoformat()
            }
            
            if is_ok:
                logger.debug(f"디스크 공간 충분: {free_gb:.2f}GB")
            else:
                logger.warning(f"디스크 공간 부족: {free_gb:.2f}GB < {min_gb}GB")
            
            return result
            
        except Exception as e:
            logger.error(f"디스크 공간 점검 오류: {e}")
            return {
                'status': False,
                'message': f'오류: {str(e)}',
                'free_gb': None,
                'used_percent': None,
                'timestamp': datetime.now().isoformat()
            }
    
    def check_excel_write_permission(self) -> Dict:
        """Excel 파일 쓰기 권한 확인
        
        Excel 파일이 존재하면 쓰기 권한을,
        없으면 디렉토리 쓰기 권한을 확인합니다.
        
        Returns:
            {
                'status': bool,      # 쓰기 가능 여부
                'message': str,      # 상세 메시지
                'timestamp': str     # 점검 시각
            }
        """
        try:
            excel_path = settings.excel_file_path
            
            # 파일이 없으면 디렉토리 쓰기 권한 확인
            if not excel_path.exists():
                # 임시 파일 생성 테스트
                test_path = excel_path.parent / '.test_write_permission'
                
                try:
                    test_path.touch()
                    test_path.unlink()
                    
                    logger.debug("Excel 디렉토리 쓰기 가능")
                    return {
                        'status': True,
                        'message': '디렉토리 쓰기 가능',
                        'timestamp': datetime.now().isoformat()
                    }
                except Exception as e:
                    logger.warning(f"Excel 디렉토리 쓰기 불가: {e}")
                    return {
                        'status': False,
                        'message': f'디렉토리 쓰기 불가: {str(e)}',
                        'timestamp': datetime.now().isoformat()
                    }
            
            # 파일이 있으면 쓰기 권한 확인
            import os
            is_writable = os.access(excel_path, os.W_OK)
            
            result = {
                'status': is_writable,
                'message': '쓰기 가능' if is_writable else '쓰기 불가능 (읽기 전용)',
                'timestamp': datetime.now().isoformat()
            }
            
            if is_writable:
                logger.debug("Excel 파일 쓰기 가능")
            else:
                logger.warning("Excel 파일 쓰기 불가 (읽기 전용)")
            
            return result
            
        except Exception as e:
            logger.error(f"Excel 권한 점검 오류: {e}")
            return {
                'status': False,
                'message': f'오류: {str(e)}',
                'timestamp': datetime.now().isoformat()
            }
    
    def run_all_checks(self) -> Dict:
        """모든 헬스 체크 실행
        
        모든 점검 항목을 실행하고 전체 상태를 판정합니다.
        
        Returns:
            {
                'overall_status': bool,      # 전체 통과 여부
                'checks': {...},             # 개별 점검 결과
                'timestamp': str,            # 점검 시각
                'summary': str,              # 요약 메시지
                'failed_count': int          # 실패 항목 수
            }
        """
        logger.info("🔍 시스템 헬스 체크 시작...")
        
        # 각 점검 실행
        checks = {
            'portal': self.check_portal_connectivity(),
            'google_sheets': self.check_google_sheets_connection(),
            'disk_space': self.check_disk_space(),
            'excel_permission': self.check_excel_write_permission()
        }
        
        # 전체 상태 판정 (모든 항목이 통과해야 함)
        all_passed = all(check['status'] for check in checks.values())
        
        # 실패한 항목 수집
        failed_checks = [
            name for name, result in checks.items()
            if not result['status']
        ]
        
        # 요약 메시지
        if all_passed:
            summary = "✅ 모든 점검 통과"
        else:
            summary = f"⚠️ {len(failed_checks)}개 항목 실패: {', '.join(failed_checks)}"
        
        result = {
            'overall_status': all_passed,
            'checks': checks,
            'timestamp': datetime.now().isoformat(),
            'summary': summary,
            'failed_count': len(failed_checks)
        }
        
        self.last_check_time = datetime.now()
        
        # 로깅
        for name, check_result in checks.items():
            status_icon = "✅" if check_result['status'] else "❌"
            logger.info(f"  {status_icon} {name}: {check_result['message']}")
        
        logger.info(summary)
        
        return result
    
    def get_health_report(self) -> Dict:
        """상세 헬스 체크 리포트 생성
        
        헬스 체크 결과에 시스템 정보를 추가합니다.
        
        Returns:
            상세 리포트 딕셔너리
        """
        result = self.run_all_checks()
        
        # 시스템 정보 추가
        result['system_info'] = {
            'python_version': sys.version.split()[0],
            'platform': platform.platform(),
            'hostname': platform.node(),
            'processor': platform.processor()
        }
        
        return result


if __name__ == "__main__":
    # 간단한 테스트
    print("HealthChecker 테스트\n")
    
    # SSL 경고 억제
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    checker = HealthChecker()
    
    # 전체 헬스 체크
    result = checker.run_all_checks()
    
    print("\n=== 헬스 체크 결과 ===")
    print(f"전체 상태: {result['summary']}")
    print(f"실패 항목: {result['failed_count']}개")
    
    print("\n=== 개별 점검 ===")
    for name, check in result['checks'].items():
        status = "✅ 통과" if check['status'] else "❌ 실패"
        print(f"{name}: {status} - {check['message']}")
    
    # 상세 리포트
    print("\n=== 상세 리포트 ===")
    report = checker.get_health_report()
    print(f"시스템: {report['system_info']['platform']}")
    print(f"Python: {report['system_info']['python_version']}")
    
    print("\n✅ 테스트 완료")
