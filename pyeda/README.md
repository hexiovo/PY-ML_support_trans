# PYEDA EDA 数据转换器

读取已完成的 PYEDA 结果包，导出 PYML 可读取的 EDA 特征表、有限值掩码、特征定义与来源哈希。转换范围可选择参与者任务角色汇总、参与者暴露汇总或记录级窗口。记录级默认保留有效窗口。

从 [Release](https://github.com/hexiovo/PY-ML_support_trans/releases) 下载 Windows ZIP 并完整解压。双击 `PYEDA-DataConversion.exe`，或在 PYML 的“插件 → 设置…”中选择包含 EXE、`pyml-plugin.json` 与 `_internal/` 的目录。源码版可在设置中选择本 `pyeda` 目录和 Python 3.12 的 `pythonw.exe`。

输入目录包含 `manifest.json`、`summary.json`、`intake/analysis_settings.json`、`intake/feature_definitions.csv` 和对应来源的 `features/participant_task_role_features.csv`、`features/participant_feature_exposure.csv` 或 `features/records/*.csv.gz`。批处理使用 Python 标准库。

```powershell
python -X utf8 launch_eda.py --input <PYEDA结果目录> --inspect
python -X utf8 launch_eda.py --input <PYEDA结果目录> --output <新输出目录> --no-open
```

无参数打开进度窗口。默认只导出已登记的 EDA 特征、来源要求的身份列和可用的质控状态。身份列用 `meta__` 标记，以便按独立单位分组。明确需要结果列时，可用 `--include-outcomes` 导出源分析设置登记的列。缺失和非有限特征由 `valid_mask.csv` 标出；用于建模前可用 [PYML 的特征处理示例](https://github.com/hexiovo/PY-ML/tree/master/examples/pyeda) 统一为空值。输出目录含来源和身份信息，请保存在本地。

Windows 构建使用装有 PyInstaller 6.22.3 的 Python 3.12 x64 环境。运行 `./build.ps1 -Python <python.exe>`，生成 EXE 文件夹、ZIP 和 SHA-256 校验文件。
