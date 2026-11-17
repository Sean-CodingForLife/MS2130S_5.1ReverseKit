@echo off
setlocal
if "%~1"=="" (
  echo Drag a 5.1 wav file onto this .cmd to fix the channel order.
  echo.
  echo The card sends   FL, FR, LFE, FC, BL, BR
  echo Standard 5.1 is  FL, FR, FC, LFE, BL, BR
  echo So channel 3 and 4 are swapped; this tool swaps them back.
  pause
  exit /b 1
)
set "FF=D:\Programs\FFmpeg Upmix\ffmpeg\bin\ffmpeg.exe"
if not exist "%FF%" set "FF=ffmpeg"
echo Input : %~1
echo Output: %~dpn1_fixed.wav
echo.
"%FF%" -hide_banner -loglevel warning -i "%~1" -af "pan=5.1|c0=c0|c1=c1|c2=c3|c3=c2|c4=c4|c5=c5" -c:a pcm_s24le -y "%~dpn1_fixed.wav"
if errorlevel 1 (
  echo.
  echo FAILED. Is ffmpeg available?
) else (
  echo.
  echo Done: %~dpn1_fixed.wav
)
pause
