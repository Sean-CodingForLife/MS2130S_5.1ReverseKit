@echo off
cd /d "%~dp0"
title NS2 5.1 录制
echo ============================================================
echo   NS2 5.1 声道录制
echo ============================================================
echo.
echo   采集卡必须插在 USB 3 口上（插 USB 2 口会退回 2 声道）
echo.
set /p SEC=要录多少秒？（直接回车 = 60）:
if "%SEC%"=="" set SEC=60
echo.
echo 开始录制 %SEC% 秒…… 现在去 NS2 上玩你想录的内容
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0rec51.ps1" -Seconds %SEC%
echo.
echo ------------------------------------------------------------
echo 录好的文件在「视频」文件夹里，文件名 ns2_51_日期_时间.wav
echo ------------------------------------------------------------
pause
