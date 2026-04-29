"""
브라우저 관리 모듈

Chrome WebDriver의 생명주기(초기화, 설정, 종료)를 관리합니다.
"""
import sys

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from config.settings import settings
from utils.logger import logger
from utils.exceptions import AutomationError


class BrowserManager:
    """Chrome WebDriver 생명주기 관리 클래스
    
    WebDriver의 초기화, 설정, 종료를 담당합니다.
    
    Attributes:
        driver: Chrome WebDriver 인스턴스
        wait: WebDriverWait 인스턴스
    """
    
    def __init__(self):
        self.driver = None
        self.wait = None
    
    def setup_driver(self):
        """웹드라이버 초기화 및 기본 설정
        
        Returns:
            bool: 성공 시 True
            
        Raises:
            AutomationError: 웹드라이버 초기화 실패 시
        """
        try:
            # webdriver_manager 사용 (개발/실행 파일 모두 지원)
            service = Service(ChromeDriverManager().install())

            if getattr(sys, 'frozen', False):
                logger.info("실행 파일 모드: ChromeDriverManager로 자동 다운로드")
            else:
                logger.info("개발 모드: ChromeDriverManager 사용")

            options = webdriver.ChromeOptions()

            options.add_argument("--window-size=1920,1080")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-extensions")
            
            if settings.headless_mode:
                options.add_argument("--headless")
            
            pdf_settings = {
                "printing.print_preview_sticky_settings.appState": '{"recentDestinations":[{"id":"Save as PDF","origin":"local","account":""}],"selectedDestinationId":"Save as PDF","version":2}',
                "savefile.default_directory": str(settings.pdf_directory.absolute())
            }
            options.add_experimental_option("prefs", pdf_settings)

            if settings.debug_mode:
                options.add_experimental_option("detach", True)

            self.driver = webdriver.Chrome(service=service, options=options)
            self.wait = WebDriverWait(self.driver, 10)
            self.driver.maximize_window()
            logger.info("웹드라이버 초기화 완료")
            return True

        except Exception as e:
            logger.error(f"웹드라이버 초기화 실패: {e}")
            raise AutomationError(f"웹드라이버 초기화 실패: {e}")
    
    def close_driver(self):
        """브라우저 종료
        
        debug_mode가 활성화된 경우 브라우저를 유지합니다.
        """
        if self.driver and not settings.debug_mode:
            self.driver.quit()
            logger.info("브라우저 종료")
        else:
            logger.info("디버그 모드: 브라우저 유지")
