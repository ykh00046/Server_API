"""
INTEROJO 포털 자동화 메인 실행 파일
GUI 모드와 자동화 모드를 지원합니다.
"""
import sys
import argparse
from pathlib import Path
import os
import time
from datetime import datetime

# Set encoding for stdout/stderr explicitly and early
# This often helps with issues in different terminal environments
if sys.stdout and sys.stdout.encoding != 'utf-8':
    sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
if sys.stderr and sys.stderr.encoding != 'utf-8':
    sys.stderr = open(sys.stderr.fileno(), mode='w', encoding='utf-8', buffering=1)


# PyInstaller로 빌드된 실행 파일에서 올바른 경로를 찾기 위한 처리
# https://pyinstaller.org/en/stable/runtime-information.html
if getattr(sys, 'frozen', False):
    # 실행 파일 모드일 때, 베이스 경로는 PyInstaller가 만든 임시 폴더
    project_root = Path(sys._MEIPASS)
    # PyInstaller는 pathex에 지정된 src 폴더의 모듈들을 최상위 레벨에 위치시키므로,
    # _MEIPASS 폴더 자체가 검색 경로가 되어야 합니다.
    src_path = project_root
else:
    # 일반 스크립트 실행 모드
    project_root = Path(__file__).parent
    src_path = project_root / "src"

sys.path.insert(0, str(project_root))
sys.path.insert(0, str(src_path))


from core.portal_automation import PortalAutomation
from core.scheduler import ServiceScheduler
from config.settings import settings
from utils.logger import logger


def run_automation():
    """자동화 실행 (콘솔 모드)"""
    try:
        print("=" * 60)
        print("🚀 INTEROJO 포털 자동화 시작")
        print("=" * 60)

        # 포털 자동화 인스턴스 생성
        automation = PortalAutomation()

        # 전체 자동화 프로세스 실행
        success = automation.run_automation()

        if success:
            print("✅ 모든 작업이 성공적으로 완료되었습니다.")
            logger.info("자동화 프로세스 완료")
            return 0
        else:
            print("❌ 작업 중 오류가 발생했습니다.")
            logger.error("자동화 프로세스 실패")
            return 1

    except KeyboardInterrupt:
        print("\n사용자에 의해 프로그램이 중단되었습니다.")
        return 0
    except Exception as e:
        print(f"예상치 못한 오류가 발생했습니다: {e}")
        logger.error(f"메인 함수 오류: {e}")
        return 1


def run_scheduled():
    """스케줄된 시간에 자동화 실행 (대기 모드)"""
    import schedule

    schedule_time = settings.schedule_time
    auto_enabled = settings.auto_enabled

    print("=" * 60)
    print(f"⏰ 스케줄 모드 시작")
    print(f"   예약 시간: {schedule_time}")
    print(f"   자동 실행: {'활성화' if auto_enabled else '비활성화'}")
    print("=" * 60)

    if not auto_enabled:
        print("⚠️ 자동 실행이 비활성화되어 있습니다.")
        print("   .env 파일에서 AUTO_ENABLED=True로 설정하세요.")
        return 0

    def job():
        """스케줄된 작업"""
        logger.info(f"⏰ 예약된 시간({schedule_time})에 자동화 시작")
        run_automation()

    # 스케줄 등록
    schedule.every().day.at(schedule_time).do(job)

    next_run = schedule.next_run()
    print(f"📅 다음 실행: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")

    # 스케줄러 실행 루프
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # 1분마다 체크
    except KeyboardInterrupt:
        print("\n⏹️ 스케줄러가 중단되었습니다.")
        return 0


def run_gui():
    """GUI 모드 실행"""
    try:
        from gui.main_window import main as gui_main
        gui_main()
        return 0

    except ImportError as e:
        print(f"GUI 모듈을 불러올 수 없습니다: {e}")
        print("tkinter가 설치되어 있는지 확인해주세요.")
        return 1
    except Exception as e:
        print(f"GUI 실행 중 오류: {e}")
        return 1


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description='INTEROJO 포털 자동화')
    parser.add_argument('--auto', action='store_true',
                       help='자동화 모드로 실행 (GUI 없이)')
    parser.add_argument('--schedule', action='store_true',
                       help='스케줄 모드로 실행 (지정된 시간까지 대기)')
    parser.add_argument('--gui', action='store_true',
                       help='GUI 모드로 실행 (기본값)')

    args = parser.parse_args()

    # 인수가 없으면 GUI 모드가 기본
    if not args.auto and not args.gui and not args.schedule:
        args.gui = True

    if args.schedule:
        return run_scheduled()
    elif args.auto:
        return run_automation()
    elif args.gui:
        return run_gui()


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)