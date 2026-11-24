@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul || (echo Python이 필요합니다. https://www.python.org 에서 설치한 뒤 다시 실행하세요. & pause & exit /b 1)
python -m pip install --quiet --disable-pip-version-check -r requirements.txt || (echo 패키지 설치에 실패했습니다. & pause & exit /b 1)
set "PYW=pythonw"
where pythonw >nul 2>nul || set "PYW=python"
start "" %PYW% "%~dp0claude_usage_tray.py"
echo TokenView를 시작했습니다. 작업표시줄 오른쪽 아래(숨겨진 아이콘 ^) 를 확인하세요.
timeout /t 3 >nul
