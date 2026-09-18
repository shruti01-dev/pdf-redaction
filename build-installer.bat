@echo off
setlocal
cd /d "%~dp0"

echo.
echo Building PDF Redaction desktop installer ...
echo.

python -m pip install -U pip
python -m pip install -r requirements.txt
python -m pip install -U pyinstaller
if exist "assets\make_icon.py" python "assets\make_icon.py"
python -m PyInstaller --noconfirm --clean pdf_redaction.spec
if errorlevel 1 exit /b 1

set ISCC=
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
if "%ISCC%"=="" (
  echo Inno Setup not found. Install with:
  echo   winget install --id JRSoftware.InnoSetup -e
  echo Then run this file again.
  exit /b 1
)

"%ISCC%" "installer\pdf_redaction.iss"
echo.
echo Installer: installer_output\PDF-Redaction-Setup.exe
echo Users can install this like a normal Windows app.
endlocal
