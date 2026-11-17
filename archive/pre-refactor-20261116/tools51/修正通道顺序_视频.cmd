@echo off
setlocal
if "%~1"=="" (
  echo Drag a recorded video file ^(.mkv / .mp4^) onto this .cmd.
  echo.
  echo It rewrites the audio track with FC and LFE swapped, video is copied
  echo without re-encoding. Output: same name with _fixed.mkv
  pause
  exit /b 1
)
set "FF=D:\Programs\FFmpeg Upmix\ffmpeg\bin\ffmpeg.exe"
if not exist "%FF%" set "FF=ffmpeg"
echo Input : %~1
echo Output: %~dpn1_fixed.mkv
echo.
"%FF%" -hide_banner -loglevel warning -i "%~1" -af "pan=5.1|c0=c0|c1=c1|c2=c3|c3=c2|c4=c4|c5=c5" -c:v copy -c:a pcm_s24le -y "%~dpn1_fixed.mkv"
if errorlevel 1 (
  echo.
  echo FAILED - is ffmpeg on PATH or at the expected location?
) else (
  echo.
  echo Done: %~dpn1_fixed.mkv
)
pause
