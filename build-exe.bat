@echo off
cd /d "%~dp0"
echo.
echo Building PDF Redaction desktop app ...
echo.

python -m pip install -U pip
python -m pip install -r requirements.txt
python -m pip install -U pyinstaller
if exist "assets\make_icon.py" python "assets\make_icon.py"
python -m PyInstaller --noconfirm pdf_redaction.spec

if exist "dist\PDF Redaction\PDF Redaction.exe" (
  echo.
  echo DONE!
  echo App folder: dist\PDF Redaction\
  echo.
  echo To make a Setup.exe that people can install:
  echo   build-installer.bat
  echo.
) else (
  echo Build failed.
)

pause
