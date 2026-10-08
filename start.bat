@echo off
chcp 65001 >nul
title DAILY WORDLE

cd /d "%~dp0"

:MENU

cls

echo.
echo ====================================================
echo                  DAILY WORDLE
echo ====================================================
echo.
echo                 1. Play Wordle
echo                 2. Gacha
echo                 3. Sell
echo                 4. Fusion
echo                 5. Collection
echo                 6. Trade
echo                 7. Exit
echo ====================================================
echo.

choice /c 1234567 /n /m "Choose: "

if errorlevel 7 goto EXIT
if errorlevel 6 goto TRADE
if errorlevel 5 goto COLLECTION
if errorlevel 4 goto FUSION
if errorlevel 3 goto SELL
if errorlevel 2 goto GACHA
if errorlevel 1 goto PLAY


:PLAY

cls

python wordle.py

goto MENU


:GACHA

cls

python wordle.py gacha

echo.
echo Press any key...
pause >nul

goto MENU


:SELL

cls

python wordle.py sell

echo.
echo Press any key...
pause >nul

goto MENU


:FUSION

cls

python wordle.py fusion

echo.
echo Press any key...
pause >nul

goto MENU


:COLLECTION

cls

python wordle.py collection

echo.
echo Press any key...
pause >nul

goto MENU


:TRADE

cls

python trade.py

echo.
echo Press any key...
pause >nul

goto MENU


:EXIT

cls

echo.
echo Thanks for playing!
echo.

exit