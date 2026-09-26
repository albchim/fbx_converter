@echo off
setlocal
cd /d "%~dp0"

rem Download uv on first run
if not exist "%~dp0thirdparty\uv.exe" (
    echo First run: downloading uv...
    powershell -NoProfile -Command "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol='Tls12'; $z=Join-Path $env:TEMP 'uv-download.zip'; Invoke-WebRequest 'https://github.com/astral-sh/uv/releases/download/0.9.8/uv-x86_64-pc-windows-msvc.zip' -OutFile $z; Expand-Archive $z -DestinationPath '%~dp0thirdparty' -Force; Remove-Item $z"
    if not exist "%~dp0thirdparty\uv.exe" (echo Could not download uv. Check your internet connection. & pause & exit /b 1)
)

for /f "usebackq delims=" %%I in (`powershell -NoProfile -STA -Command "Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.OpenFileDialog; $d.Title = 'Select GLB file'; $d.Filter = 'glTF binary (*.glb)|*.glb|glTF (*.gltf)|*.gltf|All files (*.*)|*.*'; if ($d.ShowDialog() -eq 'OK') { $d.FileName }"`) do set "INPUT=%%I"
if not defined INPUT (echo No input file selected. & pause & exit /b 1)

for /f "usebackq delims=" %%O in (`powershell -NoProfile -STA -Command "Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.SaveFileDialog; $d.Title = 'Save Maya scene as (a project folder is created next to it)'; $d.Filter = 'Maya ASCII (*.ma)|*.ma'; $d.DefaultExt = 'ma'; $d.FileName = [IO.Path]::GetFileNameWithoutExtension('%INPUT%') + '.ma'; $d.OverwritePrompt = $true; if ($d.ShowDialog() -eq 'OK') { $d.FileName }"`) do set "OUTFILE=%%O"
if not defined OUTFILE (echo No output file selected. & pause & exit /b 1)

"%~dp0thirdparty\uv.exe" run --project "%~dp0." "%~dp0src\main.py" "%INPUT%" "%OUTFILE%"
if errorlevel 1 (echo Conversion failed. & pause & exit /b 1)
echo Done.
pause
