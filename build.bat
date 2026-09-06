@echo off
setlocal

echo Building SC2026 Skill 50 Marking Tool...
echo.

python -m pip install -r requirements.txt
if errorlevel 1 goto :error

pyinstaller --noconfirm --onefile --windowed ^
    --name "SC2026_Marking_Tool" ^
    --add-data "maya_worker.py;." ^
    main.py

if errorlevel 1 goto :error

echo.
echo Build complete. The executable is at dist\SC2026_Marking_Tool.exe
goto :end

:error
echo.
echo Build FAILED - see the output above.
exit /b 1

:end
endlocal
