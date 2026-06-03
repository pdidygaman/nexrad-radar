# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for NEXRAD Radar (onedir GUI app)
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = [('static', 'static'), ('icon.ico', '.'),
         ('gazetteer.tsv', '.'), ('ocr_win.ps1', '.'),
         ('version.py', '.')]
binaries = []
hiddenimports = []

# Pull data files + submodules for packages PyInstaller can't fully trace
for pkg in ['uvicorn', 'metpy', 'pyproj', 'botocore', 'boto3', 'webview',
            'pint', 'xarray']:
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

hiddenimports += collect_submodules('uvicorn')
hiddenimports += [
    'anyio', 'anyio._backends._asyncio',
    'uvicorn.lifespan.on', 'uvicorn.loops.auto', 'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets.auto',
    'clr_loader', 'clr',                 # pythonnet / EdgeChromium backend
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
              'IPython', 'jupyter', 'notebook', 'pytest', 'gtk'],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='NEXRAD Radar',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # GUI app — no console window
    icon='icon.ico',
)

coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False,
    name='NEXRAD Radar',
)
