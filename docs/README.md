# PY-ML 数据转换插件

仓库：[PY-ML_support_trans](https://github.com/hexiovo/PY-ML_support_trans)。

仓库根目录只包含三个内容目录：

- `docs`：使用说明、兼容范围、验证摘要和 `version.md`。
- `hypereeg`：HyperEEG 转换器源码、启动入口、依赖清单和构建配置。
- `pyfnirs`：PYfNIRs 转换器源码、启动入口、依赖清单和构建配置。

GitHub 上传源码和文档。本机的 EXE、`_internal` 依赖目录及成品清单保留在各自转换器目录，通过目录内的 `.gitignore` 排除，不提交到 Git。GitHub 不包含 `prompts`、`tests`、测试工具或开发环境。

## 本机插件选择

在 PY-ML 中选择以下目录：

- HyperEEG：`F:\桌面\程序\PY-ML-support\hypereeg`，对应“插件 → 设置…”。
- PYfNIRs：`F:\桌面\程序\PY-ML-support\pyfnirs`，对应“格式 → 数据转换 → PYfNIRs 设置…”。

每个本机目录均保留 EXE、`pyml-plugin.json` 和完整 `_internal`，无需指定外部 Python。只复制 EXE 无法运行；从 GitHub 克隆的源码需要自行安装依赖并构建，不包含本机成品。

操作方法：[HyperEEG 使用说明](HyperEEG使用说明.md)、[PYfNIRs 使用说明](PYfNIRs转换器使用说明.md)。能力边界见[兼容矩阵](compatibility.md)，版本变更见[版本记录](version.md)。原始数据和转换结果留在本地。

## 源码运行

在仓库根目录进入对应转换器目录，以已安装的 Python 3.12 创建其独立环境并安装依赖，例如：

```powershell
cd hypereeg
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -X utf8 -B launch.py
```

PYfNIRs 使用 `pyfnirs` 目录，以同样方式安装该目录的依赖，然后运行：

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m pyfnirs_converter
```

## 构建

构建建议 Python 3.12.14；安装对应目录的 `requirements-lock.txt`。HyperEEG 在 `hypereeg` 中运行 `./packaging/build.ps1`。PYfNIRs 在 `pyfnirs` 中运行 `./build_pyfnirs.ps1`，按脚本参数提供外部合成 Study 导出及新的验证输出目录；需要验证原生 MAT 时另提供合成 MAT 和 MATLAB 程序路径。

构建脚本的输出分别位于转换器自己的 `dist` 和 `build` 下。重新构建后，在主程序中选择实际包含完整成品与 `pyml-plugin.json` 的目录。仓库不保留 tests、测试夹具或临时验证输出。
