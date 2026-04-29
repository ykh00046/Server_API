@echo off
chcp 65001 > nul
echo ================================================
echo INTEROJO 포털 자동화 시스템
echo ================================================
echo.

REM 가상환경 확인 및 활성화
if exist .venv\Scripts\activate.bat (
    echo [1/2] 가상환경 활성화 중...
    call .venv\Scripts\activate.bat
) else (
    echo [1/2] 가상환경 없음, 시스템 Python 사용
)

REM 프로그램 실행
echo [2/2] GUI 실행 중...
echo.
python main.py

REM 오류 확인
if errorlevel 1 (
    echo.
    echo ================================================
    echo 오류가 발생했습니다!
    echo ================================================
    pause
    exit /b 1
)

echo.
echo ================================================
echo 프로그램 종료
echo ================================================
pause
