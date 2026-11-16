@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "CCDS_DATA_DIR=%~dp0DemoData"
set "CCDS_CONFIG=%~dp0DemoData\config.json"
start "" "%~dp0CellCultureDoseSoftware.exe"
