@echo off
REM Builds "dist\4nextech Time\4nextech Time.exe" and, if Inno Setup is installed, the installer.
REM Run on Windows with Python 3.10+ installed.
cd /d "%~dp0"
python -m venv buildenv || goto :err
call buildenv\Scripts\activate || goto :err
pip install -r requirements-build.txt || goto :err
pyinstaller --noconfirm --clean --windowed --name "4nextech Time" ^
  --icon static\icons\app.ico ^
  --add-data "templates;templates" --add-data "static;static" ^
  --hidden-import zk --hidden-import PIL.ImageTk --collect-data reportlab ^
  launcher.py || goto :err
echo.
echo Program built: dist\4nextech Time\4nextech Time.exe
where iscc >nul 2>nul && (iscc installer.iss && echo Installer built: installer_output\4nextech-Time-Setup.exe) || echo Inno Setup not found - install it from jrsoftware.org to make Setup.exe, then run: iscc installer.iss
pause
exit /b 0
:err
echo Build failed.
pause
exit /b 1
