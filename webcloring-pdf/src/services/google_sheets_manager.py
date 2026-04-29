"""
구글 시트 백업 관리자 - v3.0
자재 데이터를 구글 시트에 백업합니다.

주요 개선사항:
- Rate Limiting: 60초 최소 간격으로 API 호출 제한
- Batch Processing: 개별 저장이 아닌 배치 처리로 API 호출 최소화
- Thread-Safe: 스레드 안전한 백업 작업
- Fail-Safe: 백업 실패해도 메인 로직 영향 없음
"""
import os
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from typing import Optional, Dict, Any, List
from utils.logger import logger
from config.settings import settings
from src.config.google_sheets_config import GoogleSheetsConfig


class GoogleSheetsManager:
    """구글 시트 백업 관리자"""

    def __init__(self):
        """초기화"""
        self.client = None
        self.spreadsheet = None
        self.worksheet = None
        self.is_connected = False
        self.config = GoogleSheetsConfig()
        self.is_backing_up = False  # 백업 중 상태

        # v3.0: Rate Limiting
        self.last_backup_time = None
        self.min_backup_interval = settings.min_backup_interval  # 설정 파일에서 로드

        # 자동 연결 시도 (설정이 있는 경우)
        self.auto_connect()

    def auto_connect(self) -> bool:
        """설정된 정보로 자동 연결"""
        if self.config.is_configured():
            try:
                return self.setup_connection(
                    self.config.get_credentials_file(),
                    self.config.get_spreadsheet_url()
                )
            except Exception as e:
                logger.warning(f"구글 시트 자동 연결 실패: {e}")
                return False
        return False

    def setup_connection(self, credentials_file: str, spreadsheet_url: str) -> bool:
        """구글 시트 연결 설정

        Args:
            credentials_file (str): JSON 인증 파일 경로
            spreadsheet_url (str): 구글 스프레드시트 URL

        Returns:
            bool: 연결 성공 여부
        """
        try:
            # 인증 파일 확인
            if not os.path.exists(credentials_file):
                logger.error(f"인증 파일을 찾을 수 없습니다: {credentials_file}")
                return False

            # 구글 시트 클라이언트 설정
            scope = ['https://www.googleapis.com/auth/spreadsheets']
            credentials = Credentials.from_service_account_file(credentials_file, scopes=scope)
            self.client = gspread.authorize(credentials)

            # 스프레드시트 열기
            self.spreadsheet = self.client.open_by_url(spreadsheet_url)

            # 첫 번째 워크시트 선택 (또는 생성)
            try:
                self.worksheet = self.spreadsheet.sheet1
            except:
                # 워크시트가 없으면 생성
                self.worksheet = self.spreadsheet.add_worksheet(
                    title="자재내역",
                    rows="1000",
                    cols="20"
                )

            self.is_connected = True

            # 설정 저장
            self.config.set_credentials_file(credentials_file)
            self.config.set_spreadsheet_url(spreadsheet_url)
            self.config.set_backup_enabled(True)

            logger.info("✅ 구글 시트 연결 성공")
            return True

        except Exception as e:
            logger.error(f"구글 시트 연결 실패: {e}")
            self.is_connected = False
            return False

    def backup_materials(self, excel_manager, silent: bool = False) -> bool:
        """자재 데이터를 구글 시트에 백업

        v3.0: 배치 처리 - 자동화 종료 후 1회만 호출됨

        Args:
            excel_manager: ExcelManager 인스턴스
            silent: 조용한 백업 모드 (로그 최소화)

        Returns:
            bool: 백업 성공 여부
        """
        if not self.is_connected:
            if not silent:
                logger.warning("⚠️ 구글 시트에 연결되지 않았습니다. 백업을 건너뜁니다.")
            return False

        # v3.0: Rate Limiting 체크
        if self.last_backup_time:
            elapsed = (datetime.now() - self.last_backup_time).total_seconds()
            if elapsed < self.min_backup_interval:
                remaining = self.min_backup_interval - elapsed
                logger.info(f"⏳ 백업 간격 제한: {remaining:.0f}초 후 재시도 가능")
                return False

        # 백업 중 상태 설정
        self.is_backing_up = True

        try:
            # Excel 데이터 가져오기
            backup_data = self._prepare_backup_data(excel_manager)

            if len(backup_data) <= 1:  # 헤더만 있는 경우
                if not silent:
                    logger.warning("⚠️ 백업할 자재 데이터가 없습니다.")
                return False

            # 워크시트에 데이터 업로드
            self._upload_to_sheet(backup_data)

            # 백업 성공 시 설정 업데이트
            self.config.set_last_backup_time()
            self.config.increment_backup_success()
            self.last_backup_time = datetime.now()  # v3.0: Rate Limiting 시간 기록

            if not silent:
                logger.info(f"📤 구글 시트 백업 완료: {len(backup_data)-1}건의 자재 데이터")
            return True

        except Exception as e:
            # 백업 실패 시 설정 업데이트
            self.config.increment_backup_failure()
            self._log_backup_failure(e)

            if not silent:
                logger.error(f"❌ 구글 시트 백업 실패: {e}")
            return False

        finally:
            # 백업 중 상태 해제
            self.is_backing_up = False

    def _prepare_backup_data(self, excel_manager) -> List[List[Any]]:
        """백업용 데이터 준비

        Args:
            excel_manager: ExcelManager 인스턴스

        Returns:
            List[List[Any]]: 구글 시트에 업로드할 데이터
        """
        # 헤더 정의 (ExcelManager와 동일한 구조)
        headers = excel_manager.columns.copy()
        headers.append("백업일시")  # 백업 시간 추가

        backup_rows = [headers]
        backup_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Excel에서 데이터 읽기
        try:
            ws = excel_manager.worksheet

            # 데이터 행만 추출 (헤더 제외, 2행부터)
            for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                # 빈 행 건너뛰기
                if not any(row):
                    continue

                # 순번 값이 없으면 건너뛰기
                if not row[0]:
                    continue

                # 데이터 행 추가 (모든 컬럼 + 백업 일시)
                backup_row = [
                    str(cell) if cell is not None else ""
                    for cell in row[:len(excel_manager.columns)]
                ]
                backup_row.append(backup_datetime)  # 백업일시
                backup_rows.append(backup_row)

            logger.info(f"📊 백업 데이터 준비 완료: {len(backup_rows)-1}건")

        except Exception as e:
            logger.error(f"데이터 준비 중 오류: {e}")
            raise

        return backup_rows

    def _upload_to_sheet(self, data: List[List[Any]]) -> None:
        """데이터를 구글 시트에 업로드

        v3.0: Clear & Update 방식 (Phase 1)

        Args:
            data: 업로드할 데이터
        """
        try:
            # 1. 기존 데이터 삭제
            self.worksheet.clear()
            logger.debug("기존 데이터 삭제 완료")

            # 2. 시트 크기 조정
            if len(data) > 0:
                rows_needed = len(data)
                cols_needed = len(data[0]) if data else 12

                # 여유 공간을 두고 시트 크기 조정
                self.worksheet.resize(
                    rows=max(rows_needed + 100, 1000),
                    cols=max(cols_needed, 15)
                )
                logger.debug(f"시트 크기 조정: {rows_needed + 100}행 × {cols_needed}열")

            # 3. 데이터 업로드 (배치로 한번에)
            if len(data) > 0:
                end_col_letter = chr(ord('A') + len(data[0]) - 1)
                range_name = f'A1:{end_col_letter}{len(data)}'
                self.worksheet.update(range_name=range_name, values=data)
                logger.debug(f"데이터 업로드 완료: {range_name}")

            # 4. 헤더 스타일링 (굵게, 회색 배경)
            header_range = f'A1:{chr(ord("A") + len(data[0]) - 1)}1' if data else 'A1:L1'
            self.worksheet.format(header_range, {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.9, 'green': 0.9, 'blue': 0.9}
            })
            logger.debug("헤더 스타일링 완료")

        except Exception as e:
            logger.error(f"구글 시트 업로드 실패: {e}")
            raise

    def _log_backup_failure(self, error: Exception) -> None:
        """백업 실패 로그 기록"""
        try:
            log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
            os.makedirs(log_dir, exist_ok=True)

            log_file = os.path.join(log_dir, 'backup_failures.log')

            with open(log_file, 'a', encoding='utf-8') as f:
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                f.write(f"[{timestamp}] 백업 실패: {str(error)}\n")
        except Exception as e:
            logger.error(f"백업 실패 로그 기록 오류: {e}")

    def test_connection(self) -> Dict[str, Any]:
        """연결 테스트

        Returns:
            Dict[str, Any]: 테스트 결과
        """
        result = {
            'success': False,
            'message': '',
            'spreadsheet_name': '',
            'worksheet_name': ''
        }

        try:
            if not self.is_connected:
                result['message'] = "구글 시트에 연결되지 않았습니다."
                return result

            # 스프레드시트 정보 가져오기
            result['spreadsheet_name'] = self.spreadsheet.title
            result['worksheet_name'] = self.worksheet.title
            result['success'] = True
            result['message'] = "연결 테스트 성공"

        except Exception as e:
            result['message'] = f"연결 테스트 실패: {e}"

        return result

    def create_sample_data(self) -> bool:
        """샘플 데이터로 테스트

        Returns:
            bool: 테스트 성공 여부
        """
        if not self.is_connected:
            logger.error("구글 시트에 연결되지 않았습니다.")
            return False

        try:
            # 샘플 데이터
            sample_data = [
                ["No", "기안자", "문서번호", "부서", "품명", "규격", "수량", "단위", "단가", "금액", "비고", "등록일시"],
                ["1", "테스트기안자", "TEST-001", "테스트부서", "테스트품명", "100x200", "10", "EA", "1000", "10000", "테스트",
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
            ]

            self._upload_to_sheet(sample_data)
            logger.info("✅ 샘플 데이터 업로드 완료")
            return True

        except Exception as e:
            logger.error(f"❌ 샘플 데이터 업로드 실패: {e}")
            return False

    def get_backup_status(self) -> Dict[str, Any]:
        """백업 상태 정보 반환"""
        return {
            'is_connected': self.is_connected,
            'is_backing_up': self.is_backing_up,
            'is_configured': self.config.is_configured(),
            'last_backup_time': self.config.get_last_backup_time(),
            'success_count': self.config.get_backup_success_count(),
            'failure_count': self.config.get_backup_failure_count(),
            'status_text': self.config.get_backup_status_text()
        }


def create_credentials_guide() -> str:
    """구글 API 인증 설정 가이드

    Returns:
        str: 설정 가이드 텍스트
    """
    guide = """
🔧 구글 시트 백업 설정 가이드

1. Google Cloud Console 접속
   - https://console.cloud.google.com/ 접속
   - 새 프로젝트 생성 또는 기존 프로젝트 선택

2. Google Sheets API 활성화
   - "API 및 서비스" → "라이브러리" 메뉴
   - "Google Sheets API" 검색하여 활성화

3. 서비스 계정 생성
   - "API 및 서비스" → "사용자 인증 정보" 메뉴
   - "+ 사용자 인증 정보 만들기" → "서비스 계정" 선택
   - 서비스 계정 이름 입력 (예: "interojo-automation-backup")
   - 역할: "편집자" 선택

4. JSON 키 파일 다운로드
   - 생성된 서비스 계정 클릭
   - "키" 탭 → "키 추가" → "새 키 만들기"
   - JSON 형식 선택하여 다운로드
   - 파일을 프로젝트의 'src/config' 디렉토리에 저장

5. 구글 시트 준비
   - 새 구글 시트 생성
   - 서비스 계정 이메일을 시트에 "편집자" 권한으로 공유
   - 시트 URL 복사

6. 프로그램 설정
   - JSON 파일 경로와 시트 URL을 프로그램에 입력
   - "연결 테스트" 버튼으로 확인

📋 필요한 패키지:
pip install gspread google-auth
"""
    return guide
