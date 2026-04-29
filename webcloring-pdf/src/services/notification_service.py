"""
알림 서비스 모듈

이메일을 통한 자동화 완료/실패 알림을 제공합니다.
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, List
from pathlib import Path

from config.settings import settings
from utils.logger import logger


class NotificationService:
    """알림 서비스 클래스
    
    SMTP를 통한 이메일 알림을 제공합니다.
    자동화 완료, 실패, 경고 등 다양한 알림을 지원합니다.
    
    Attributes:
        smtp_server (str): SMTP 서버 주소
        smtp_port (int): SMTP 포트
        sender_email (str): 발신자 이메일
        sender_password (str): 발신자 비밀번호
        recipient_emails (List[str]): 수신자 이메일 목록
        enabled (bool): 알림 활성화 여부
    """
    
    def __init__(self):
        """설정 파일에서 알림 설정 로드"""
        self.smtp_server = settings.get('notification.smtp_server', 'smtp.gmail.com')
        self.smtp_port = settings.get('notification.smtp_port', 587)
        self.sender_email = settings.get('notification.sender_email', '')
        self.sender_password = settings.get('notification.sender_password', '')
        self.recipient_emails = settings.get('notification.recipient_emails', [])
        self.enabled = settings.get('notification.enabled', False)
        
        self.notify_on_success = settings.get('notification.notify_on_success', True)
        self.notify_on_failure = settings.get('notification.notify_on_failure', True)
        self.min_failure_count = settings.get('notification.min_failure_count', 1)
        
        if self.enabled and not self.sender_email:
            logger.warning("알림이 활성화되었으나 발신자 이메일이 설정되지 않았습니다")
            self.enabled = False
        
        if self.enabled and not self.recipient_emails:
            logger.warning("알림이 활성화되었으나 수신자 이메일이 설정되지 않았습니다")
            self.enabled = False
        
        if self.enabled:
            logger.info(f"알림 서비스 활성화: {len(self.recipient_emails)}명의 수신자")
        else:
            logger.debug("알림 서비스 비활성화")
    
    def send_completion_email(self, metrics: Dict):
        """자동화 완료 이메일 발송
        
        Args:
            metrics: 실행 요약 통계
        """
        if not self.enabled:
            logger.debug("알림 비활성화 - 이메일 전송 건너뜀")
            return
        
        if not self.notify_on_success:
            logger.debug("성공 알림 비활성화")
            return
        
        # 성공률에 따라 제목 이모지 변경
        success_rate = metrics.get('success_rate', 0)
        if success_rate >= 95:
            emoji = "✅"
        elif success_rate >= 80:
            emoji = "⚠️"
        else:
            emoji = "❌"
        
        subject = f"{emoji} INTEROJO 자동화 완료 - {metrics['total_documents']}건 처리 (성공률 {success_rate}%)"
        
        body = self._create_completion_html(metrics)
        
        self._send_email(subject, body)
    
    def send_failure_email(self, error_message: str, metrics: Dict = None):
        """자동화 실패 이메일 발송
        
        Args:
            error_message: 오류 메시지
            metrics: 실행 통계 (선택)
        """
        if not self.enabled:
            return
        
        if not self.notify_on_failure:
            logger.debug("실패 알림 비활성화")
            return
        
        subject = "❌ INTEROJO 자동화 실패"
        
        body = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                .header {{ background-color: #f44336; color: white; padding: 20px; }}
                .content {{ padding: 20px; }}
                .error {{ background-color: #ffebee; padding: 10px; border-left: 4px solid #f44336; }}
                .stats {{ background-color: #f5f5f5; padding: 10px; margin-top: 20px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>⚠️ INTEROJO 포털 자동화 실패</h2>
            </div>
            
            <div class="content">
                <h3>오류 정보</h3>
                <div class="error">
                    <pre>{error_message}</pre>
                </div>
        """
        
        if metrics:
            body += f"""
                <div class="stats">
                    <h3>처리 통계</h3>
                    <ul>
                        <li>처리 시도: {metrics.get('total_documents', 0)}건</li>
                        <li>성공: {metrics.get('success_count', 0)}건</li>
                        <li>실패: {metrics.get('failed_count', 0)}건</li>
                    </ul>
                </div>
            """
        
        body += """
                <p><strong>조치 사항:</strong></p>
                <ol>
                    <li>로그 파일을 확인해 주세요</li>
                    <li>포털 접속 상태를 확인해 주세요</li>
                    <li>필요 시 수동으로 실행해 주세요</li>
                </ol>
            </div>
        </body>
        </html>
        """
        
        self._send_email(subject, body)
    
    def send_warning_email(self, title: str, message: str):
        """경고 이메일 발송
        
        Args:
            title: 경고 제목
            message: 경고 메시지
        """
        if not self.enabled:
            return
        
        subject = f"⚠️ INTEROJO 자동화 경고 - {title}"
        
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <div style="background-color: #ff9800; color: white; padding: 20px;">
                <h2>⚠️ 경고: {title}</h2>
            </div>
            
            <div style="padding: 20px;">
                <p>{message}</p>
                <p>시스템 상태를 확인해 주세요.</p>
            </div>
        </body>
        </html>
        """
        
        self._send_email(subject, body)
    
    def send_health_check_report(self, health_result: Dict):
        """헬스 체크 리포트 이메일
        
        Args:
            health_result: run_all_checks() 결과
        """
        if not self.enabled:
            return
        
        overall = health_result['overall_status']
        emoji = "✅" if overall else "⚠️"
        
        subject = f"{emoji} INTEROJO 시스템 헬스 체크"
        
        # HTML 테이블 생성
        check_rows = ""
        for name, check in health_result['checks'].items():
            status_icon = "✅" if check['status'] else "❌"
            check_rows += f"""
                <tr>
                    <td>{name}</td>
                    <td style="text-align: center;">{status_icon}</td>
                    <td>{check['message']}</td>
                </tr>
            """
        
        body = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .header {{ background-color: {'#4caf50' if overall else '#ff9800'}; color: white; padding: 20px; }}
                .content {{ padding: 20px; }}
                table {{ border-collapse: collapse; width: 100%; margin-top: 15px; }}
                th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>{emoji} 시스템 헬스 체크 결과</h2>
            </div>
            
            <div class="content">
                <p><strong>전체 상태:</strong> {health_result['summary']}</p>
                <p><strong>점검 시각:</strong> {health_result['timestamp']}</p>
                
                <h3>점검 항목</h3>
                <table>
                    <tr>
                        <th>항목</th>
                        <th style="text-align: center;">상태</th>
                        <th>메시지</th>
                    </tr>
                    {check_rows}
                </table>
                
                <p style="margin-top: 20px; color: #666;">
                    <small>정기적인 헬스 체크를 통해 시스템 상태를 확인하세요.</small>
                </p>
            </div>
        </body>
        </html>
        """
        
        self._send_email(subject, body)
    
    def _create_completion_html(self, metrics: Dict) -> str:
        """완료 이메일 HTML 생성
        
        Args:
            metrics: 실행 통계
            
        Returns:
            HTML 문자열
        """
        success_rate = metrics.get('success_rate', 0)
        
        # 성공률에 따른 색상
        if success_rate >= 95:
            color = "#4caf50"  # 녹색
        elif success_rate >= 80:
            color = "#ff9800"  # 주황색
        else:
            color = "#f44336"  # 빨강색
        
        duration_min = metrics.get('duration_seconds', 0) / 60
        
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                .header {{ background-color: {color}; color: white; padding: 20px; }}
                .content {{ padding: 20px; }}
                .stats-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; }}
                .stat-box {{ background-color: #f5f5f5; padding: 15px; border-radius: 5px; }}
                .stat-label {{ color: #666; font-size: 14px; }}
                .stat-value {{ font-size: 24px; font-weight: bold; color: #333; }}
                .progress-bar {{ background-color: #e0e0e0; height: 25px; border-radius: 5px; overflow: hidden; margin-top: 10px; }}
                .progress-fill {{ background-color: {color}; height: 100%; text-align: center; color: white; line-height: 25px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h2>✅ INTEROJO 포털 자동화 완료</h2>
                <p>실행 시간: {duration_min:.1f}분</p>
            </div>
            
            <div class="content">
                <h3>📊 처리 결과</h3>
                <div class="stats-grid">
                    <div class="stat-box">
                        <div class="stat-label">총 처리</div>
                        <div class="stat-value">{metrics['total_documents']}건</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-label">성공</div>
                        <div class="stat-value" style="color: #4caf50;">{metrics['success_count']}건</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-label">실패</div>
                        <div class="stat-value" style="color: #f44336;">{metrics['failed_count']}건</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-label">스킵</div>
                        <div class="stat-value" style="color: #ff9800;">{metrics['skipped_count']}건</div>
                    </div>
                </div>
                
                <h3>성공률</h3>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {success_rate}%;">{success_rate}%</div>
                </div>
                
                <h3>⏱️ 성능 지표</h3>
                <ul>
                    <li><strong>문서당 평균 처리 시간:</strong> {metrics.get('avg_processing_time', 0):.1f}초</li>
                    <li><strong>평균 PDF 생성 시간:</strong> {metrics.get('avg_pdf_time', 0):.2f}초</li>
                    <li><strong>평균 Excel 저장 시간:</strong> {metrics.get('avg_excel_time', 0):.2f}초</li>
                    <li><strong>평균 메모리 사용량:</strong> {metrics.get('avg_memory_mb', 0):.0f}MB</li>
                    <li><strong>최대 메모리 사용량:</strong> {metrics.get('peak_memory_mb', 0):.0f}MB</li>
                </ul>
                
                <p style="margin-top: 30px; color: #666;">
                    <small>상세 로그는 시스템의 로그 파일을 확인해 주세요.</small>
                </p>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def _send_email(self, subject: str, body: str):
        """실제 이메일 발송
        
        Args:
            subject: 이메일 제목
            body: 이메일 본문 (HTML)
        """
        try:
            message = MIMEMultipart('alternative')
            message['From'] = self.sender_email
            message['To'] = ', '.join(self.recipient_emails)
            message['Subject'] = subject
            
            # HTML 본문 추가
            html_part = MIMEText(body, 'html', 'utf-8')
            message.attach(html_part)
            
            # SMTP 연결 및 발송
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(message)
            
            logger.info(f"✉️ 이메일 발송 성공: {subject}")
            
        except smtplib.SMTPAuthenticationError:
            logger.error("❌ SMTP 인증 실패: 이메일/비밀번호를 확인하세요")
        except smtplib.SMTPException as e:
            logger.error(f"❌ SMTP 오류: {e}")
        except Exception as e:
            logger.error(f"❌ 이메일 발송 실패: {e}")
    
    def test_connection(self) -> bool:
        """SMTP 연결 테스트
        
        Returns:
            연결 성공 여부
        """
        if not self.enabled:
            logger.warning("알림이 비활성화되어 있습니다")
            return False
        
        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=10) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
            
            logger.info("✅ SMTP 연결 테스트 성공")
            return True
            
        except Exception as e:
            logger.error(f"❌ SMTP 연결 테스트 실패: {e}")
            return False


if __name__ == "__main__":
    # 간단한 테스트
    print("NotificationService 테스트\n")
    
    # 테스트용 메트릭
    test_metrics = {
        'total_documents': 50,
        'success_count': 48,
        'failed_count': 1,
        'skipped_count': 1,
        'success_rate': 96.0,
        'duration_seconds': 300,
        'avg_processing_time': 6.0,
        'avg_pdf_time': 0.5,
        'avg_excel_time': 0.3,
        'avg_memory_mb': 150,
        'peak_memory_mb': 200
    }
    
    service = NotificationService()
    
    if service.enabled:
        print("알림 서비스가 활성화되어 있습니다")
        print(f"수신자: {service.recipient_emails}")
        
        # 연결 테스트
        if service.test_connection():
            print("\n이메일 발송 테스트...")
            service.send_completion_email(test_metrics)
            print("완료 이메일 발송 완료")
    else:
        print("알림 서비스가 비활성화되어 있습니다")
        print("config.json에서 notification.enabled를 true로 설정하세요")
    
    print("\n✅ 테스트 완료")