# HyperEEG 数据转换 0.1.0

将 HyperEEG 已计算的特征表转成 PY-ML 能读取的 CSV。转换器不重新计算 EEG 特征，不进行标准化、插补、聚类、统计检验或训练。

## 从 PY-ML 接入

1. 解压发行包，保留整个 `PYML-DataConversion` 文件夹及 `_internal` 子目录。
2. 在 PY-ML 的 **插件 → 设置** 选择这个文件夹（包含 `pyml-plugin.json` 和真实 EXE）。Python 程序留空。
3. 点击保存，**插件 → 数据转换** 会启用，点击后打开独立中文窗口。
4. 也可以直接双击 `PYML-DataConversion.exe`，独立于主程序使用。

源码运行：先进入仓库的 `hypereeg` 目录，在 Python 3.12 环境中 `pip install -r requirements.txt`，然后 `python launch.py`。
源码仓库根目录故意没有正式清单，避免把未构建环境声明为可用发行。
构建：在仓库的 `hypereeg` 目录中操作，建议 Python 3.12.14，安装 `requirements-lock.txt`，在 PowerShell 执行 `./packaging/build.ps1`。不要用 Python 3.12.0 构建（其冻结字节码处理存在已知缺陷）。构建脚本保留已经存在的发行 ZIP；改版后另建不同名称的压缩包。

## 输入与具体映射

| 输入 | 样本身份 | 特征列 |
| --- | --- | --- |
| `FeatureResult.longData` MAT | file_name、subject_id、session、condition、timepoint、segment_name、window_index 中实际存在的列；缺 file_name 时用 source_mat | result_key × measure × cell_key × value |
| 旧 XLSX 的“分析长表” | file_name、subject_id 等真实身份 | feature × value |
| 新 XLSX 的“特征文件清单” | 按完成状态读取 path 指向的 FeatureResult MAT，再使用其长表身份 | 读取真实载荷，不把清单当训练数值；清单和审计页保留为附表 |
| 单导正式 features CSV | StreamID、SourcePath、SubjectId、IndependentUnitID、Session、Condition、SourceSegmentId、TimeSegmentIndex、WindowIndex 中实际存在的列 | 当前源码的 11 个正式指标：Mean、Std、RMS、PeakToPeak、HjorthActivity/Mobility/Complexity、SampleEntropy、ApproximateEntropy、PermutationEntropy、SpectralEntropy |
| 单导 band power CSV | 同上 | Band、LowHz、HighHz 坐标 × Power/RelativePower |
| 单导 connectivity CSV | Session、GroupId、两名被试/独立单位/流/片段、条件、WindowIndex | Method × Metric × Band × Value/LagSeconds；保留配对身份 |
| 单导 network CSV | Session、GroupId、IndependentUnitID、Condition、WindowIndex | Method × Band × Density/MeanStrength/MeanClustering/GlobalEfficiency |
| record 范围 Artifact 的通道标量表 | 原生 Artifact.sourceIds 的唯一来源生成 `__source_id`；窗口列存在时另保留 | channel_index/channel_name/频带坐标 × 取数方案明确的幅度、频谱和非线性标量 |
| 其它 Results/Artifact MATLAB table | 在字段映射中明确选择样本、坐标和数值列 | 只展开已命名的标量表列；附带原生路径、类型、单位、Artifact 来源和参数 |
| 其它 7 份参考 XLSX、旧结果中的参考审计页 | 不作为 EEG 样本 | 勾选“只导出参考工作表”，逐页保留 CSV 附表 |

例如旧“分析长表”中的 `file_name=A.bdf, subject_id=001, feature=rms_Fz, value=1.25`，成为 A.bdf/001 的一行，其 `feature__{"values":"value","coordinates":[["feature","rms_Fz"]]}` 列为原值 `1.25`。另一条通道坐标成为同一样本的另一列，不新增被试。JSON 列名保留完整坐标并避免名称碰撞，含义也写入列字典。

MAT 读取通过 MATLAB 的 `load` 还原原生 table/string/cell，支持 v7 与 v7.3。需本机安装并有许可的 MATLAB；可填写 `matlab.exe`，留空时从 PATH 查找。默认读取 `FeatureResult.longData`；其它文件只有一个表时可定位它，有多个表时报告可用路径，填写例如 `Artifact.payload.scalar` 或 `Results.firstOrder.timeDomain.data`。

任意矩阵、含向量单元的 table、复杂 cell、微状态模板或跨样本拟合表示，没有明确坐标和拟合边界时不会自动转置或展平。此版不承诺原始 BDF/RDS/IDS 或完整 PSD/STFT 张量的自动特征提取。对这些数据，应先由 HyperEEG 按既定方法导出带真实样本与坐标的标量长表，再接入转换。sourceIds/scopeKey 不等于标签，也不会猜原始 BDF 与清洗 MAT 的文件对应关系。

## 批处理、标签与导入

选择输入、输出目录，按需要勾选递归及合并。默认逐文件输出并同时按真实样本键对齐合并。先选一个代表文件预览；默认映射只适用于上表的明确契约，其它表填写样本身份列、特征坐标列、数值列，列名以逗号分隔。

外部标签/分组表可选 CSV/XLSX。必须指定两边实际存在的完整连接列；多个匹配工作表时另选页名。连接表中键必须唯一，每个样本必须匹配，已有元数据发生冲突时报告失败。需要监督学习时填写真实标签列；不填就不生成标签。缺标签、重复键或未匹配样本不会通过截断、重排、丢样本或伪造标签处理。

每次运行创建新的时间戳加随机标识目录；不会覆盖前次结果。输出目录不能等于输入或包含输入，输入下的输出子目录会排除；已移动的本插件结果目录也根据来源清单排除。正式 XLSX 清单引用的成功 MAT 由该清单读取一次，递归扫描不会再次读取同一个 MAT。单文件失败后继续其它文件；合并冲突单独报告，逐文件成功结果保留。取消会保留已完成文件，删除未发布的暂存结果，并给出未处理数量。

每个成功目录有：

- `dataset.csv`：sample_id、meta__ 元数据、可选 target__ 标签及 feature__ 数值列。
- `valid_mask.csv`：同样本顺序，1 表示有限数值；空值/NaN/Inf 为 0。它不代替算法质量资格。
- `feature_dictionary.json`：数值列和坐标、原始路径的对应关系。
- `source_tables/`：完整原始表列及来源路径；不把审计、分组、质量列静默变成 EEG 输入。
- `provenance.json`：输入 SHA256、映射选项、样本键、原生类型/单位/参数及输出维度。
- 每轮根目录的 `batch_summary.json`：逐文件原因、成功/失败/跳过/未处理数量和合并结果。

在 PY-ML 选择 `dataset.csv`，显式选择 `feature__` 列作为输入、真实 `target__` 列作为目标。sample_id、meta__ 被试/群组/场次用于索引和分组验证，避免把同一被试的窗口拆进不同训练/测试集。不得把测试结果、参考签名、标签或分组身份当作 EEG 特征。此版保留原始质量列；failed/skipped/unavailable/invalid/rejected 等明确失败状态会使该输入报告失败，其它状态须结合 HyperEEG 原始资格复核。

所有原有数值文本原样写出；MAT double 使用 17 位有效数字。缺失不补零。不同来源的通道、频带、单位、参考及参数仍须可比；列不存在时合并保留空值和 mask=0，没有自动降维或选择特征。

命令行：`python launch.py --input "输入目录" --output "输出目录" --options "映射.json"`。选项 JSON 对应 `hypereeg_converter.core.Options`，如 `{"sample_columns":["subject_id","session"],"coordinate_columns":["channel_index"],"value_columns":["rms"]}`。发行 EXE 支持同样参数，结果写入输出目录；窗口版没有终端输出。

真实验证范围和限制见 `validation-summary.md`。没有实际采集特征 MAT 时，合成原生 MAT 通过不等于真实设备数据通过。
