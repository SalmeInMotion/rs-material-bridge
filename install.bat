@echo off
REM RS Material Bridge -- Windows launcher for the installer.
REM Uses your Python if you have one; otherwise borrows the Python that
REM ships inside Houdini or Cinema 4D, so nothing extra has to be installed.
setlocal enabledelayedexpansion
cd /d "%~dp0"

for %%P in (py.exe python.exe) do (
    where %%P >nul 2>nul && (
        if /i "%%P"=="py.exe" ( py -3 install.py & goto :done ) else ( python install.py & goto :done )
    )
)

for /d %%D in ("%ProgramFiles%\Side Effects Software\Houdini*") do (
    if exist "%%~fD\bin\hython.exe" (
        echo Using Python from %%~nxD
        "%%~fD\bin\hython.exe" install.py
        goto :done
    )
)

for /d %%D in ("%ProgramFiles%\Maxon Cinema 4D*") do (
    if exist "%%~fD\resource\modules\python\libs\win64\python.exe" (
        echo Using Python from %%~nxD
        "%%~fD\resource\modules\python\libs\win64\python.exe" install.py
        goto :done
    )
)

echo.
echo Could not find a Python interpreter.
echo Install Python from python.org, or run install.py from Houdini's
echo Python shell.
pause
exit /b 1

:done
if errorlevel 1 pause
endlocal
