from PyInstaller.utils.hooks import collect_submodules
from pathlib import Path
root = Path(SPECPATH).parent
modules = collect_submodules('ros')
engine_sources = [(str(root/'ros'/'lib'/(name+'.py')),'ros/lib') for name in ('notebook_coverage','notebook_trace')]
a = Analysis([str(root/'desktop'/'backend_entry.py')], pathex=[str(root)], binaries=[], datas=[(str(root/'ros'/'portal'),'ros/portal'), (str(root/'assets'),'assets'), (str(root/'VERSION'),'.'), (str(root/'references'),'references'), (str(root/'skills'),'skills'), (str(root/'agents'),'agents'), (str(root/'extensions'),'extensions')] + engine_sources, hiddenimports=modules, hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=['numpy','torch','transformers','matplotlib','PIL.ImageTk','tkinter','PySide6','PyQt5'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz,a.scripts,[],exclude_binaries=True,name='research-os-backend',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=True)
coll = COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='research-os-backend')
