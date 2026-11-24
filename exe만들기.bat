@echo off
chcp 65001 >nul
cd /d "%~dp0"
where python >nul 2>nul || (echo Python이 필요합니다. & pause & exit /b 1)
python -m pip install --quiet --disable-pip-version-check -r requirements.txt pyinstaller || (echo 패키지 설치에 실패했습니다. & pause & exit /b 1)
python -m PyInstaller --onefile --noconsole --name ClaudeUsageTray claude_usage_tray.py || (echo exe 만들기에 실패했습니다. & pause & exit /b 1)
echo 완료: dist\ClaudeUsageTray.exe
pause
