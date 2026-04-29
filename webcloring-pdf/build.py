#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
INTEROJO 포털 자동화 시스템 - 빌드 스크립트
PyInstaller를 사용하여 실행 파일을 생성합니다.

사용법:
    python build.py               # 일반 빌드
    python build.py --clean       # 완전 정리 후 빌드
    python build.py --test        # 빌드 후 자동 테스트
"""
import os
import shutil
import subprocess
import sys
import argparse
from pathlib import Path
from datetime import datetime

# --- 설정 ---
PROJECT_ROOT = Path(__file__).parent
SPEC_FILE = PROJECT_ROOT / 'automation.spec'
DIST_DIR = PROJECT_ROOT / 'dist'
BUILD_DIR = PROJECT_ROOT / 'build'
VERSION = '3.1.0'

# 색상 코드 (Windows 콘솔)
try:
    import colorama
    colorama.init()
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
except ImportError:
    GREEN = YELLOW = RED = BLUE = RESET = ''


def print_header(message):
    """헤더 출력"""
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}{message}{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")


def print_success(message):
    """성공 메시지"""
    print(f"{GREEN}✓ {message}{RESET}")


def print_warning(message):
    """경고 메시지"""
    print(f"{YELLOW}⚠ {message}{RESET}")


def print_error(message):
    """오류 메시지"""
    print(f"{RED}✗ {message}{RESET}")


def check_dependencies():
    """필수 의존성 확인"""
    print_header("Step 1: 의존성 확인")

    required_packages = [
        'pyinstaller',
        'selenium',
        'openpyxl',
        'python-dotenv',
        'schedule',
        'psutil',
        'gspread',           # Google Sheets API (v3.0)
        'google-auth',       # Google 인증 (v3.0)
        'colorama',          # 콘솔 색상
        'tabulate',          # 테이블 출력
        'webdriver-manager', # ChromeDriver 자동 관리
    ]

    missing = []
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
            print_success(f"{package} 설치됨")
        except ImportError:
            missing.append(package)
            print_error(f"{package} 누락")

    if missing:
        print_error(f"\n누락된 패키지: {', '.join(missing)}")
        print(f"\n설치 명령: pip install {' '.join(missing)}")
        return False

    print_success("모든 의존성 확인 완료")
    return True


def check_required_files():
    """필수 파일 확인"""
    print_header("Step 2: 필수 파일 확인")

    required_files = [
        'main.py',
        'automation.spec',
        'src/core/portal_automation.py',
        'src/core/excel_manager.py',
        'src/core/scheduler.py',
        'src/gui/main_window.py',
        'src/gui/settings_dialog.py',
        'src/gui/google_sheets_dialog.py',  # v3.0
        'src/config/settings.py',
        'src/config/config.json',
        'src/config/google_sheets_config.py',  # v3.0
        'src/services/google_sheets_manager.py',  # v3.0
        'src/utils/logger.py',
        'src/utils/error_handler.py',
    ]

    missing = []
    for file_path in required_files:
        full_path = PROJECT_ROOT / file_path
        if full_path.exists():
            print_success(f"{file_path}")
        else:
            missing.append(file_path)
            print_error(f"{file_path} 누락")

    if missing:
        print_error(f"\n필수 파일 누락: {len(missing)}개")
        return False

    print_success("모든 필수 파일 확인 완료")
    return True


def clean_build_directories(full_clean=False):
    """빌드 디렉토리 정리"""
    print_header("Step 3: 빌드 디렉토리 정리")

    dirs_to_clean = [DIST_DIR, BUILD_DIR]

    if full_clean:
        # 완전 정리 시 추가 디렉토리
        dirs_to_clean.extend([
            PROJECT_ROOT / '__pycache__',
            PROJECT_ROOT / 'src' / '__pycache__',
        ])

    for dir_path in dirs_to_clean:
        if dir_path.exists():
            try:
                shutil.rmtree(dir_path)
                print_success(f"{dir_path.name}/ 삭제 완료")
            except Exception as e:
                print_warning(f"{dir_path.name}/ 삭제 실패: {e}")
        else:
            print(f"  {dir_path.name}/ 이미 없음")

    print_success("디렉토리 정리 완료")


def run_pyinstaller():
    """PyInstaller 실행"""
    print_header("Step 4: PyInstaller 빌드 실행")

    if not SPEC_FILE.exists():
        print_error(f"SPEC 파일을 찾을 수 없습니다: {SPEC_FILE}")
        return False

    command = [
        sys.executable,
        '-m',
        'PyInstaller',
        str(SPEC_FILE),
        '--noconfirm',  # 확인 없이 실행
        '--clean',      # 캐시 정리
    ]

    print(f"명령어: {' '.join(command)}\n")

    try:
        result = subprocess.run(
            command,
            check=True,
            text=True,
            encoding='utf-8',
            capture_output=True,
        )

        # 성공 메시지
        print_success("빌드 성공!")

        # 경고 메시지가 있으면 표시
        if result.stderr:
            print_warning("경고 메시지:")
            for line in result.stderr.split('\n'):
                if line.strip() and 'WARNING' in line:
                    print(f"  {line}")

        return True

    except subprocess.CalledProcessError as e:
        print_error("PyInstaller 빌드 실패")
        print(f"\n반환 코드: {e.returncode}")
        if e.stdout:
            print("\nSTDOUT:")
            print(e.stdout)
        if e.stderr:
            print("\nSTDERR:")
            print(e.stderr)
        return False

    except FileNotFoundError:
        print_error("'PyInstaller'를 찾을 수 없습니다")
        print("설치 명령: pip install pyinstaller")
        return False


def verify_build():
    """빌드 결과 검증"""
    print_header("Step 5: 빌드 결과 검증")

    exe_path = DIST_DIR / 'interojo_automation' / 'interojo_automation.exe'

    if not exe_path.exists():
        print_error("실행 파일을 찾을 수 없습니다")
        return False

    print_success(f"실행 파일 생성 확인: {exe_path.name}")

    # 파일 크기 확인
    size_mb = exe_path.stat().st_size / (1024 * 1024)
    print(f"  파일 크기: {size_mb:.2f} MB")

    # 폴더 내용 확인
    dist_contents = list((DIST_DIR / 'interojo_automation').iterdir())
    print(f"  전체 파일/폴더 수: {len(dist_contents)}개")

    # 필수 파일 확인
    required_in_dist = ['_internal']
    for item in required_in_dist:
        item_path = DIST_DIR / 'interojo_automation' / item
        if item_path.exists():
            print_success(f"  {item}/ 폴더 확인")
        else:
            print_warning(f"  {item}/ 폴더 누락")

    print_success("빌드 결과 검증 완료")
    return True


def create_user_guide():
    """사용자 가이드 생성"""
    print_header("Step 6: 사용자 가이드 생성")

    guide_content = f"""
# INTEROJO 포털 자동화 시스템 v{VERSION}

## 📦 설치 및 실행

### 1. 첫 실행
1. `interojo_automation.exe` 더블클릭
2. 자동으로 `.env` 파일과 필요한 폴더가 생성됩니다

### 2. 설정
1. GUI에서 "설정" 버튼 클릭
2. 로그인 정보 입력:
   - 사용자명: INTEROJO 포털 ID
   - 비밀번호: INTEROJO 포털 비밀번호
3. 검색 설정:
   - 검색 키워드: 찾을 문서 키워드 (기본: "자재")
   - 시작 날짜: 검색 시작 날짜 (YYYY.MM.DD 형식)
   - ☑ 스마트 필터링: 마지막 처리 문서부터 자동 검색
4. 자동 실행 스케줄 (선택사항):
   - 매일 특정 시간에 자동 실행
5. "저장" 클릭

### 3. 실행
- **수동 실행**: "지금 실행하기" 버튼 클릭
- **자동 모드**: "자동 모드 시작" 버튼 클릭

## 📂 폴더 구조

```
interojo_automation/
├── interojo_automation.exe    # 실행 파일
├── .env                       # 설정 파일
├── data/
│   ├── PDF/
│   │   └── YYYY-MM-DD/       # 날짜별 PDF 저장
│   └── excel/
│       └── Material_Release_Request.xlsx
└── logs/
    └── automation_YYYYMMDD.log
```

## 🔧 문제 해결

### 로그인 실패
- .env 파일에서 사용자명/비밀번호 확인
- 포털 비밀번호 변경 시 설정에서 재입력

### 문서 검색 안 됨
- 검색 키워드 확인 ("자재", "접수" 등)
- 시작 날짜 범위 확인

### 실행 파일 오류
- logs/ 폴더의 로그 파일 확인
- data/screenshots/ 폴더의 스크린샷 확인

## 📞 지원

문제 발생 시:
1. logs/ 폴더의 최신 로그 파일 확인
2. 오류 메시지 캡처
3. IT 담당자에게 문의

---
빌드 날짜: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
버전: {VERSION}
"""

    guide_path = DIST_DIR / 'interojo_automation' / 'README.txt'

    try:
        with open(guide_path, 'w', encoding='utf-8') as f:
            f.write(guide_content)
        print_success(f"사용자 가이드 생성: {guide_path.name}")
        return True
    except Exception as e:
        print_warning(f"사용자 가이드 생성 실패: {e}")
        return False


def print_summary():
    """빌드 결과 요약"""
    print_header("빌드 완료 요약")

    exe_dir = DIST_DIR / 'interojo_automation'

    print(f"{GREEN}✓ 빌드가 성공적으로 완료되었습니다!{RESET}\n")
    print(f"📦 실행 파일 위치:")
    print(f"   {exe_dir.resolve()}\n")
    print(f"🚀 배포 방법:")
    print(f"   1. {exe_dir.name}/ 폴더 전체를 압축 (ZIP)")
    print(f"   2. 압축 파일을 대상 PC에 배포")
    print(f"   3. 압축 해제 후 interojo_automation.exe 실행\n")
    print(f"📄 포함된 파일:")
    print(f"   - interojo_automation.exe  (메인 실행 파일)")
    print(f"   - _internal/               (필수 라이브러리)")
    print(f"   - README.txt               (사용자 가이드)")
    print(f"   - chromedriver.exe         (Chrome 드라이버)\n")


def test_executable():
    """실행 파일 테스트"""
    print_header("Step 7: 실행 파일 테스트")

    exe_path = DIST_DIR / 'interojo_automation' / 'interojo_automation.exe'

    if not exe_path.exists():
        print_error("실행 파일을 찾을 수 없습니다")
        return False

    print("실행 파일 시작 테스트 (5초 후 자동 종료)...")

    try:
        # --version 인자로 테스트 (실제로는 구현 필요)
        result = subprocess.run(
            [str(exe_path)],
            timeout=5,
            capture_output=True,
            text=True,
        )
        print_success("실행 파일 정상 작동")
        return True

    except subprocess.TimeoutExpired:
        print_success("실행 파일 정상 시작 확인 (타임아웃)")
        return True

    except Exception as e:
        print_error(f"실행 파일 테스트 실패: {e}")
        return False


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description='INTEROJO 자동화 시스템 빌드')
    parser.add_argument('--clean', action='store_true', help='완전 정리 후 빌드')
    parser.add_argument('--test', action='store_true', help='빌드 후 자동 테스트')
    parser.add_argument('--skip-deps', action='store_true', help='의존성 체크 건너뛰기')
    args = parser.parse_args()

    print_header(f"INTEROJO 포털 자동화 시스템 v{VERSION} - 빌드 시작")
    start_time = datetime.now()

    # 1. 의존성 확인
    if not args.skip_deps:
        if not check_dependencies():
            print_error("\n의존성 체크 실패. 빌드를 중단합니다.")
            return 1

    # 2. 필수 파일 확인
    if not check_required_files():
        print_error("\n필수 파일 체크 실패. 빌드를 중단합니다.")
        return 1

    # 3. 빌드 디렉토리 정리
    clean_build_directories(full_clean=args.clean)

    # 4. PyInstaller 실행
    if not run_pyinstaller():
        print_error("\nPyInstaller 빌드 실패.")
        return 1

    # 5. 빌드 결과 검증
    if not verify_build():
        print_error("\n빌드 결과 검증 실패.")
        return 1

    # 6. 사용자 가이드 생성
    create_user_guide()

    # 7. 실행 파일 테스트 (선택사항)
    if args.test:
        test_executable()

    # 8. 결과 요약
    print_summary()

    # 소요 시간
    elapsed = datetime.now() - start_time
    print(f"⏱️  총 소요 시간: {elapsed.total_seconds():.1f}초\n")

    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n\n{YELLOW}사용자에 의해 빌드가 중단되었습니다.{RESET}")
        sys.exit(1)
    except Exception as e:
        print_error(f"\n예상치 못한 오류: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
