# PYfNIRs 数据转换契约（schema 1）

本文定义 PYfNIRs-DA `study` 如何进入 PY-ML 的样本矩阵。MATLAB v7.3 中的 table 由 MATLAB 导出桥读取；Python 不把 MAT 文件内部 HDF5/MATLAB 对象布局误当普通表格。

## 源 study

输入顶层必须包含标量 struct `study`，且 `Kind="PYfNIRsDA.Study"`、`SchemaVersion=1`。规范结构包含 `Sources`、`Observations`、`PairLinks`、`FeatureDefinitions`、`Values` 和 `CovariateMetadata` 六张 MATLAB table。桥校验规范列顺序与 MATLAB 类型，并保留额外的表、struct、cell 和数组形状；遇到未注册 MATLAB 类或复数值会明确拒绝，不静默转成文本数字或实数。

`Values` 是逐观察长表，规范字段为 `ObservationID`、`FeatureID`、`Value`、`IsValid`、`MissingReason`、`SourceID`，其中 `(ObservationID, FeatureID)` 唯一。有效数值必须有限且缺失原因为空；无效值必须是 NaN 并带原因。所有样本、特征和来源 ID 都要能解析到对应表。

`Observations` 的规范前缀列为 `ObservationID`、`RecordID`、`SubjectID`、`PairObservationID`、`Group`、`Condition`、`Session`、`Timepoint`、`Include`、`SourceID`。每行必须明确属于一个主体记录或配对观察；只有以 `Cov_` 开头的标量协变量列可以追加，含义由 `CovariateMetadata` 的 `ColumnName`、`Level`、`Origin`、`DataKey` 说明。

`PairLinks` 用 `PairObservationID` 连接配对观察，保留 `PairID`、两侧记录和主体 ID、`RoleA/RoleB` 及条件/会话/时间点。`FeatureDefinitions` 为每个 `FeatureID` 提供指标、层级、血红蛋白、节点/角色、频带/时间窗、尺度、单位、变换、方向、维度和参数/映射指纹。所有字段按源 schema 保存；桥不计算或重命名科学特征。

`Sources` 记录来源类型、版本、路径、指纹、适配器和能力状态。`Capability` 仅允许 `direct`、`needs_summary`、`preview`、`unsupported`。来源能力和转换器实测状态分开记录；32 项逐项边界见 [兼容矩阵](compatibility.md) 与 `pyfnirs_converter/capabilities.json`。

## MATLAB 到 Python 中间包

MATLAB 桥输出 `study_export.json`，schema 标识为 `pyfnirs.matlab-export/1`。每张表保留原列名、顺序、MATLAB class、单位/说明、row names 和行序。单元值保留 class、原形状和精确文本；double 使用 17 位有效数字，整数按原整数文本导出。字段 ID 不依赖 MAT cell 顺序。Python 校验双 ID 唯一、外键、来源引用、有效性和缺失原因后才接受。

中间包不代表训练矩阵，也不代表 32 项全部可转换。`TermTests`、`Descriptive` 等结果表即使随 study 输出，也不能替代逐样本 `Values`。稳定、经过 schema 1 验证的中间包可以在没有 MATLAB 的机器上继续转换；读取原生 MATLAB table MAT 时需要 MATLAB。

## PY-ML 输入结构

内存结构 `MLInput` 的 `schema_version` 为 `1`，包含：

- `X`：按 `Samples` 行序和 `FeatureIDs` 列序排列的二维数值矩阵。
- `FeatureIDs`：唯一且按 `FeatureDefinitions` 顺序排列。
- `Samples`：每行含明确 `ObservationID` 及样本/配对身份、来源与防泄漏信息。
- `Targets`、`Covariates`：按 `Samples` 对齐的独立字段映射；用户显式选择目标。文件名、`Group`、`Condition` 不会自动成为目标。
- `FeatureDefinitions`：与 `FeatureIDs` 一一同序，保留单位、节点/方向、时间窗、变换、指纹和原始 `FeatureID`。
- `ValidMask`、`MissingReasons`：形状均为 `样本数 × 特征数`；无效值不得填补或改成零。
- `Provenance`：来源文件、导出桥版本、字段映射及转换摘要。

动态窗口不会自动成为独立样本；同一主体/配对的拆分组信息须保留以支持防泄漏。任何汇总、投影或配对差值必须由注册表中的精确定义明确声明，不能按数组形状猜测。

## 人工审核工作簿

工作簿使用 `FeatureMatrix`、`Samples`、`FeatureDictionary` 三张表；矩阵行序与 `Samples` 一致，列序与字典的 FeatureID 一致。每张工作表最多 1,048,576 行、16,384 列。超限时不得截断或拆表冒充单一矩阵；转换器应停止 XLSX 写出并报告容量边界，后续可选择已支持的 CSV 路径。

## 当前验证边界

仓库没有真实 `analysis_input.mat` 或逐样本结果工作簿。步骤一使用 MATLAB 创建的合成 v7.3 fixture，检查真实 MATLAB table 序列化、乱序且非连续身份、标签/协变量按 ID 联结、值精度和缺失状态。它只验证合成结构，不构成真实研究数据验证。`results.xlsx` 是统计结果工作簿，不能作为逐样本训练输入。
