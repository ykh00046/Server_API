"""
포털 네비게이션 모듈

INTEROJO 포털의 로그인, 메뉴 이동, 문서 검색, 페이지네이션을 담당합니다.
"""
import re
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from config.settings import settings
from utils.logger import logger
from utils.error_handler import (
    retry_on_failure, handle_selenium_errors,
    handle_login_errors, handle_navigation_errors,
    take_error_screenshot
)
from utils.exceptions import LoginError, NavigationError
from utils.retry_decorator import retry


class PortalNavigator:
    """포털 네비게이션 클래스
    
    로그인, 메뉴 이동, 문서 검색, 페이지네이션 기능을 제공합니다.
    
    Args:
        driver: Chrome WebDriver 인스턴스
        wait: WebDriverWait 인스턴스
    """
    
    def __init__(self, driver, wait):
        self.driver = driver
        self.wait = wait
    
    @handle_login_errors("INTEROJO 포털")
    @retry(max_attempts=3, delay=2.0, exceptions=(TimeoutException, LoginError))
    def login_to_portal(self):
        """INTEROJO 포털 로그인"""
        try:
            logger.info("포털 페이지 접속 중...")
            self.driver.get(settings.portal_url)
            username_field = self.wait.until(EC.presence_of_element_located((By.XPATH, "//*[@title='ID']")))
            username_field.send_keys(settings.portal_username)
            password_field = self.driver.find_element(By.XPATH, "//*[@title='Password']")
            password_field.send_keys(settings.portal_password)

            # 로그인 버튼 직접 클릭 (submit() 대신)
            time.sleep(0.5)  # 입력 완료 대기
            try:
                # 방법 1: 로그인 버튼 찾아서 클릭
                login_btn = self.driver.find_element(By.XPATH, "//input[@type='image' or @type='submit' or contains(@class, 'login')]")
                login_btn.click()
                logger.info("로그인 버튼 클릭")
            except NoSuchElementException:
                # 방법 2: Enter 키로 submit
                password_field.send_keys(Keys.RETURN)
                logger.info("Enter 키로 로그인")

            time.sleep(2)  # 로그인 처리 대기

            try:
                self.wait.until(EC.url_contains("main"))
                logger.info("포털 로그인 성공 (URL 변경 확인)")
                return True
            except TimeoutException:
                try:
                    self.wait.until(EC.presence_of_element_located((By.ID, "gnbWrap")))
                    logger.info("포털 로그인 성공 (메인 페이지 요소 확인)")
                    return True
                except TimeoutException:
                    # 추가: 로그인 실패 알림 체크
                    try:
                        alert = self.driver.switch_to.alert
                        alert_text = alert.text
                        alert.accept()
                        raise LoginError("INTEROJO 포털", f"로그인 실패: {alert_text}")
                    except:
                        raise LoginError("INTEROJO 포털", "로그인 실패 - 예상된 메인 페이지로 이동하지 않음")
        except TimeoutException as e:
            take_error_screenshot(self.driver, "login_timeout")
            raise LoginError("INTEROJO 포털", f"로그인 타임아웃: {e}")

    @handle_navigation_errors("전자결재")
    @retry_on_failure(max_attempts=2, delay=1.0)
    def navigate_to_electronic_approval(self):
        """전자결재 메뉴로 이동"""
        try:
            logger.info("전자결재 메뉴 탐색 중...")
            elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), '전자결재')]/parent::a")
            if not elements:
                text_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), '전자결재')]" )
                for elem in text_elements:
                    try:
                        parent = elem.find_element(By.XPATH, "..")
                        if parent.tag_name == 'a':
                            elements = [parent]
                            break
                    except: continue
            if not elements: raise NavigationError("전자결재", "전자결재 메뉴를 찾을 수 없습니다")
            approval_menu = elements[0]
            href = approval_menu.get_attribute('href')
            logger.info("전자결재 페이지로 이동 중...")
            self.driver.get(href)
            try:
                self.wait.until(EC.url_contains("approval"))
                self.wait.until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(), '결재대기') or contains(text(), '결재진행')]" )))
                logger.info("전자결재 페이지 이동 성공")
                return True
            except TimeoutException:
                raise NavigationError("전자결재", "전자결재 페이지 로딩 실패")
        except Exception as e:
            take_error_screenshot(self.driver, "electronic_approval_nav")
            raise

    @handle_navigation_errors("완료문서함")
    @retry_on_failure(max_attempts=2, delay=1.0)
    def navigate_to_completed_documents(self):
        """완료문서함 메뉴로 이동"""
        try:
            logger.info("완료문서함 메뉴 탐색 중...")
            elements = self.driver.find_elements(By.XPATH, "//a[contains(text(), '완료문서함')]" )
            if not elements:
                text_elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), '완료문서함')]" )
                for elem in text_elements:
                    if elem.tag_name == 'a':
                        elements = [elem]
                        break
                    try:
                        parent = elem.find_element(By.XPATH, "..")
                        if parent.tag_name == 'a':
                            elements = [parent]
                            break
                    except: continue
            if not elements: raise NavigationError("완료문서함", "완료문서함 메뉴를 찾을 수 없습니다")
            completed_menu = elements[0]
            href = completed_menu.get_attribute('href')
            if href and href.startswith('javascript:'):
                logger.info("완료문서함 클릭 중...")
                self.driver.execute_script("arguments[0].click();", completed_menu)
                try:
                    self.wait.until(EC.presence_of_element_located((By.ID, "searchFormName")))
                    logger.info("완료문서함 페이지 이동 성공 (JS 클릭)")
                except TimeoutException:
                    logger.warning("완료문서함 클릭 완료 (JS 클릭, 요소 확인 실패)")
            else:
                logger.info("완료문서함 클릭 중 (href 없음)...")
                self.driver.execute_script("arguments[0].click();", completed_menu)
                try:
                    self.wait.until(EC.presence_of_element_located((By.ID, "searchFormName")))
                    logger.info("완료문서함 클릭 완료 (일반 클릭)")
                except TimeoutException:
                    raise NavigationError("완료문서함", "완료문서함 페이지 로딩 실패")
            return True
        except Exception as e:
            take_error_screenshot(self.driver, "completed_documents_nav")
            raise

    @handle_selenium_errors(default_return=False, log_error=True, screenshot_on_error=True)
    def search_documents(self, start_date, keyword=None):
        """문서 검색
        
        Args:
            start_date: 검색 시작 날짜 (YYYY.MM.DD)
            keyword: 검색 키워드 (None이면 settings에서 가져옴)
        """
        try:
            logger.info("문서 검색 시작...")
            try:
                self.driver.switch_to.frame(0)
                self.wait.until(EC.presence_of_element_located((By.ID, "searchFormName")))
                logger.info("iframe으로 전환하여 검색폼 발견")
            except Exception:
                self.driver.switch_to.default_content()
                logger.info("iframe 전환 없이 메인 프레임에서 검색 시작")

            form_name_input = self.wait.until(EC.presence_of_element_located((By.ID, "searchFormName")))
            form_name_input.clear()

            # 동적 키워드 사용
            if keyword is None:
                keyword = settings.search_keyword
            form_name_input.send_keys(keyword)
            logger.info(f"검색 키워드: '{keyword}'")

            start_date_input = self.wait.until(EC.presence_of_element_located((By.ID, "searchStartDate")))
            self.driver.execute_script(f"arguments[0].removeAttribute('readonly'); arguments[0].value = '{start_date}';", start_date_input)
            logger.info(f"시작일을 {start_date}로 설정 완료")

            form_name_input.send_keys(Keys.RETURN)
            logger.info("Enter 키로 검색 실행")

            self.wait.until(EC.presence_of_element_located((By.ID, "listTable")))
            logger.info("문서 검색 완료 및 결과 테이블 로딩 확인")
            return True
        except Exception as e:
            logger.error(f"문서 검색 실패: {e}")
            raise

    @handle_selenium_errors(default_return=False, log_error=True)
    def change_page_size(self):
        """페이지당 글 수를 50개로 변경"""
        try:
            logger.info("페이지당 글 수 변경 시작...")

            # 페이지 크기 관련 select 요소 찾기
            all_selects = self.driver.find_elements(By.TAG_NAME, "select")

            # pagePerRecord 요소 존재 여부 확인 (문서가 0개면 없을 수 있음)
            page_size_select = None

            # 1차: name='pagePerRecord'로 찾기
            try:
                page_size_select = self.driver.find_element(By.NAME, "pagePerRecord")
                logger.info("✅ name='pagePerRecord'로 찾음")
            except:
                logger.warning("⚠️ name='pagePerRecord' 요소를 찾을 수 없음, 다른 방법 시도...")

            # 2차: 10, 20, 50이 동시에 있는 select 찾기
            if not page_size_select:
                for sel in all_selects:
                    options = [opt.get_attribute('value') for opt in sel.find_elements(By.TAG_NAME, "option")]
                    # 10, 20, 50이 모두 있어야 페이지 크기 select
                    if '10' in options and '20' in options and '50' in options:
                        page_size_select = sel
                        logger.info(f"✅ 페이지 크기 select 발견 (10,20,50 확인): {options}")
                        break
                else:
                    logger.info("⚠️ 페이지 크기 선택 UI 없음")
                    return True

            current_value = page_size_select.get_attribute('value')
            logger.info(f"현재 페이지 크기: {current_value}")

            if current_value == '50':
                logger.info("페이지 크기가 이미 10입니다.")
                return True

            Select(page_size_select).select_by_value('50')
            time.sleep(2)  # 페이지 리로드 대기
            logger.info("✅ 페이지 크기 변경 완료 (50개로 설정)")
            return True

        except Exception as e:
            logger.error(f"페이지당 글 수 변경 실패: {e}")
            return False

    def collect_document_list(self):
        """문서 목록 수집
        
        Returns:
            list: 문서 정보 리스트 [{'title': str, 'id': str}, ...]
        """
        try:
            logger.info("문서 목록 수집 시작...")
            self.wait.until(EC.presence_of_element_located((By.ID, "listTable")))

            # JavaScript가 테이블 데이터를 로드할 시간 대기
            logger.info("⏳ JavaScript 데이터 로딩 대기 중...")
            time.sleep(3)  # 3초 대기

            # "검색 결과가 존재하지 않습니다." 체크
            if "검색 결과가 존재하지 않습니다." in self.driver.page_source:
                logger.info("⚠️ 검색 결과가 존재하지 않습니다 (페이지 소스에서 발견)")
                return []

            # listTable 안의 tbody/tr만 선택 (datepicker 등 다른 테이블 제외)
            document_rows = self.driver.find_elements(By.XPATH, "//table[@id='listTable']//tbody/tr")
            logger.info(f"📊 발견된 행(row) 수: {len(document_rows)}")

            document_list = []
            for idx, row in enumerate(document_rows, 1):
                try:
                    # td[4] 안의 모든 하위 <a> 태그 찾기 (//a 사용)
                    title_cell = row.find_element(By.XPATH, ".//td[4]//a")
                    doc_title = title_cell.text.strip()
                    href = title_cell.get_attribute('href')
                    onclick = title_cell.get_attribute('onclick')

                    # onclick에서 문서 ID 추출: getApprDetail('101262382213','','')
                    doc_id_match = re.search(r"getApprDetail\('(\d+)'", onclick if onclick else href)

                    if doc_title and doc_id_match:
                        document_list.append({'title': doc_title, 'id': doc_id_match.group(1)})
                        if idx <= 5:  # 처음 5개만 로그 출력
                            logger.info(f"✅ 문서 {idx}: {doc_title} (ID: {doc_id_match.group(1)})")
                    else:
                        if idx <= 3:
                            logger.warning(f"⚠️ 행 {idx}: 제목 또는 ID 없음")
                except NoSuchElementException:
                    if idx <= 3:
                        logger.debug(f"행 {idx}: td[4]//a 없음 (헤더 또는 빈 행)")
                    continue
            logger.info(f"총 {len(document_list)}개의 문서 정보 수집 완료")
            return document_list
        except Exception as e:
            logger.error(f"문서 목록 수집 실패: {e}")
            return []

    # ===== 페이지네이션 =====

    def get_current_page_number(self) -> int:
        """현재 활성화된 페이지 번호를 반환합니다.
        
        Returns:
            int: 현재 페이지 번호, 실패 시 1 반환
        """
        try:
            # iframe 컨텍스트 확인
            try:
                self.driver.find_element(By.ID, "listTable")
            except NoSuchElementException:
                logger.debug("listTable 없음, iframe 전환 시도")
                self.driver.switch_to.default_content()
                self.driver.switch_to.frame(0)

            current_page_xpath = "//div[contains(@class, 'paging')]//a[contains(@class, 'fColor')]"
            current_page_elem = self.driver.find_element(By.XPATH, current_page_xpath)
            page_number = int(current_page_elem.text.strip())

            logger.debug(f"📄 현재 페이지: {page_number}")
            return page_number

        except NoSuchElementException:
            logger.warning("페이지네이션 요소를 찾을 수 없음, 기본값 1 반환")
            return 1
        except ValueError as e:
            logger.warning(f"페이지 번호 파싱 실패: {e}, 기본값 1 반환")
            return 1
        except Exception as e:
            logger.error(f"현재 페이지 번호 확인 중 오류: {e}, 기본값 1 반환")
            return 1

    def has_next_page(self) -> bool:
        """다음 페이지 존재 여부를 확인합니다.
        
        Returns:
            bool: 다음 페이지가 있으면 True
        """
        try:
            current_page = self.get_current_page_number()
            next_page = current_page + 1

            logger.debug(f"다음 페이지({next_page}) 존재 여부 확인 중...")

            # iframe 컨텍스트 확인
            try:
                self.driver.find_element(By.ID, "listTable")
            except NoSuchElementException:
                self.driver.switch_to.default_content()
                self.driver.switch_to.frame(0)

            # 방법 1: 다음 페이지 번호 버튼이 있는지 확인
            next_page_xpath = f"//div[contains(@class, 'paging')]//a[@class='page' and text()='{next_page}']"
            next_page_elems = self.driver.find_elements(By.XPATH, next_page_xpath)

            if next_page_elems:
                logger.info(f"✅ 다음 페이지({next_page}) 버튼 발견")
                return True

            # 방법 2: "다음 10페이지" 버튼이 활성화되어 있는지 확인
            next_group_xpath = "//div[contains(@class, 'paging')]//a[contains(@class, 'btn') and contains(@class, 'next') and not(contains(@class, 'disabled'))]"
            next_group_elems = self.driver.find_elements(By.XPATH, next_group_xpath)

            if next_group_elems:
                logger.info("✅ '다음 10페이지' 버튼 활성화됨")
                return True

            logger.info("🏁 더 이상 페이지 없음 (마지막 페이지 도달)")
            return False

        except Exception as e:
            logger.error(f"다음 페이지 확인 중 오류: {e}")
            return False

    def move_to_next_page(self) -> bool:
        """다음 페이지로 이동합니다.
        
        Returns:
            bool: 이동 성공 시 True
        """
        try:
            current_page = self.get_current_page_number()
            next_page = current_page + 1

            logger.info(f"➡️  {next_page}페이지로 이동 시도...")

            # iframe 컨텍스트 확인
            try:
                old_table = self.driver.find_element(By.ID, "listTable")
            except NoSuchElementException:
                self.driver.switch_to.default_content()
                self.driver.switch_to.frame(0)
                old_table = self.driver.find_element(By.ID, "listTable")

            # 1. 다음 페이지 번호 버튼 찾기
            next_page_xpath = f"//div[contains(@class, 'paging')]//a[@class='page' and text()='{next_page}']"
            next_page_elems = self.driver.find_elements(By.XPATH, next_page_xpath)

            if next_page_elems:
                logger.debug(f"🖱️  {next_page}페이지 버튼 클릭 중...")
                self.driver.execute_script("arguments[0].click();", next_page_elems[0])

                # 페이지 전환 대기 - Staleness 체크
                try:
                    WebDriverWait(self.driver, 5).until(EC.staleness_of(old_table))
                    logger.debug("⏳ 기존 테이블 갱신 감지")
                except TimeoutException:
                    logger.warning("⚠️  Staleness 타임아웃, 고정 대기로 대체")

                time.sleep(2)
                self.wait.until(EC.presence_of_element_located((By.ID, "listTable")))
                time.sleep(1)

                logger.info(f"✅ {next_page}페이지 로딩 완료")
                return True

            # 2. 숫자 버튼이 없으면 "다음 10페이지" 버튼 클릭
            logger.debug("숫자 버튼 없음, '다음 10페이지' 버튼 탐색...")
            next_group_xpath = "//div[contains(@class, 'paging')]//a[contains(@class, 'btn') and contains(@class, 'next') and not(contains(@class, 'disabled'))]"
            next_group_elems = self.driver.find_elements(By.XPATH, next_group_xpath)

            if next_group_elems:
                logger.info("➡️  '다음 10페이지' 버튼 클릭...")
                self.driver.execute_script("arguments[0].click();", next_group_elems[0])

                time.sleep(3)
                self.wait.until(EC.presence_of_element_located((By.ID, "listTable")))
                time.sleep(1)

                logger.info("✅ 다음 페이지 그룹 로딩 완료")
                return True

            logger.info("🏁 더 이상 이동할 페이지 없음")
            return False

        except Exception as e:
            logger.error(f"페이지 이동 실패: {e}")
            take_error_screenshot(self.driver, "page_move_failure")
            return False
