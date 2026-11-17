@echo off
cd /d "%~dp0"
title MS2130S restore stock firmware

echo ============================================================
echo   MS2130S capture card -- restore stock firmware
echo ============================================================
echo.
echo   target : ..\firmware\ms2130s_backup.bin  (98356 bytes, stock)
echo   tool   : ..\tools\ms213x_flash.exe      (v0.10)
echo   ETA    : about 6 minutes
echo.
echo   DO NOT unplug the USB cable while it is running.
echo.

set "FLASH=..\tools\ms213x_flash.exe"
set "FW=..\firmware\ms2130s_backup.bin"

if not exist "%FLASH%" goto nofile
if not exist "%FW%" goto nofile

echo [1/2] writing ...
echo.
"%FLASH%" -w "%FW%"
if errorlevel 1 goto failed

echo.
echo [2/2] SUCCESS - the line above should read:
echo       "Successfully written and verified flash"
echo.
echo   Next: unplug the card from USB, wait 10 seconds, plug it back in.
echo   Then tell me, and I will check whether the 6-channel endpoint appears.
goto end

:failed
echo.
echo [2/2] FAILED
echo.
echo   Nothing was written.  Two possibilities:
echo     - "Could not open device": the card is still invisible to Windows
echo       even inside WinPE.  Report this back, the card is unchanged.
echo     - an erase/write error: stop, do NOT unplug, report the text.
goto end

:end
echo.
echo ------------------------------------------------------------
echo  Take a photo of this window and send it back.
echo ------------------------------------------------------------
pause
exit /b 0

:nofile
echo [ERROR] required file missing:
echo         %FLASH%
echo         %FW%
pause
exit /b 1
