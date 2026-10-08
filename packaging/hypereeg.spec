from pathlib import Path
import sys

if sys.version_info[:3] == (3, 12, 0):
    raise SystemExit('Use Python 3.12.14 (3.12.0 has a PyInstaller code.replace bug).')

root = Path(SPECPATH).parent
a = Analysis([str(root / 'launch.py')], pathex=[str(root)], binaries=[],
    datas=[(str(root / 'hypereeg_converter/matlab'), 'hypereeg_converter/matlab')],
    hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=['scipy', 'matplotlib', 'tkinter'], noarchive=False)
# Qt imports the Windows system ICU symbols. Poppler's PATH-visible DLL has
# versioned ICU symbols and must never shadow the Windows system library.
a.binaries = [item for item in a.binaries if Path(item[0]).name.casefold() != 'icuuc.dll']
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='PYML-DataConversion',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False, console=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='PYML-DataConversion')
