@echo off
rem ---------------------------------------------------------------------------
rem  Commit and push a change, then optionally tag a release.
rem
rem  Runs the test suite first and stops if it fails, writes the commit message
rem  outside the repository (a message file written *inside* it was committed by
rem  accident twice), and offers the tag that matches APP_VERSION.
rem ---------------------------------------------------------------------------
cd /d "%~dp0"
call "%~dp0_find-python.bat"
if not defined PYEXE (
    echo No Python 3.10+ found. Run install.bat first.
    pause
    exit /b 1
)
"%PYEXE%" "%~dp0tools\push_update.py" %*
echo.
pause
