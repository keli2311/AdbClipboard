# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:/Users/admin/Documents/ChatGPT/PC 安卓剪切板同步/AdbClipboard/pc_app.py'],
    pathex=[],
    binaries=[],
    datas=[('C:/Users/admin/Documents/ChatGPT/PC 安卓剪切板同步/AdbClipboard/build/pc_staging/app.apk', '.'), ('C:/Users/admin/Documents/ChatGPT/PC 安卓剪切板同步/AdbClipboard/build/pc_staging/adb.exe', '.'), ('C:/Users/admin/Documents/ChatGPT/PC 安卓剪切板同步/AdbClipboard/build/pc_staging/AdbWinApi.dll', '.'), ('C:/Users/admin/Documents/ChatGPT/PC 安卓剪切板同步/AdbClipboard/build/pc_staging/AdbWinUsbApi.dll', '.'), ('C:/Users/admin/Documents/ChatGPT/PC 安卓剪切板同步/AdbClipboard/build/pc_staging/libwinpthread-1.dll', '.'), ('C:/Users/admin/Documents/ChatGPT/PC 安卓剪切板同步/AdbClipboard/build/pc_staging/ic_launcher.png', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AdbClipboard助手',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:/Users/admin/Documents/ChatGPT/PC 安卓剪切板同步/AdbClipboard/build/pc_staging/app.ico'],
)
