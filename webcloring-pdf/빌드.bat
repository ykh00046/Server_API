@echo off
chcp 65001 > nul
echo ================================================
echo INTEROJO 실행 파일 빌드 v3.1.0
echo ================================================
echo.

REM 가상환경 확인 및 활성화
if exist .venv\Scripts\activate.bat (
    echo [1/3] 가상환경 활성화 중...
    call .venv\Scripts\activate.bat
) else (
    echo [1/3] 가상환경 없음, 시스템 Python 사용
)

REM 이전 빌드 삭제 (automation.spec은 유지)
echo [2/3] 이전 빌드 파일 정리 중...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
echo     - build/ 폴더 삭제
echo     - dist/ 폴더 삭제
echo     - automation.spec 파일 유지 (필수 파일)

REM 빌드 실행
echo [3/3] 빌드 시작...
echo.
echo 상세한 빌드 가이드: BUILD_GUIDE.md 참조
echo.
python -m PyInstaller automation.spec --noconfirm --clean

REM 결과 확인
if errorlevel 1 (
    echo.
    echo ================================================
    echo 빌드 실패!
    echo ================================================
    echo 로그를 확인하고 문제를 해결하세요.
    pause
    exit /b 1
)

echo.
echo ================================================
echo 빌드 완료!
echo 실행 파일 위치: dist\interojo_automation\
echo ================================================
echo.
echo 배포 방법:
echo   1. dist\interojo_automation\ 폴더 전체를 압축
echo   2. 대상 PC에 압축 해제
echo   3. interojo_automation.exe 실행
echo.
pause
