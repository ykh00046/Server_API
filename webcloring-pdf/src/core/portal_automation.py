"""
INTEROJO 포털 자동화 핵심 모듈 (오케스트레이터)

서비스 클래스를 조합하여 전체 자동화 워크플로우를 제어합니다.
- BrowserManager: 웹드라이버 생명주기
- PortalNavigator: 포털 로그인·이동·검색·페이지네이션
- DocumentHandler: 문서 데이터 추출·PDF·Excel 처리
"""
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

from config.settings import settings
from utils.logger import logger
from utils.error_handler import log_execution_time, take_error_screenshot
from core.browser_manager import BrowserManager
from core.portal_navigator import PortalNavigator
from core.document_handler import DocumentHandler
from core.excel_manager import ExcelManager
from utils.processed_document_manager import ProcessedDocumentManager
from utils.metrics_collector import MetricsCollector
from services.notification_service import NotificationService
from services.health_checker import HealthChecker


class PortalAutomation:
    """INTEROJO 포털 자동화 오케스트레이터
    
    서비스 클래스를 조합하여 전체 자동화 워크플로우를 제어합니다.
    
    공개 API (하위 호환):
        - PortalAutomation()
        - .run_automation()
        - .setup_driver()
        - .login_to_portal()
        - .driver
    """
    
    def __init__(self):
        # 공통 인프라
        self.browser = BrowserManager()
        self.excel_manager = ExcelManager()
        self.doc_manager = ProcessedDocumentManager()
        self.metrics = MetricsCollector()
        self.notification = NotificationService()
        self.health_checker = HealthChecker()
        
        # driver 의존 서비스 (setup_driver 이후 초기화)
        self.navigator = None
        self.handler = None
    
    @property
    def driver(self):
        """하위 호환: self.driver 접근"""
        return self.browser.driver
    
    @property
    def wait(self):
        """하위 호환: self.wait 접근"""
        return self.browser.wait
    
    def setup_driver(self):
        """하위 호환: 웹드라이버 초기화 후 서비스 생성"""
        result = self.browser.setup_driver()
        
        # driver가 준비되면 서비스 인스턴스 생성
        self.navigator = PortalNavigator(self.browser.driver, self.browser.wait)
        self.handler = DocumentHandler(
            self.browser.driver, self.browser.wait,
            self.excel_manager, self.doc_manager, self.metrics
        )
        return result
    
    def login_to_portal(self):
        """하위 호환: 포털 로그인"""
        return self.navigator.login_to_portal()
    
    def _get_dynamic_start_date(self) -> str:
        """동적 필터링 설정에 따른 검색 시작 날짜 반환"""
        try:
            if not settings.dynamic_filtering:
                start_date = settings.search_start_date
                logger.info(f"수동 필터링 모드: {start_date}")
                return start_date

            days_back = settings.days_back
            suggested_date = self.excel_manager.get_suggested_start_date(days_back)
            logger.info(f"스마트 필터링 모드: {suggested_date} (여분 {days_back}일)")
            return suggested_date

        except ValueError as e:
            logger.error(f"❌ 설정 오류: {e}")
            raise
        except Exception as e:
            logger.error(f"시작 날짜 계산 오류: {e}")
            return settings.search_start_date
    
    def process_document_list(self):
        """현재 페이지의 문서 목록을 순회하며 처리"""
        try:
            logger.info("문서 목록 처리 시작...")

            # iframe으로 전환 (문서 목록이 iframe 안에 있음)
            try:
                self.browser.driver.switch_to.default_content()
                self.browser.driver.switch_to.frame(0)
                logger.debug("✅ iframe으로 전환 완료")
            except Exception as e:
                logger.warning(f"iframe 전환 실패 (이미 iframe 안에 있을 수 있음): {e}")

            doc_list = self.navigator.collect_document_list()
            if not doc_list:
                return True

            for i, doc_info in enumerate(doc_list):
                try:
                    logger.info(f"문서 {i + 1}/{len(doc_list)} 처리 중: {doc_info['title']}")

                    # 문서 링크 클릭 - JavaScript 직접 호출 방식 (안정적)
                    try:
                        logger.debug(f"📄 문서 열기: ID={doc_info['id']}")
                        self.browser.driver.execute_script(
                            f"getApprDetail('{doc_info['id']}','','')"
                        )
                        time.sleep(2)
                    except Exception as js_error:
                        # JavaScript 실패 시 XPath fallback
                        logger.warning(f"⚠️ JavaScript 호출 실패, XPath 방식 시도: {js_error}")
                        try:
                            link_xpath = f"//a[contains(@onclick, \"getApprDetail('{doc_info['id']}')\")]"
                            doc_link = self.browser.wait.until(
                                EC.element_to_be_clickable((By.XPATH, link_xpath)),
                                message=f"문서 링크를 찾을 수 없음: {doc_info['id']}"
                            )
                            self.browser.driver.execute_script("arguments[0].click();", doc_link)
                            time.sleep(1)
                        except Exception as xpath_error:
                            logger.error(f"❌ XPath 방식도 실패: {xpath_error}")
                            raise

                    # 문서 처리 (DocumentHandler에 위임)
                    self.handler.process_document(doc_info)

                    # 목록으로 복귀
                    self._return_to_list()

                except Exception as e:
                    logger.error(f"개별 문서 처리 실패: {doc_info['title']} - {e}")
                    take_error_screenshot(
                        self.browser.driver,
                        f"doc_fail_{doc_info.get('id', 'unknown')}"
                    )
                    # 목록으로 복귀 시도
                    try:
                        logger.warning("목록으로 복귀 시도 중...")
                        self.browser.driver.back()
                        time.sleep(2)
                        # iframe으로 다시 전환
                        self.browser.driver.switch_to.default_content()
                        self.browser.driver.switch_to.frame(0)
                        self.browser.wait.until(
                            EC.presence_of_element_located((By.ID, "listTable"))
                        )
                        logger.info("✅ 목록으로 복귀 성공, 다음 문서 계속 처리")
                    except:
                        logger.error("목록 복귀 실패, 다음 문서로 건너뜀")
                        continue
            return True
        except Exception as e:
            logger.error(f"문서 목록 처리 실패: {e}")
            return False
    
    def _return_to_list(self):
        """문서 상세 → 목록 페이지 복귀"""
        logger.info("📋 목록 페이지로 복귀 중...")
        try:
            # 먼저 default_content로 전환 후 iframe 진입
            self.browser.driver.switch_to.default_content()
            self.browser.driver.switch_to.frame(0)
            self.browser.driver.find_element(By.ID, "listTable")
            logger.info("✅ 이미 목록 페이지에 있음")
        except:
            logger.info("🔙 뒤로가기 실행")
            self.browser.driver.back()
            time.sleep(2)
            # 확실히 iframe으로 전환
            self.browser.driver.switch_to.default_content()
            self.browser.driver.switch_to.frame(0)
            self.browser.wait.until(
                EC.presence_of_element_located((By.ID, "listTable"))
            )
            logger.info("✅ 목록 페이지 복귀 완료")
    
    @log_execution_time
    def run_automation(self):
        """전체 자동화 워크플로우 실행"""
        try:
            # 헬스 체크
            logger.info("=" * 60)
            health_result = self.health_checker.run_all_checks()
            logger.info("=" * 60)
            
            if not health_result['overall_status']:
                self.notification.send_warning_email(
                    "헬스 체크 실패", health_result['summary']
                )
                if not health_result['checks']['portal']['status']:
                    logger.error("❌ 포털 접속 불가능 - 자동화 중단")
                    self.notification.send_failure_email(
                        "포털 접속 불가능으로 자동화 중단", health_result
                    )
                    return False
                logger.warning("⚠️ 일부 헬스 체크 실패 - 주의하며 계속 진행")
            
            # 메트릭 수집 시작
            self.metrics.start_run()
            
            # 초기화 → 로그인 → 네비게이션 → 검색
            logger.info("INTEROJO 포털 자동화 시작")
            if not self.setup_driver():
                return False
            if not self.navigator.login_to_portal():
                return False
            if not self.navigator.navigate_to_electronic_approval():
                return False
            if not self.navigator.navigate_to_completed_documents():
                return False
            
            start_date = self._get_dynamic_start_date()
            if not self.navigator.search_documents(start_date):
                return False
            self.navigator.change_page_size()

            # ===== 페이지 순회 루프 =====
            page_count = 0

            while True:
                page_count += 1
                current_page = self.navigator.get_current_page_number()

                logger.info(f"{'=' * 60}")
                logger.info(f"📄 {current_page}페이지 처리 시작 (누적 {page_count}페이지)")
                logger.info(f"{'=' * 60}")

                success = self.process_document_list()
                if not success:
                    logger.error(f"❌ {current_page}페이지 처리 실패, 중단")
                    return False

                logger.info(f"✅ {current_page}페이지 처리 완료")

                if not self.navigator.has_next_page():
                    logger.info("🏁 마지막 페이지 도달, 작업 완료")
                    break

                if not self.navigator.move_to_next_page():
                    logger.error("❌ 페이지 이동 실패, 중단")
                    return False

                time.sleep(1)

            # ===== 완료 =====
            logger.info(f"{'=' * 60}")
            logger.info(f"🎉 전체 작업 완료: 총 {page_count}페이지 처리")
            logger.info(f"{'=' * 60}")
            
            self.metrics.end_run()
            summary = self.metrics.get_summary()
            self.notification.send_completion_email(summary)
            
            return True
            
        except Exception as e:
            logger.error(f"자동화 프로세스 실패: {e}")
            take_error_screenshot(self.browser.driver, "automation_failure")
            
            self.metrics.end_run()
            summary = self.metrics.get_summary()
            self.notification.send_failure_email(str(e), summary)
            
            return False
            
        finally:
            # Google Sheets 백업
            try:
                if self.excel_manager:
                    logger.info("📤 자동화 종료 - Google Sheets 백업 시작...")
                    self.excel_manager.finalize_google_backup()
            except Exception as e:
                logger.warning(
                    f"Google Sheets 백업 실패 (Excel 데이터는 정상 저장됨): {e}"
                )
            
            # 브라우저 종료
            self.browser.close_driver()
