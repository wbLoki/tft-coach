# Builds dist\TFT Coach.exe:  .venv\Scripts\python -m PyInstaller tft_coach.spec --noconfirm
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# The data files are baked in, so rebuild after refreshing the meta. Matches and .env stay out.
datas = [(f"data/{name}", "data") for name in ("set_data.json", "meta.json", "static.json")]
# RapidOCR loads its detector/recogniser modules by name at run time, from its own folder on sys.path:
# ship the sources along with the models, and list the submodules so their dependencies are found.
datas += collect_data_files("rapidocr_onnxruntime", include_py_files=True)

a = Analysis(["run_live.py"], datas=datas, hiddenimports=collect_submodules("rapidocr_onnxruntime"))
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, name="TFT Coach", console=False, upx=False)
