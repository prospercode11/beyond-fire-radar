# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules


hidden_imports = (
    collect_submodules("app")
    + collect_submodules("alembic")
    + collect_submodules("uvicorn")
)

a = Analysis(
    ["backend_entrypoint.py"],
    pathex=["../apps/api"],
    binaries=[],
    datas=[
        ("../apps/api/alembic.ini", "apps/api"),
        ("../apps/api/migrations", "apps/api/migrations"),
    ],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "mypy", "ruff"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="beyond-fire-radar-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="beyond-fire-radar-backend",
)
