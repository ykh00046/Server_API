"""
문서 처리 모듈

문서 데이터 추출, PDF 저장, 단일 문서 처리 워크플로우를 담당합니다.
"""
import re
import time
import base64
from datetime import datetime

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

from config.settings import settings
from utils.logger import logger
from utils.error_handler import take_error_screenshot
from utils.retry_decorator import retry


class DocumentHandler:
    """문서 데이터 처리 클래스
    
    개별 문서의 데이터 추출, PDF 생성, 처리 워크플로우를 제공합니다.
    
    Args:
        driver: Chrome WebDriver 인스턴스
        wait: WebDriverWait 인스턴스
        excel_manager: ExcelManager 인스턴스
        doc_manager: ProcessedDocumentManager 인스턴스
        metrics: MetricsCollector 인스턴스
    """
    
    def __init__(self, driver, wait, excel_manager, doc_manager, metrics):
        self.driver = driver
        self.wait = wait
        self.excel_manager = excel_manager
        self.doc_manager = doc_manager
        self.metrics = metrics
        self.processed_count = 0
    
    def extract_document_data(self):
        """문서에서 데이터 추출 (정규식 오류 처리 강화)

        Returns:
            tuple: (table_rows, drafter, doc_number, department)
        """
        try:
            # 문서 페이지 로딩 대기 (approval_view_wrap 또는 대안 요소)
            try:
                self.wait.until(EC.presence_of_element_located((By.CLASS_NAME, "approval_view_wrap")))
                logger.info("✅ approval_view_wrap 찾음")
            except:
                logger.warning("⚠️ approval_view_wrap 없음, body로 진행")
                time.sleep(2)  # 페이지 로딩 추가 대기

            # 현재 URL 확인 (디버깅)
            current_url = self.driver.current_url
            logger.info(f"🔍 현재 URL: {current_url}")

            page_text = self.driver.find_element(By.TAG_NAME, "body").text.strip()
            logger.info(f"📄 페이지 텍스트 길이: {len(page_text)} 문자")

            # 기안자 추출 (패턴 1 또는 2, 실패 시 기본값)
            drafter_match = re.search(r"기안자\s+(.+?)/", page_text) or \
                           re.search(r"기안자\s*[:：]\s*(.+)", page_text)
            drafter = drafter_match.group(1).strip() if drafter_match else "Unknown"

            # 문서번호 추출 (패턴 1 또는 2, 실패 시 기본값)
            doc_number_match = re.search(r"문서번호\s+(\S+)", page_text) or \
                              re.search(r"문서번호\s*[:：]\s*(\S+)", page_text)
            doc_number = doc_number_match.group(1).strip() if doc_number_match else ""

            # 요청부서 추출 (패턴 1 또는 2, 실패 시 기본값)
            department_match = re.search(r"요청부서\s+(.+)", page_text) or \
                              re.search(r"요청부서\s*[:：]\s*(.+)", page_text)
            department = department_match.group(1).strip() if department_match else "Unknown"

            # 자재 테이블 데이터 추출
            table_rows = []
            tables = self.driver.find_elements(By.TAG_NAME, "table")
            logger.info(f"📊 페이지 내 총 테이블 개수: {len(tables)}")

            for table_idx, table in enumerate(tables, 1):
                rows = table.find_elements(By.TAG_NAME, "tr")
                logger.info(f"  테이블 {table_idx}: {len(rows)}개 행")

                for row_idx, row in enumerate(rows, 1):
                    cells = row.find_elements(By.TAG_NAME, "td")

                    # 디버깅: 처음 3개 행만 상세 출력
                    if row_idx <= 3 and len(cells) > 0:
                        first_cell = cells[0].text.strip()
                        logger.info(f"    행 {row_idx}: {len(cells)}개 셀, 첫 셀='{first_cell}'")

                    # 최소 4개 컬럼, 첫 번째 컬럼이 숫자인 행만 추출
                    if len(cells) >= 4 and cells[0].text.strip().isdigit():
                        # 5개 컬럼까지 추출 (부족하면 빈 문자열)
                        row_data = [cells[i].text.strip() if i < len(cells) else "" for i in range(5)]
                        table_rows.append(row_data)
                        logger.info(f"    ✅ 데이터 행 추가: {row_data}")

                if table_rows:
                    logger.info(f"✅ 테이블 {table_idx}에서 {len(table_rows)}개 자재 행 발견, 탐색 종료")
                    break

            logger.info(f"데이터 추출 완료 - 기안자: {drafter}, 문서번호: {doc_number}, 부서: {department}, 자재 행: {len(table_rows)}")
            return table_rows, drafter, doc_number, department

        except Exception as e:
            logger.error(f"문서 데이터 추출 실패: {e}")
            take_error_screenshot(self.driver, "extract_document_data")
            return [], "Unknown", "", "Unknown"

    @retry(max_attempts=2, delay=1.0)
    def save_screenshot_as_pdf(self, drafter, doc_number):
        """PDF 파일 저장 (날짜별 폴더에 저장)

        Args:
            drafter: 기안자명
            doc_number: 문서번호 (예: 20251127P001)

        Returns:
            str: 저장된 PDF 파일 경로, 실패 시 None
        """
        start_time = time.time()
        try:
            # 문서번호에서 날짜 추출 시도 (형식: 20251127P001 -> 2025-11-27)
            date_str = None
            if doc_number and len(doc_number) >= 8 and doc_number[:8].isdigit():
                try:
                    doc_date = datetime.strptime(doc_number[:8], '%Y%m%d')
                    date_str = doc_date.strftime('%Y-%m-%d')
                    logger.debug(f"문서번호에서 날짜 추출: {date_str}")
                except ValueError:
                    logger.debug(f"문서번호에서 날짜 추출 실패: {doc_number}, 현재 날짜 사용")

            # 날짜별 디렉토리 가져오기 (날짜 추출 실패 시 오늘 날짜 사용)
            pdf_dir = settings.get_pdf_directory_by_date(date_str)

            # 파일명 생성 (특수문자 제거)
            file_name = f"{drafter}_{doc_number}.pdf".replace("/", "_").replace("\\", "_").replace(" ", "_")
            file_path = pdf_dir / file_name

            # Chrome DevTools Protocol로 PDF 생성
            result = self.driver.execute_cdp_cmd('Page.printToPDF', {'printBackground': True})

            # PDF 파일 저장
            with open(file_path, 'wb') as file:
                file.write(base64.b64decode(result['data']))

            # PDF 생성 시간 기록
            elapsed = time.time() - start_time
            self.metrics.record_pdf_time(elapsed)

            logger.info(f"PDF 저장 완료: {file_path}")
            return str(file_path)

        except Exception as e:
            logger.error(f"PDF 저장 실패 ({drafter}_{doc_number}): {e}")
            return None

    def process_document(self, doc_info):
        """단일 문서 처리 워크플로우
        
        Args:
            doc_info: 문서 정보 dict {'title': str, 'id': str}
        """
        # 문서 처리 시작 기록
        self.metrics.start_document()
        
        try:
            logger.info(f"문서 처리 시작: {doc_info['title']}")
            
            # 1. 데이터 추출
            table_rows, drafter, document_number, department = self.extract_document_data()
            if not document_number:
                document_number = doc_info['id']
            
            # 2. 해시 계산
            doc_hash = self.doc_manager.calculate_hash(table_rows)
            
            # 3. 처리 여부 확인 (영속적 이력 기반)
            check_result = self.doc_manager.is_processed(document_number, doc_hash)
            
            if check_result['processed'] and not check_result['modified']:
                logger.info(f"✓ 문서 {document_number} 이미 처리됨 - 스킵")
                self.doc_manager.mark_processed(
                    doc_id=document_number,
                    doc_hash=doc_hash,
                    status='skipped',
                    drafter=drafter,
                    department=department
                )
                self.metrics.end_document('skipped')
                return
            
            if check_result['modified']:
                logger.warning(f"⚠ 문서 {document_number} 수정본 감지 - 재처리")
            
            if not table_rows:
                logger.warning(f"자재 테이블 데이터가 없어서 건너뛰기: {doc_info['title']}")
                self.doc_manager.mark_processed(
                    doc_id=document_number,
                    doc_hash=doc_hash,
                    status='skipped',
                    drafter=drafter,
                    department=department,
                    error_message="자재 테이블 없음"
                )
                self.metrics.end_document('skipped')
                return
            
            try:
                # 4. PDF 저장
                pdf_path = self.save_screenshot_as_pdf(drafter, document_number)
                
                # 5. Excel 저장
                excel_start = time.time()
                self.excel_manager.save_material_data(table_rows, drafter, document_number, department)
                excel_elapsed = time.time() - excel_start
                self.metrics.record_excel_time(excel_elapsed)
                excel_row = self.excel_manager.current_row - 1
                
                # 6. 처리 완료 기록
                self.doc_manager.mark_processed(
                    doc_id=document_number,
                    doc_hash=doc_hash,
                    status='success',
                    drafter=drafter,
                    department=department,
                    pdf_path=pdf_path,
                    excel_row=excel_row
                )
                
                self.processed_count += 1
                self.metrics.end_document('success')
                logger.info(f"✅ 문서 처리 완료: {doc_info['title']} (누적 {self.processed_count}건)")
                
            except Exception as e:
                # 처리 실패 기록
                self.doc_manager.mark_processed(
                    doc_id=document_number,
                    doc_hash=doc_hash,
                    status='failed',
                    drafter=drafter,
                    department=department,
                    error_message=str(e)
                )
                self.metrics.record_error(str(e))
                self.metrics.end_document('failed')
                raise
                
        except Exception as e:
            logger.error(f"문서 처리 실패: {doc_info['title']} - {e}")
            self.metrics.end_document('failed')
            take_error_screenshot(self.driver, f"doc_process_fail_{doc_info.get('id','unknown')}")
            raise
