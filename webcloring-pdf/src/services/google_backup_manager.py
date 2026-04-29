"""
Google Sheets 백업 관리 서비스

ExcelManager에서 분리된 Google Sheets 백업 오케스트레이션을 담당합니다.
"""
from utils.logger import logger

# Google Sheets 통합 (Lazy Loading)
try:
    from src.services.google_sheets_manager import GoogleSheetsManager
    GOOGLE_SHEETS_AVAILABLE = True
except ImportError:
    GOOGLE_SHEETS_AVAILABLE = False
    logger.debug("Google Sheets 모듈을 사용할 수 없습니다 (선택 사항)")


class GoogleBackupManager:
    """Google Sheets 백업 오케스트레이션 클래스

    ExcelManager에서 분리된 Google Sheets 백업 로직입니다.

    Args:
        excel_manager: ExcelManager 인스턴스 (데이터 소스)
    """

    def __init__(self, excel_manager):
        self.excel_manager = excel_manager
        self._google_sheets_manager = None

    @property
    def google_sheets_manager(self):
        """Google Sheets Manager 인스턴스 (Lazy Loading)

        처음 접근 시에만 초기화되어 초기 로딩 시간을 단축합니다.
        """
        if self._google_sheets_manager is None and GOOGLE_SHEETS_AVAILABLE:
            try:
                self._google_sheets_manager = GoogleSheetsManager()
                logger.debug("GoogleSheetsManager 초기화 완료 (Lazy Loading)")
            except Exception as e:
                logger.warning(f"GoogleSheetsManager 초기화 실패: {e}")
        return self._google_sheets_manager

    def finalize(self) -> bool:
        """자동화 종료 시 Google Sheets 백업 실행

        배치 처리 - 전체 Excel 데이터를 1회만 백업합니다.
        GUI 프리징 방지를 위해 스레드에서 실행 권장합니다.

        Returns:
            bool: 백업 성공 여부
        """
        if not GOOGLE_SHEETS_AVAILABLE:
            logger.debug("Google Sheets 모듈을 사용할 수 없습니다")
            return False

        if self.google_sheets_manager is None:
            logger.debug("Google Sheets가 설정되지 않았습니다")
            return False

        try:
            # 백업 전 강제 저장
            self.excel_manager.force_save()

            # Google Sheets 백업 실행 (배치 처리)
            logger.info("📤 Google Sheets 백업 시작...")
            success = self.google_sheets_manager.backup_materials(
                excel_manager=self.excel_manager,
                silent=False
            )

            if success:
                logger.info("✅ Google Sheets 백업 완료")
            else:
                logger.warning("⚠️ Google Sheets 백업 실패 (Excel 데이터는 정상 저장됨)")

            return success

        except Exception as e:
            logger.error(f"Google Sheets 백업 중 오류: {e}")
            logger.warning("Excel 데이터는 정상적으로 저장되었습니다")
            return False
