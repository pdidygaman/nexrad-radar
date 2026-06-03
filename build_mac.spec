# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for NEXRAD Radar — macOS .app bundle
# Built on a macos-latest GitHub Actions runner (cannot be built on Windows).
from PyInstaller.utils.hooks import collect_all, collect_submodules

# Bundle static assets + the gazetteer (used for DOW geolocation when an OCR
# engine is available). The Windows-only .ps1 helpers are intentionally omitted.
datas = [('static', 'static'), ('icon.icns', '.'),
         ('gazetteer.tsv', '.'), ('version.py', '.')]
binaries = []
hiddenimports = []

for pkg in ['uvicorn', 'metpy', 'pyproj', 'botocore', 'boto3', 'webview',
            'pint', 'xarray', 'scipy']:
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

hiddenimports += collect_submodules('uvicorn')
hiddenimports += [
    'anyio', 'anyio._backends._asyncio',
    'uvicorn.lifespan.on', 'uvicorn.loops.auto', 'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets.auto',
    'scipy.signal', 'scipy.ndimage',
    # pywebview's macOS (Cocoa/WebKit) backend uses pyobjc:
    'webview.platforms.cocoa',
    'objc', 'Foundation', 'AppKit', 'WebKit', 'Quartz', 'CoreFoundation',
    'Cocoa',
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
              'IPython', 'jupyter', 'notebook', 'pytest', 'gtk',
              'clr', 'clr_loader', 'pythonnet'],   # Windows WebView2 backend — not used on mac
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
    console=False,
    icon='icon.icns',
)

coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False,
    name='NEXRAD Radar',
)

app = BUNDLE(
    coll,
    name='NEXRAD Radar.app',
    icon='icon.icns',
    bundle_identifier='com.pdidygaman.nexradradar',
    info_plist={
        'CFBundleName': 'NEXRAD Radar',
        'CFBundleDisplayName': 'NEXRAD Radar',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleVersion': '1.0.0',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '11.0',
        'LSApplicationCategoryType': 'public.app-category.weather',
        'NSHumanReadableCopyright': 'Free / MIT',
        # We don't open camera/mic; declare nothing sensitive.
    },
)
