# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for LeadHunter Pro GUI.

Build command:
    pyinstaller leadhunter_gui.spec --clean --noconfirm

Output:  dist/LeadHunterPro.exe  (single file, no console window)

NOTE: Playwright browser binaries are NOT bundled — run setup.bat first.
"""

import os
import customtkinter

block_cipher = None
CTK_PATH = os.path.dirname(customtkinter.__file__)

a = Analysis(
    ['gui_main.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        # CustomTkinter theme assets (required at runtime)
        (CTK_PATH, 'customtkinter'),
        # .env template — user places their real .env next to the EXE
        ('.env.example', '.'),
    ],
    hiddenimports=[
        'customtkinter',
        'customtkinter.windows',
        'customtkinter.windows.widgets',
        'customtkinter.windows.widgets.theme',
        'sqlalchemy',
        'sqlalchemy.dialects.sqlite',
        'sqlalchemy.orm',
        'sqlalchemy.ext.declarative',
        'playwright',
        'playwright.async_api',
        'playwright.sync_api',
        'aiohttp',
        'aiohttp.connector',
        'beautifulsoup4',
        'bs4',
        'openpyxl',
        'openpyxl.styles',
        'anthropic',
        'python_dotenv',
        'dotenv',
        'rich',
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.filedialog',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter.test',
        'test',
        'unittest',
        'pytest',
        'matplotlib',
        'numpy',
        'pandas',
        'scipy',
        'PIL',
    ],
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
    name='LeadHunterPro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,       # No console window — GUI only
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='gui/assets/icon.ico' if os.path.exists('gui/assets/icon.ico') else None,
    onefile=True,
)
