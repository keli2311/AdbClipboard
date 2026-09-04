$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$staging = Join-Path $root "build\pc_staging"
New-Item -ItemType Directory -Force -Path $staging | Out-Null

Write-Host "==> 准备资源文件 ..."

# APK（推送安装用）
Copy-Item (Join-Path $root "app\build\outputs\apk\debug\AdbClipboard-3.2_6-debug.apk") `
    (Join-Path $staging "app.apk") -Force

# adb 及其运行库（捆绑进软件，不依赖系统 PATH）
$adbDir = if (Test-Path "C:\adb") { "C:\adb" } else { "C:\Users\admin\.android-sdk\platform-tools" }
foreach ($f in @("adb.exe", "AdbWinApi.dll", "AdbWinUsbApi.dll", "libwinpthread-1.dll")) {
    Copy-Item (Join-Path $adbDir $f) (Join-Path $staging $f) -Force
}

# 图标
$png = Join-Path $root "app\src\main\res\drawable-xxhdpi\ic_launcher.png"
py -X utf8 -c "from PIL import Image; im=Image.open(r'$png').convert('RGBA'); im.save(r'$staging\app.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])"
Copy-Item $png (Join-Path $staging "ic_launcher.png") -Force

Write-Host "==> PyInstaller 打包 ..."
$env:PYTHONUTF8 = "1"
$dataApk = "$(Join-Path $staging 'app.apk');."
$dataAdb = "$(Join-Path $staging 'adb.exe');."
$dataAdbWinApi = "$(Join-Path $staging 'AdbWinApi.dll');."
$dataAdbWinUsbApi = "$(Join-Path $staging 'AdbWinUsbApi.dll');."
$dataWinpthread = "$(Join-Path $staging 'libwinpthread-1.dll');."
$dataIcon = "$(Join-Path $staging 'ic_launcher.png');."

py -m PyInstaller --noconfirm --onefile --windowed --clean `
    --name "AdbClipboard助手" `
    --icon (Join-Path $staging "app.ico") `
    --add-data $dataApk `
    --add-data $dataAdb `
    --add-data $dataAdbWinApi `
    --add-data $dataAdbWinUsbApi `
    --add-data $dataWinpthread `
    --add-data $dataIcon `
    (Join-Path $root "pc_app.py")

Write-Host ""
Write-Host "==> 完成：$(Join-Path $root 'dist\AdbClipboard助手.exe')"
