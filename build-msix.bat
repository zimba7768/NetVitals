@echo off
rem ---------------------------------------------------------------------------
rem  Build the Microsoft Store package.
rem
rem  1. PyInstaller builds a folder (not a single file — a package needs the
rem     real layout).
rem  2. tools\make_msix.py stages it with the manifest and tile images.
rem  3. makeappx packs it into a .msix. No signing: the Store signs what it
rem     accepts, and a package signed with your own certificate can fail
rem     validation on a publisher mismatch. Install it locally with
rem     Add-AppxPackage -AllowUnsigned.
rem ---------------------------------------------------------------------------
cd /d "%~dp0"
call "%~dp0_find-python.bat"
if not defined PYEXE (
    echo No Python 3.10+ found. Run install.bat first.
    pause
    exit /b 1
)

echo Building the application folder...
"%PYEXE%" -m PyInstaller --noconfirm --clean netvitals-dir.spec
if errorlevel 1 goto :failed

echo.
echo Staging the package...
"%PYEXE%" "%~dp0tools\make_msix.py"
if errorlevel 1 goto :failed

echo.
echo Done. The command to pack it is printed above.
echo makeappx comes with the Windows SDK. If it is not on your PATH, open a
echo "Developer Command Prompt for VS", or add the SDK's bin\x64 folder.
pause
exit /b 0

:failed
echo.
echo Build failed - see the messages above.
pause
exit /b 1
