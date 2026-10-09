# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


project_root = Path(SPECPATH).resolve()
matlab_root = project_root / "pyfnirs_converter" / "matlab"
if not matlab_root.is_dir():
    raise RuntimeError(f"PYfNIRs MATLAB helper tree is missing: {matlab_root}")

datas = [
    (str(project_root / "pyfnirs_converter" / "capabilities.json"), "pyfnirs_converter"),
]
for source in sorted(matlab_root.rglob("*")):
    if source.is_file() and "__pycache__" not in source.parts:
        destination = Path("pyfnirs_converter") / "matlab" / source.relative_to(matlab_root).parent
        datas.append((str(source), destination.as_posix()))

a = Analysis(
    [str(project_root / "launch_pyfnirs.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "tkinter"],
    noarchive=False,
    optimize=0,
)

# Qt's Windows build uses the operating-system ICU API. PyInstaller otherwise
# collects the first icuuc.dll found on PATH (for example, an incompatible
# versioned ICU from Poppler), which can break PySide6.QtCore imports.
a.binaries = [
    item
    for item in a.binaries
    if Path(item[0]).name.casefold() not in {"icuuc.dll", "icudt78.dll"}
]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PYfNIRs-DataConversion",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PYfNIRs-DataConversion",
)
