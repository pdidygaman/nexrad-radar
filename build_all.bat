@echo off
REM ── Build NEXRAD Radar: icon → exe → installer ───────────────────────
cd /d "%~dp0"
echo.
echo [1/3] Generating icon...
python make_icon.py || goto :err

echo.
echo [2/3] Building standalone app with PyInstaller (this takes a few minutes)...
python -m PyInstaller build.spec --noconfirm --clean || goto :err

echo.
echo [3/3] Building installer with Inno Setup...
set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo Inno Setup not found. Install it from https://jrsoftware.org/isdl.php
  echo The standalone app is still in: dist\NEXRAD Radar\
  goto :end
)
"%ISCC%" installer.iss || goto :err

echo.
echo ============================================================
echo  DONE.  Installer: installer\NEXRAD-Radar-Setup.exe
echo         Standalone: dist\NEXRAD Radar\NEXRAD Radar.exe
echo ============================================================
goto :end

:err
echo.
echo BUILD FAILED. See messages above.
exit /b 1

:end
pause
