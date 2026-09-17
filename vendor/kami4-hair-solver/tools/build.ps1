param([switch]$Configure)
$ErrorActionPreference='Stop'
$repo=Split-Path $PSScriptRoot -Parent
$vswhere='C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe'
$vs=& $vswhere -latest -version '[17.0,18.0)' -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$vcvars=Join-Path $vs 'VC\Auxiliary\Build\vcvars64.bat'
$compilerEnv=& cmd /d /c "call `"$vcvars`" >nul && set"
foreach($line in $compilerEnv){if($line -match '^([^=]+)=(.*)$'){[Environment]::SetEnvironmentVariable($matches[1],$matches[2],'Process')}}
$env:VSLANG='1033'
if($Configure -or !(Test-Path "$repo/build/build.ninja")) {
 & cmake -S $repo -B "$repo/build" -G Ninja -DCMAKE_BUILD_TYPE=Release "-DCMAKE_CXX_COMPILER=$((Get-Command cl.exe).Source)" '-DCMAKE_CUDA_COMPILER=C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.9/bin/nvcc.exe'
 if($LASTEXITCODE){throw 'Configure failed'}
}
& cmake --build "$repo/build" --parallel 4
if($LASTEXITCODE){throw 'Build failed'}
& cmake --install "$repo/build" --prefix "$repo/extension"
if($LASTEXITCODE){throw 'Install failed'}
