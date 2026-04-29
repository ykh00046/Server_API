"""
문서 모니터링 핵심 클래스
INTEROJO 포털에서 신규 자재 요청 문서를 실시간으로 감지하고 처리합니다.
"""
import time
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from config.settings import settings
from utils.logger import logger
from core.excel_manager import ExcelManager
from core.browser_manager import BrowserManager
from utils.exceptions import LoginError, NavigationError, AutomationError


class DocumentMonitor:
    """문서 모니터링 클래스"""
    
    def __init__(self):
        self.browser = BrowserManager()
        self.driver = None
        self.wait = None
        self.excel_manager = ExcelManager()
        
        # 상태 관리
        self.last_check_time = None
        self.processed_documents = set()  # 처리된 문서 ID 추적
        self.session_count = 0
        self.is_logged_in = False
        
        # 상태 파일 경로
        self.state_file = Path(__file__).parent.parent / "data" / "monitor_state.json"
        self.state_file.parent.mkdir(exist_ok=True)
        
        # 이전 상태 로드
        self._load_state()
    
    def initialize(self) -> bool:
        """모니터 초기화"""
        try:
            logger.info("🔧 문서 모니터 초기화 중...")
            
            # 웹드라이버 설정 (BrowserManager 재사용)
            if not self._setup_driver():
                return False
            
            # 포털 로그인
            if not self._login_to_portal():
                return False
            
            # 전자결재 페이지로 이동
            if not self._navigate_to_approval_page():
                return False
            
            logger.info("✅ 문서 모니터 초기화 완료")
            return True
            
        except Exception as e:
            logger.error(f"문서 모니터 초기화 실패: {e}")
            return False
    
    def _setup_driver(self) -> bool:
        """웹드라이버 설정 (BrowserManager에 위임)"""
        try:
            self.browser.setup_driver()
            self.driver = self.browser.driver
            self.wait = self.browser.wait
            logger.info("✅ 웹드라이버 설정 완료 (BrowserManager)")
            return True
        except Exception as e:
            logger.error(f"웹드라이버 설정 실패: {e}")
            return False
    
    def _login_to_portal(self) -> bool:
        """포털 로그인"""
        try:
            logger.info("🔐 포털 로그인 중...")
            
            self.driver.get(settings.portal_url)
            time.sleep(3)
            
            username_field = self.wait.until(
                EC.presence_of_element_located((By.XPATH, "//*[@title='ID']"))
            )
            username_field.clear()
            username_field.send_keys(settings.portal_username)
            
            password_field = self.driver.find_element(By.XPATH, "//*[@title='Password']")
            password_field.clear()
            password_field.send_keys(settings.portal_password)
            
            password_field.submit()
            time.sleep(5)
            
            if "portalMain" in self.driver.current_url or "main" in self.driver.current_url:
                self.is_logged_in = True
                logger.info("✅ 포털 로그인 성공")
                return True
            else:
                logger.error(f"로그인 후 URL 확인 실패: {self.driver.current_url}")
                return False
            
        except Exception as e:
            logger.error(f"포털 로그인 실패: {e}")
            return False
    
    def _navigate_to_approval_page(self) -> bool:
        """전자결재 페이지로 이동"""
        try:
            logger.info("📋 전자결재 페이지로 이동 중...")
            
            self.driver.get(settings.approval_url)
            
            # 페이지 로드 확인
            self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "approval-container")))
            
            logger.info("✅ 전자결재 페이지 이동 완료")
            return True
            
        except Exception as e:
            logger.error(f"전자결재 페이지 이동 실패: {e}")
            return False
    
    def check_for_new_documents(self) -> List[Dict[str, Any]]:
        """신규 문서 체크"""
        try:
            logger.debug("🔍 신규 문서 검색 중...")
            
            # 로그인 상태 확인
            if not self._ensure_logged_in():
                logger.error("로그인 상태 확인 실패")
                return []
            
            # 검색 조건 설정
            search_start_date = self._get_search_start_date()
            
            # 문서 검색 실행
            documents = self._search_documents(
                start_date=search_start_date,
                keywords=settings.search_keywords
            )
            
            # 신규 문서 필터링
            new_documents = self._filter_new_documents(documents)
            
            # 상태 업데이트
            self.last_check_time = datetime.now()
            self._save_state()
            
            return new_documents
            
        except Exception as e:
            logger.error(f"신규 문서 체크 실패: {e}")
            return []
    
    def _get_search_start_date(self) -> str:
        """검색 시작일 결정"""
        if self.last_check_time:
            # 마지막 체크 시간부터 검색 (10분 여유)
            start_time = self.last_check_time - timedelta(minutes=10)
            return start_time.strftime("%Y.%m.%d")
        else:
            # 최초 실행 시 설정된 시작일 사용
            return settings.search_start_date
    
    def _search_documents(self, start_date: str, keywords: List[str]) -> List[Dict[str, Any]]:
        """문서 검색"""
        try:
            # 완료문서함으로 이동
            completed_tab = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), '완료문서함')]"))
            )
            completed_tab.click()
            time.sleep(2)
            
            # 검색 조건 설정
            self._set_search_conditions(start_date, keywords)
            
            # 검색 실행
            search_button = self.driver.find_element(By.ID, "searchButton")
            search_button.click()
            time.sleep(3)
            
            # 결과 파싱
            documents = self._parse_document_list()
            
            logger.info(f"📋 검색 결과: {len(documents)}개 문서 발견")
            return documents
            
        except Exception as e:
            logger.error(f"문서 검색 실패: {e}")
            return []
    
    def _set_search_conditions(self, start_date: str, keywords: List[str]):
        """검색 조건 설정"""
        try:
            # 작성일 범위 설정
            start_date_field = self.driver.find_element(By.ID, "searchStartDate")
            start_date_field.clear()
            start_date_field.send_keys(start_date)
            
            # 종료일은 오늘로 설정
            end_date_field = self.driver.find_element(By.ID, "searchEndDate")
            end_date_field.clear()
            end_date_field.send_keys(datetime.now().strftime("%Y.%m.%d"))
            
            # 키워드 설정 (주로 "자재")
            keyword_field = self.driver.find_element(By.ID, "searchKeyword")
            keyword_field.clear()
            keyword_field.send_keys(" ".join(keywords))
            
        except Exception as e:
            logger.error(f"검색 조건 설정 실패: {e}")
            raise
    
    def _parse_document_list(self) -> List[Dict[str, Any]]:
        """문서 목록 파싱"""
        documents = []
        
        try:
            # 문서 테이블 찾기
            doc_table = self.wait.until(
                EC.presence_of_element_located((By.CLASS_NAME, "document-list-table"))
            )
            
            # 각 문서 행 처리
            rows = doc_table.find_elements(By.TAG_NAME, "tr")[1:]  # 헤더 제외
            
            for row in rows:
                try:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 6:  # 필수 컬럼 확인
                        document = {
                            "id": cells[0].text.strip(),
                            "title": cells[1].text.strip(),
                            "author": cells[2].text.strip(),
                            "department": cells[3].text.strip(),
                            "created_date": cells[4].text.strip(),
                            "status": cells[5].text.strip(),
                            "row_element": row  # 클릭을 위한 요소 참조
                        }
                        
                        # 자재 관련 문서만 필터링
                        if any(keyword in document["title"] for keyword in settings.search_keywords):
                            documents.append(document)
                            
                except Exception as e:
                    logger.warning(f"문서 행 파싱 실패: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"문서 목록 파싱 실패: {e}")
            
        return documents
    
    def _filter_new_documents(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """신규 문서 필터링"""
        new_documents = []
        
        for document in documents:
            doc_id = document["id"]
            if doc_id not in self.processed_documents:
                new_documents.append(document)
                logger.info(f"🆕 신규 문서 발견: {doc_id} - {document['title']}")
        
        return new_documents
    
    def process_document(self, document: Dict[str, Any]):
        """문서 처리 (PDF 저장 + Excel 업데이트)"""
        try:
            doc_id = document["id"]
            logger.info(f"📄 문서 처리 시작: {doc_id}")
            
            # 문서 상세 페이지로 이동
            document["row_element"].click()
            time.sleep(3)
            
            # 문서 상세 정보 추출
            detailed_info = self._extract_document_details()
            document.update(detailed_info)
            
            # PDF 저장
            pdf_path = self._save_document_as_pdf(document)
            document["pdf_path"] = str(pdf_path)
            
            # Excel 업데이트
            self.excel_manager.add_document_data(document)
            
            # 처리 완료 표시
            self.processed_documents.add(doc_id)
            self._save_state()
            
            # 뒤로 가기
            self.driver.back()
            time.sleep(2)
            
            logger.info(f"✅ 문서 처리 완료: {doc_id}")
            
        except Exception as e:
            logger.error(f"문서 처리 실패 {document.get('id', 'Unknown')}: {e}")
            raise
    
    def _extract_document_details(self) -> Dict[str, Any]:
        """문서 상세 정보 추출"""
        details = {}
        
        try:
            # 문서 내용에서 자재 정보 추출
            content_div = self.wait.until(
                EC.presence_of_element_located((By.CLASS_NAME, "document-content"))
            )
            
            # 자재 테이블 찾기
            material_rows = content_div.find_elements(By.XPATH, ".//tr[contains(@class, 'material-row')]")
            
            materials = []
            for row in material_rows:
                try:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) >= 5:
                        material = {
                            "sequence": cells[0].text.strip(),
                            "material_code": cells[1].text.strip(),
                            "material_name": cells[2].text.strip(),
                            "quantity": cells[3].text.strip(),
                            "reason": cells[4].text.strip()
                        }
                        materials.append(material)
                except Exception as e:
                    logger.warning(f"자재 행 파싱 실패: {e}")
                    continue
            
            details["materials"] = materials
            
        except Exception as e:
            logger.warning(f"문서 상세 정보 추출 실패: {e}")
            details["materials"] = []
        
        return details
    
    def _save_document_as_pdf(self, document: Dict[str, Any]) -> Path:
        """문서를 PDF로 저장"""
        try:
            # PDF 파일명 생성
            safe_title = "".join(c for c in document["title"] if c.isalnum() or c in (' ', '-', '_')).rstrip()
            pdf_filename = f"{document['id']}_{safe_title}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            pdf_path = settings.pdf_directory / pdf_filename
            
            # Chrome DevTools Protocol을 사용한 PDF 생성
            self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined,
                    })
                """
            })
            
            # PDF 생성
            pdf_data = self.driver.execute_cdp_cmd("Page.printToPDF", {
                "format": "A4",
                "printBackground": True,
                "marginTop": 0.39,
                "marginBottom": 0.39,
                "marginLeft": 0.39,
                "marginRight": 0.39
            })
            
            # PDF 파일 저장
            import base64
            with open(pdf_path, "wb") as f:
                f.write(base64.b64decode(pdf_data["data"]))
            
            logger.info(f"📄 PDF 저장 완료: {pdf_path}")
            return pdf_path
            
        except Exception as e:
            logger.error(f"PDF 저장 실패: {e}")
            raise
    
    def _ensure_logged_in(self) -> bool:
        """로그인 상태 확인 및 재로그인"""
        try:
            # 로그인 상태 확인
            if self.driver.current_url and "login" in self.driver.current_url.lower():
                logger.warning("로그인 세션 만료 감지")
                return self._login_to_portal()
            
            return True
            
        except Exception as e:
            logger.error(f"로그인 상태 확인 실패: {e}")
            return False
    
    def restart_browser(self):
        """브라우저 재시작 (메모리 최적화)"""
        try:
            logger.info("🔄 브라우저 재시작 중...")
            
            if self.driver:
                self.driver.quit()
            
            self.session_count = 0
            self.is_logged_in = False
            
            # 재초기화
            if self.initialize():
                logger.info("✅ 브라우저 재시작 완료")
            else:
                logger.error("❌ 브라우저 재시작 실패")
                
        except Exception as e:
            logger.error(f"브라우저 재시작 실패: {e}")
    
    def cleanup(self):
        """리소스 정리"""
        try:
            if self.driver:
                self.driver.quit()
                logger.info("✅ 브라우저 리소스 정리 완료")
        except Exception as e:
            logger.error(f"리소스 정리 실패: {e}")
    
    def _load_state(self):
        """이전 상태 로드"""
        try:
            if self.state_file.exists():
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                    
                self.processed_documents = set(state.get('processed_documents', []))
                
                if state.get('last_check_time'):
                    self.last_check_time = datetime.fromisoformat(state['last_check_time'])
                
                logger.info(f"📂 이전 상태 로드: {len(self.processed_documents)}개 문서 기록")
                
        except Exception as e:
            logger.warning(f"상태 파일 로드 실패: {e}")
    
    def _save_state(self):
        """현재 상태 저장"""
        try:
            state = {
                'processed_documents': list(self.processed_documents),
                'last_check_time': self.last_check_time.isoformat() if self.last_check_time else None,
                'session_count': self.session_count
            }
            
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"상태 저장 실패: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """모니터 상태 반환"""
        return {
            "is_initialized": self.driver is not None,
            "is_logged_in": self.is_logged_in,
            "last_check_time": self.last_check_time.isoformat() if self.last_check_time else None,
            "processed_count": len(self.processed_documents),
            "session_count": self.session_count
        }