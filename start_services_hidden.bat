@echo off
chcp 65001 > nul
cd /d "%~dp0"

:: Start Manager Hidden (inherits hidden window from VBS)
python manager.py
