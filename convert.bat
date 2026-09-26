@echo off
setlocal
cd /d "%~dp0"

for /f "usebackq delims=" %%I in (`powershell -NoProfile -STA -Command "Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.OpenFileDialog; $d.Title = 'Select GLB file'; $d.Filter = 'glTF binary (*.glb)|*.glb|glTF (*.gltf)|*.gltf|All files (*.*)|*.*'; if ($d.ShowDialog() -eq 'OK') { $d.FileName }"`) do set "INPUT=%%I"
if not defined INPUT (echo No input file selected. & pause & exit /b 1)

for /f "usebackq delims=" %%O in (`powershell -NoProfile -STA -Command "Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.SaveFileDialog; $d.Title = 'Save FBX as'; $d.Filter = 'FBX (*.fbx)|*.fbx'; $d.DefaultExt = 'fbx'; $d.FileName = [IO.Path]::GetFileNameWithoutExtension('%INPUT%') + '.fbx'; $d.OverwritePrompt = $true; if ($d.ShowDialog() -eq 'OK') { $d.FileName }"`) do set "OUTFILE=%%O"
if not defined OUTFILE (echo No output file selected. & pause & exit /b 1)

uv run main.py "%INPUT%" "%OUTFILE%"
if errorlevel 1 (echo Conversion failed. & pause & exit /b 1)
echo Done.
pause
