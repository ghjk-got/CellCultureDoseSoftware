@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "APP=main.py"

if exist "%~dp0runtime\pythonw.exe" (
    start "" "%~dp0runtime\pythonw.exe" "%APP%"
    exit /b 0
)

set "CODEX_PYW=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"
if exist "%CODEX_PYW%" (
    start "" "%CODEX_PYW%" "%APP%"
    exit /b 0
)

where pythonw.exe >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw.exe "%APP%"
    exit /b 0
)

where pyw.exe >nul 2>nul
if %errorlevel%==0 (
    start "" pyw.exe -3 "%APP%"
    exit /b 0
)

where python.exe >nul 2>nul
if %errorlevel%==0 (
    python "%APP%"
    pause
    exit /b 0
)

echo 未找到可用的 Python 运行环境。
echo 请安装 Python 3.10 或更高版本，并勾选 Add Python to PATH。
pause
