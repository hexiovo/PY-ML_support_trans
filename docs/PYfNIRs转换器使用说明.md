# PYfNIRs → PY-ML 转换器使用说明

本工具在本机把明确选择的 PYfNIRs 输出整理成 PY-ML 可读取的特征矩阵。它不会根据文件名、表格行号或数组下标猜测观察身份、标签或特征含义。

## 发行版与 PY-ML 主程序入口

当前 Windows 发行目录为 `F:\桌面\程序\PY-ML-support\pyfnirs`，入口 EXE 为 `F:\桌面\程序\PY-ML-support\pyfnirs\PYfNIRs-DataConversion.exe`。启动时保留并复制整个 `PYfNIRs-DataConversion` 目录，包括 `_internal`、EXE 和 `pyml-plugin.json`；不要单独移动 EXE。需要放到其他位置时，完整复制目录，再在 PY-ML 设置中选择新目录。

发行清单 `pyml-plugin.json` 使用 `source_project=PYfNIRs` 标识来源。通过 PY-ML 源码主程序接入时，运行 `F:\桌面\程序\PY-ML\run_pyml_workbench.bat`，在菜单中打开 **格式 → 数据转换 → PYfNIRs 设置…**，选择上面的发行目录并保存；随后从 **格式 → 数据转换 → PYfNIRs** 启动转换器。PYfNIRs 使用独立设置槽，不会覆盖“插件”菜单的通用数据转换设置。未配置或所选目录无效时，PYfNIRs 菜单项保持禁用。

本次验证使用上述源码 launcher 与正式发行 EXE；不会重建或替换已安装的 PY-ML 桌面程序。桌面版快捷方式是否出现该菜单，取决于后续是否另行发布桌面版更新。

## 输入和支持范围

工具可检查 `.mat` 文件和符合转换契约的 `study_export.json`。读取原生 MATLAB 文件时需要本机安装且有许可的外部 MATLAB；本次原生 MAT 验证使用 MATLAB R2023a，需在界面中选择 `matlab.exe`。符合契约的 `study_export.json` 由工具直接读取，不需要 MATLAB。

`study-defined` 适配器只搬运规范 Study 中已经登记的 `FeatureDefinitions` 与 `Values`，不代表 32 类原生 raw Results 都已实现。原生候选项只有在界面显示“已支持”或“条件支持”时才可选择；其具体字段、参数和限制以 [能力注册表](../pyfnirs/pyfnirs_converter/capabilities.json) 和[兼容矩阵](compatibility.md)为准。未验证或不支持的候选项会显示原因并保持不可选。

## 图形界面

正式发行版可直接运行上一节列出的 EXE；下面的命令需先进入仓库的 `pyfnirs` 目录，并按 [仓库说明](README.md)创建该目录的开发环境：

```powershell
.\.venv\Scripts\python.exe -X utf8 -B -m pyfnirs_converter
```

1. 选择输入目录和输出目录；需要时勾选“递归扫描子目录”。目录扫描只处理 `.mat` 与 `.json`，并排除输出目录。
2. 读取 `.mat` 时填写 MATLAB 程序路径。点击“检查输入”，选择要检查的样本文件和来源适配器。
3. 从检查结果明确选择观察 ID，以及可选的记录 ID、主体 ID、配对 ID 和来源 ID。逐项指定目标标签、协变量和特征列；文件名、行序或 `Group` 字段不会自动成为身份或目标。
4. 点击“预览转换”检查样本数、输出列、缺失单元、警告和合并冲突。预览不写文件。
5. 选择 CSV 文件组或 Excel 工作簿，选择逐文件输出或兼容来源合并，以及输出冲突策略“重名时跳过”或“重名时改名”；然后启动批处理。

批处理中每个文件单独报告成功、失败、跳过、取消或未处理。取消采用协作式停止：工具安全结束当前步骤后停止继续处理后续文件，并保留逐文件状态。逐文件模式下已完成并发布的输出会保留；合并模式取消时不会发布部分合并结果。

## 批处理与合并

- 逐文件模式为每个来源单独生成结果。策略“重名时跳过”保留现有结果；“重名时改名”会选择未占用的新输出名称，不覆盖已有 CSV 目录或 XLSX 文件。
- 合并模式要求输入具有兼容的特征定义和映射。重复观察 ID、定义冲突或映射不一致会拒绝发布合并结果，不会静默覆盖或重排特征含义。
- 当输入明确列出多个文件时，合并顺序遵循所列顺序；目录扫描在每个目录内按文件名稳定排序。
- 输入目录包含输出目录时，扫描会排除输出子树，避免将先前结果再次作为输入。

## 输出内容

CSV 文件组包含 `FeatureMatrix.csv`、`Samples.csv`、`FeatureDictionary.csv` 和 `Provenance.json`。Excel 工作簿包含同名的前三张表及 `Provenance` 表。

`FeatureMatrix` 保存观察 ID、明确映射的标签/协变量和所选特征值；有效掩码及缺失原因保存在 `Provenance`，按观察和 FeatureID 的矩阵顺序对应。缺失不会填成 0；来源缺失、质量拒绝等原因会保留。Excel 中的 ID、标签、特征 ID 和来源字符串均按文本保存，即使原值以 `=` 开头也不会被当作公式；CSV 保留原字面值，不增加前缀。

XLSX 中的有限浮点仍写为数值单元格，并使用可由 Python 二进制浮点精确回读的十进制表示。工作簿软件自身的显示或数值精度规则可能影响可见位数。

## 合成示例与 PY-ML 导入

下面仅演示表格组织，数据为合成示例，不是实际研究记录。观察顺序和特征顺序都明确固定为 `OBS-42`、`OBS-8` 与 `F-O2`、`F-HbR`：

| ObservationID | F-O2 | F-HbR | Group | AgeYears |
|---|---:|---:|---|---:|
| OBS-42 | 1.25 | 3.75 | control | 31 |
| OBS-8 | 2.5 | 缺失 | case | 45 |

因此特征矩阵为 `[[1.25, 3.75], [2.5, 缺失]]`，目标列为 `Group`，`AgeYears` 是显式映射的协变量。缺失值会保持缺失并在 `Provenance` 中记录有效掩码和原因，不填成 0。此示例的监督目标完整；训练前仍需确认所选模型对缺失特征的处理方式。

选择 CSV 时，将生成的 `FeatureMatrix.csv` 导入 PY-ML；CSV 文件组还包含 `Samples.csv`、`FeatureDictionary.csv` 和 `Provenance.json`。选择 XLSX 时，将生成的工作簿导入，并指定 `FeatureMatrix` 工作表；工作簿另外包含 `Samples`、`FeatureDictionary`、`Provenance` 工作表。导入后显式指定特征列 `F-O2`、`F-HbR` 和目标列 `Group`。在该示例中，`ObservationID` 保持样本身份列、`AgeYears` 保持协变量，不会被自动加入特征矩阵；只有在明确制定分析方案后才应把协变量作为模型特征。

PY-ML 的表格读取接口支持从 CSV 或指定工作表读取，例如 `load_dataset(path, sheet_name="FeatureMatrix")`，随后通过 `select_features_target(..., feature_columns=["F-O2", "F-HbR"], target_column="Group")` 显式选择特征与目标。标签不要改由文件名、行号或观察 ID 推断。

## 原生能力状态与限制

32 类原生 raw Results 候选中，只有以下 3 个明确子形态为条件支持：第 07 项的静态 Pearson FC 边（`ModelIndex=1`，并要求明确且唯一的节点顺序、匹配的对称矩阵和参数指纹）；第 14 项的非窗口 MVAR-Granger 有向边（`Status=ok`，公式、方向约定和节点顺序一致）；第 24 项的 `TotalPersistence` 标量（状态、节点顺序、输入语义、阈值和距离定义一致）。其余 29 项及这三类之外的其他子形态保持 `unverified`，不能从“文件可读取”推断为已支持。完整条件见[兼容矩阵](compatibility.md)与[能力注册表](../pyfnirs/pyfnirs_converter/capabilities.json)。

发行版目前输出 CSV 文件组或 XLSX 工作簿；提议的权威 `MLInput.mat` 输出尚未实现。所有发行验证与上表示例使用合成夹具，不代表真实研究数据、设备同步或训练结果已经验证。

## 命令行

图形界面和命令行共用同一公共 API。命令行入口为 `pyfnirs_converter.cli`：

```powershell
# 检查一个输入并列出可用适配器、字段和候选特征
.\.venv\Scripts\python.exe -X utf8 -B -m pyfnirs_converter.cli inspect "D:\data\study_export.json"

# 预览 selection.json 中明示的映射，不写出结果
.\.venv\Scripts\python.exe -X utf8 -B -m pyfnirs_converter.cli preview "D:\data\study_export.json" --selection "D:\config\selection.json"

# 转换一个或多个文件/目录；递归扫描需显式传入 --recursive
.\.venv\Scripts\python.exe -X utf8 -B -m pyfnirs_converter.cli convert "D:\data" --selection "D:\config\selection.json" --output-dir "D:\converted" --recursive
```

`selection.json` 必须明确提供适配器、身份字段、特征选择、目标、协变量、输出格式、合并方式和重名策略。每个特征选择还要提供能力 ID、输出 FeatureID、来源路径、允许的轴选择及参数；不完整或包含未知键的配置会被拒绝。原生 `.mat` 还可在 `inspect`、`preview` 或 `convert` 命令中用 `--matlab` 显式指定 MATLAB 可执行文件。

下面是针对合成 `study_export.json` 的最小格式示例。它只搬运该 Study 中已经存在的 `F-O2`、`F-HbR`，不能直接套用于 raw Results 或其他字段布局；请按本地检查结果修改来源路径、ID 和列名。

```json
{
  "source_adapter_id": "pyfnirs.study_export.v1",
  "identity": {
    "observation_id_source_path": "study.Observations.ObservationID",
    "record_id_source_path": "study.Observations.RecordID",
    "subject_id_source_path": "study.Observations.SubjectID",
    "pair_observation_id_source_path": "study.Observations.PairObservationID",
    "source_id_source_path": "study.Observations.SourceID"
  },
  "feature_selections": [
    {
      "capability_id": "study-defined",
      "feature_id": "F-O2",
      "source_path": "study.Values",
      "axis_selection": {},
      "summary_parameters": {}
    },
    {
      "capability_id": "study-defined",
      "feature_id": "F-HbR",
      "source_path": "study.Values",
      "axis_selection": {},
      "summary_parameters": {}
    }
  ],
  "targets": [
    {"source_path": "study.Observations.Group", "output_name": "Group"}
  ],
  "covariates": [
    {"source_path": "study.Observations.Cov_AgeYears", "output_name": "AgeYears"}
  ],
  "output_format": "csv",
  "merge_mode": "per_file",
  "collision_policy": "skip"
}
```

## 验证边界

合成 fixture 用于核对已登记条件下的值、身份、顺序和缺失掩码，不代表真实研究数据已通过。不同样本的节点顺序、单位、处理参数、来源身份或记录配对不一致时，应先解决来源定义；不能仅因字段可读取就合并或作为同一特征训练。
