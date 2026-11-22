@echo off
REM Builds Balanse into dist\Balanse (PyInstaller), then the setup file installer_output\BalanseSetup.exe (Inno Setup).
cd /d "%~dp0"

python -m pip install --upgrade pyinstaller pywebview
if errorlevel 1 goto :fail

python -m PyInstaller --noconfirm --windowed --name Balanse ^
  --collect-all streamlit --copy-metadata streamlit ^
  --add-data "app.py;." --add-data "balanse;balanse" --add-data ".streamlit;.streamlit" ^
  run_balanse.py
if errorlevel 1 goto :fail

set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
  echo Inno Setup 6 is not installed. Install it from https://jrsoftware.org/isinfo.php and run this file again.
  goto :fail
)
%ISCC% installer.iss
if errorlevel 1 goto :fail

echo.
echo Done: installer_output\BalanseSetup.exe
goto :eof

:fail
echo Build stopped with an error.
exit /b 1
