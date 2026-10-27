@echo off
echo =========================================================
echo Running PreGuard DB Automated Pytest Verification Suite
echo =========================================================
cd /d "%~dp0"
python -m pytest tests/test_preguard.py -v
pause
