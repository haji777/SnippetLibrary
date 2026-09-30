@echo off
rem ---------------------------------------------------------------
rem  Snippet Library viewer launcher. Copy this per project and edit:
rem    SNIPPETLIB_ROOT   library of this project (default: <repo>\snippetLibrary)
rem    SNIPPETLIB_USER   override the Windows user name
rem    SNIPPETLIB_LINKS  extra libraries to show, separated by ;
rem    SNIPPETLIB_PYTHON full path of a python.exe (3.7+) to force one
rem ---------------------------------------------------------------
rem set SNIPPETLIB_ROOT=P:\MyProject\snippetLibrary
rem set SNIPPETLIB_USER=someone
rem set SNIPPETLIB_LINKS=P:\OtherProject\snippetLibrary;P:\Studio\snippetLibrary

setlocal
cd /d "%~dp0"
rem the viewer only needs the standard library: never inherit a DCC python env
set PYTHONHOME=
set PYTHONPATH=
set PYTHONUTF8=1

if defined SNIPPETLIB_PYTHON set PY="%SNIPPETLIB_PYTHON%"
if defined PY goto run

rem 1) python launcher  2) python on PATH (the Microsoft Store stub fails this test)
py -3 -c "import sys" >nul 2>nul && set "PY=py -3" && goto run
python -c "import sys" >nul 2>nul && set "PY=python" && goto run

rem 3) no system python: borrow the one bundled with Houdini / Nuke
for /d %%H in ("%ProgramFiles%\Side Effects Software\Houdini *") do for /d %%P in ("%%H\python3*") do if exist "%%P\python.exe" set PY="%%P\python.exe"
if defined PY goto run
for /d %%N in ("%ProgramFiles%\Nuke*") do if exist "%%N\python.exe" set PY="%%N\python.exe"
if defined PY goto run

echo Python 3 was not found. Install Python 3 or set SNIPPETLIB_PYTHON in this bat.
pause
exit /b 1

:run
%PY% viewer\server.py %*
if errorlevel 1 pause
