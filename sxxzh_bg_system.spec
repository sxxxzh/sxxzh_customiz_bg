# -*- mode: python ; coding: utf-8 -*-

import sys
import os

# 获取当前目录
current_dir = os.getcwd()

# 分析需要包含的文件（单文件外置资源，打包不内置）
datas = []

# 添加日志目录
logs_dir = os.path.join(current_dir, 'logs')
if not os.path.exists(logs_dir):
    os.makedirs(logs_dir)

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[current_dir],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'win32gui',
        'win32con',
        'win32api',
        'win32process',
        'pythoncom',
        'pystray',
        'PIL',
        'PIL.Image',
        'PIL.ImageDraw',
        'target_manager',
        'window_detector',
        'bg_creator'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='sxxzh_bg_system',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 设置为False以隐藏控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(current_dir, 'logo.ico')
)

# 单文件模式：不使用 COLLECT，直接生成独立 EXE