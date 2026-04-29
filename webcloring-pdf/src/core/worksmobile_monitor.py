"""
WorksMobile 메신저 모니터링 클래스
전자결재 알림 봇을 모니터링하여 신규 자재 요청을 감지합니다.
"""
import time
import re
from typing import List, Dict, Optional
from datetime import datetime, timedelta

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from config.settings import settings
from utils.logger import logger


class WorksMobileMonitor:
    """WorksMobile 메신저 모니터링 클래스"""
    
    def __init__(self):
        self.driver = None
        self.wait = None
        self.detected_messages = []
    
    def setup_driver(self):
        """Chrome 드라이버 설정"""
        try:
            chrome_options = Options()
            
            # 기본 옵션 설정
            for option in settings.get("selenium.chrome_options", []):
                chrome_options.add_argument(option)
            
            # 윈도우 크기
            window_size = settings.get("selenium.window_size", [1920, 1080])
            chrome_options.add_argument(f"--window-size={window_size[0]},{window_size[1]}")
            
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.implicitly_wait(settings.implicit_wait)
            self.wait = WebDriverWait(self.driver, settings.page_load_timeout)
            
            logger.info("WorksMobile 모니터링용 드라이버 설정 완료")
            return True
            
        except Exception as e:
            logger.error(f"드라이버 설정 실패: {e}")
            return False
    
    def login(self) -> bool:
        """WorksMobile 로그인"""
        try:
            logger.login_attempt(settings.worksmobile_username, "WorksMobile")
            
            self.driver.get(settings.worksmobile_url)
            logger.step("WorksMobile 접속", settings.worksmobile_url)
            
            # 로그인 페이지 대기
            time.sleep(3)
            
            # 이메일 입력
            email_selectors = [
                "input[name='userEmail']",
                "input[id='loginEmail']",
                "input[type='email']",
                ".login-email"
            ]
            
            email_input = self._find_element_by_selectors(email_selectors)
            if not email_input:
                raise Exception("이메일 입력 필드를 찾을 수 없습니다")
            
            email_input.clear()
            email_input.send_keys(settings.worksmobile_username)
            time.sleep(settings.click_delay)
            
            # 패스워드 입력
            password_selectors = [
                "input[name='userPw']",
                "input[id='loginPw']",
                "input[type='password']",
                ".login-password"
            ]
            
            password_input = self._find_element_by_selectors(password_selectors)
            if not password_input:
                raise Exception("패스워드 입력 필드를 찾을 수 없습니다")
            
            password_input.clear()
            password_input.send_keys(settings.worksmobile_password)
            time.sleep(settings.click_delay)
            
            # 로그인 버튼 클릭
            login_selectors = [
                "button[type='submit']",
                "input[type='submit']",
                ".login-btn",
                "button:contains('로그인')"
            ]
            
            login_button = self._find_element_by_selectors(login_selectors)
            if login_button:
                login_button.click()
            else:
                password_input.send_keys("\n")
            
            # 로그인 성공 대기
            time.sleep(5)
            
            # 메인 페이지 확인
            if "talk.worksmobile.com" in self.driver.current_url:
                logger.login_success("WorksMobile")
                return True
            else:
                raise Exception("로그인 후 페이지 확인 실패")
                
        except Exception as e:
            logger.login_failed("WorksMobile", str(e))
            return False
    
    def navigate_to_bot_chat(self) -> bool:
        """전자결재 봇 채팅방으로 이동"""
        try:
            logger.step("전자결재 봇 채팅방 이동")
            
            # 봇 검색 또는 직접 이동
            bot_selectors = [
                "a:contains('전자결재')",
                "a:contains('결재')",
                ".bot-chat",
                "[data-name*='전자결재']"
            ]
            
            for selector in bot_selectors:
                try:
                    if ":contains" in selector:
                        # XPath로 텍스트 검색
                        text = selector.split(":contains('")[1].rstrip("')")
                        elements = self.driver.find_elements(By.XPATH, f"//a[contains(text(), '{text}')]")
                        if elements:
                            elements[0].click()
                            break
                    else:
                        element = self.driver.find_element(By.CSS_SELECTOR, selector)
                        element.click()
                        break
                except NoSuchElementException:
                    continue
            
            time.sleep(3)
            logger.info("전자결재 봇 채팅방 이동 완료")
            return True
            
        except Exception as e:
            logger.error(f"봇 채팅방 이동 실패: {e}")
            return False
    
    def search_by_date(self, target_date: str) -> bool:
        """특정 날짜로 이동하여 메시지 검색"""
        try:
            logger.step("날짜별 메시지 검색", target_date)
            
            # 캘린더 버튼 찾기
            calendar_selectors = [
                ".calendar-btn",
                "button:contains('캘린더')",
                "[data-action='calendar']",
                ".date-picker"
            ]
            
            calendar_button = self._find_element_by_selectors(calendar_selectors)
            if calendar_button:
                calendar_button.click()
                time.sleep(2)
                
                # 날짜 입력 또는 선택
                date_input = self._find_element_by_selectors([
                    "input[type='date']",
                    ".date-input",
                    "input[name='date']"
                ])
                
                if date_input:
                    date_input.clear()
                    date_input.send_keys(target_date.replace('.', '-'))
                    time.sleep(1)
                    
                    # 확인 버튼
                    confirm_selectors = [
                        "button:contains('확인')",
                        "button:contains('이동')",
                        ".confirm-btn"
                    ]
                    
                    confirm_button = self._find_element_by_selectors(confirm_selectors)
                    if confirm_button:
                        confirm_button.click()
                        time.sleep(3)
            
            # 페이지 하단으로 스크롤하여 모든 메시지 로드
            self._scroll_to_load_messages()
            
            logger.info(f"{target_date} 날짜 검색 완료")
            return True
            
        except Exception as e:
            logger.error(f"날짜별 검색 실패: {e}")
            return False
    
    def _scroll_to_load_messages(self):
        """메시지 전체 로드를 위한 스크롤"""
        try:
            scroll_count = 0
            max_scrolls = 20
            
            while scroll_count < max_scrolls:
                # 현재 메시지 수 확인
                current_messages = len(self.driver.find_elements(By.CSS_SELECTOR, ".message, .chat-message"))
                
                # 페이지 상단으로 스크롤 (이전 메시지 로드)
                self.driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(settings.scroll_delay)
                
                # 메시지 수 변화 확인
                new_messages = len(self.driver.find_elements(By.CSS_SELECTOR, ".message, .chat-message"))
                
                if new_messages == current_messages:
                    break  # 더 이상 새 메시지가 없음
                
                scroll_count += 1
            
            # 마지막에 다시 하단으로 스크롤
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            
        except Exception as e:
            logger.warning(f"메시지 스크롤 중 오류: {e}")
    
    def monitor_messages(self, keywords: List[str] = None) -> List[Dict]:
        """키워드가 포함된 메시지 모니터링"""
        try:
            if keywords is None:
                keywords = settings.search_keywords
            
            logger.step("메시지 모니터링", f"키워드: {keywords}")
            
            detected_messages = []
            
            # 모든 메시지 요소 찾기
            message_selectors = [
                ".message",
                ".chat-message",
                ".message-content",
                ".msg-content"
            ]
            
            messages = []
            for selector in message_selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if elements:
                        messages = elements
                        break
                except NoSuchElementException:
                    continue
            
            # 메시지 내용 검사
            for message in messages:
                try:
                    message_text = message.text.strip()
                    
                    # 키워드 매칭 확인
                    if all(keyword in message_text for keyword in keywords):
                        logger.info(f"키워드 매칭 메시지 발견: {message_text[:50]}...")
                        
                        # Web 버튼 찾기
                        web_buttons = message.find_elements(By.XPATH, ".//button[contains(text(), 'Web')] | .//a[contains(text(), 'Web')]")
                        
                        message_info = {
                            'text': message_text,
                            'timestamp': self._extract_timestamp(message),
                            'has_web_button': len(web_buttons) > 0,
                            'web_button': web_buttons[0] if web_buttons else None
                        }
                        
                        detected_messages.append(message_info)
                
                except Exception as e:
                    logger.debug(f"메시지 처리 중 오류: {e}")
                    continue
            
            logger.data_extracted(len(detected_messages), "관련 메시지")
            return detected_messages
            
        except Exception as e:
            logger.error(f"메시지 모니터링 실패: {e}")
            return []
    
    def _extract_timestamp(self, message_element) -> Optional[str]:
        """메시지 타임스탬프 추출"""
        try:
            timestamp_selectors = [
                ".timestamp",
                ".time",
                ".message-time",
                ".msg-time"
            ]
            
            for selector in timestamp_selectors:
                try:
                    timestamp_element = message_element.find_element(By.CSS_SELECTOR, selector)
                    return timestamp_element.text.strip()
                except NoSuchElementException:
                    continue
            
            return None
            
        except Exception:
            return None
    
    def click_web_buttons(self, messages: List[Dict]) -> List[str]:
        """Web 버튼 클릭하여 상세 정보 수집"""
        try:
            clicked_urls = []
            
            for message in messages:
                if message.get('has_web_button') and message.get('web_button'):
                    try:
                        web_button = message['web_button']
                        
                        # 버튼 클릭
                        web_button.click()
                        time.sleep(2)
                        
                        # 새 창/탭 처리
                        if len(self.driver.window_handles) > 1:
                            # 새 창으로 전환
                            self.driver.switch_to.window(self.driver.window_handles[-1])
                            
                            # URL 수집
                            current_url = self.driver.current_url
                            clicked_urls.append(current_url)
                            
                            logger.info(f"Web 버튼 클릭: {current_url}")
                            
                            # 창 닫기
                            self.driver.close()
                            
                            # 원래 창으로 복귀
                            self.driver.switch_to.window(self.driver.window_handles[0])
                        
                        time.sleep(settings.click_delay)
                        
                    except Exception as e:
                        logger.warning(f"Web 버튼 클릭 실패: {e}")
                        continue
            
            return clicked_urls
            
        except Exception as e:
            logger.error(f"Web 버튼 처리 실패: {e}")
            return []
    
    def _find_element_by_selectors(self, selectors: List[str]):
        """여러 선택자로 요소 찾기"""
        for selector in selectors:
            try:
                if ":contains" in selector:
                    # XPath로 변환
                    text = selector.split(":contains('")[1].rstrip("')")
                    return self.driver.find_element(By.XPATH, f"//*[contains(text(), '{text}')]")
                else:
                    return self.driver.find_element(By.CSS_SELECTOR, selector)
            except NoSuchElementException:
                continue
        return None
    
    def cleanup(self):
        """리소스 정리"""
        try:
            if self.driver:
                self.driver.quit()
                logger.info("WorksMobile 모니터링 드라이버 종료")
        except Exception as e:
            logger.error(f"드라이버 종료 실패: {e}")
    
    def run_monitoring(self, target_date: str = None) -> List[Dict]:
        """전체 모니터링 프로세스 실행"""
        try:
            logger.automation_start("WorksMobile 메시지 모니터링")
            
            # 날짜 설정 (기본값: 오늘)
            if not target_date:
                target_date = datetime.now().strftime("%Y.%m.%d")
            
            # 1. 드라이버 설정
            if not self.setup_driver():
                return []
            
            # 2. 로그인
            if not self.login():
                return []
            
            # 3. 봇 채팅방 이동
            if not self.navigate_to_bot_chat():
                return []
            
            # 4. 날짜별 검색
            if not self.search_by_date(target_date):
                return []
            
            # 5. 메시지 모니터링
            detected_messages = self.monitor_messages()
            
            # 6. Web 버튼 클릭
            if detected_messages:
                urls = self.click_web_buttons(detected_messages)
                logger.info(f"수집된 URL: {len(urls)}개")
            
            logger.automation_end("WorksMobile 메시지 모니터링", True)
            return detected_messages
            
        except Exception as e:
            logger.error(f"모니터링 프로세스 실패: {e}")
            logger.automation_end("WorksMobile 메시지 모니터링", False)
            return []
        finally:
            self.cleanup()