# 版本记录

## 2026-10-09 — PYfNIRs G4 host 接入阶段三独立复核

- 阶段三正式独立 verdict 已登记 PASS：21/21 criteria PASS，含 16 项真实 host 接口检查和 5 项冻结材料/运行证据复用；正式报告与 RUN 哈希见 docs/PYfNIRs验证摘要.md。
- 新增 docs/PYfNIRs验证摘要.md 和 docs/host-patches/PYfNIRs/ 补丁交接包；前置说明记录旧 clean HEAD 缺少 generic 插件文件及准确 before hashes。
- PY-ML 新菜单仅通过源码 launcher 显示，桌面 APP 未重建；实际模型路由仍为 UNVERIFIED。自动清理被策略拒绝，未删除文件。
- 本轮完成 support/master 选择性源码交付；具体 commit SHA 与远端推送确认见本次 RUN 最终交付记录。本独立技术验收不作 Git 断言，G5 最终报告另行记录。

## 2026-10-09 — PYfNIRs 0.1.0 独立发行与 PY-ML 接入

- 正式发行目录为 `dist/PYfNIRs-DataConversion`，manifest 标记 `source_project=PYfNIRs`。冻结包完成 GUI smoke、合成 JSON 的 CSV/XLSX 转换及 MATLAB R2023a raw MAT 转换；从独立验证目录启动时进程映像匹配正式 EXE，运行 4 秒后由测试结束。发行 EXE SHA256：`cb77fe424a0f90d455263e49ac93e5834dcbc6fd98b8ff37b311baaf07045229`。
- PY-ML 实际读取转换器生成的 CSV/XLSX，明确选择 `F-O2`、`F-HbR` 及 `Group`，确认身份列与 `AgeYears` 未进入特征；数值和缺失 mask 与 oracle 一致。额外精度 XLSX 的 `-0.0`、最小次正规值和最大有限值逐位回读通过；长期证据见 `H:/AIcode/HexiPlan/runs/pyfnirs-pyml-converter-20261008-01/evidence/pyml-integration-release-20261009`。
- PY-ML 菜单由 `QProcess` 启动正式发行 EXE；隔离设置保存、实际映像路径及 host 定向测试 4/4 通过。仅使用合成夹具，不代表真实研究数据验证；能力边界仍以 `docs/compatibility.md` 为准。
- 构建排除 PATH 中与 Qt 不兼容的 Poppler ICU，脚本改为显式等待并检查隐藏 EXE。插件版本保持 0.1.0。

## 2026-10-09 — PYfNIRs 阶段二独立复核修复轮 1

- XLSX writer 改为将有限浮点的 round-trip 十进制值写入数值类型单元格，避免 openpyxl 默认 16 位有效数字格式化改变 binary64 值；回归检查同时确认单元格仍是 numeric，未将数值转为文本。
- 批处理保留用户显式传入的文件顺序；目录扫描仍按各目录中的文件名稳定排序。合并回归覆盖目录顺序和显式 `(B, A)` 文件顺序。
- 修复前两项独立反例均可复现；修复后 I/O 定向测试 5 项、批次定向测试 5 项通过。I/O 回归还核对负零、1 的下一个 binary64、最小 subnormal 和最大有限 double 的 CSV/XLSX 回读。
- R2 独立复核已正式登记 PASS：19 项新增检查全部通过；首次复核其余 17 项 PASS 证据复用，原两项失败均由新检查关闭，修复轮次保持 1。verdict wrapper、复核报告、机器结果 SHA256 分别为 `1495748819f732745e5ac46fd06c73e00432c7f6fb04f0d889b1e13d0f3873ca`、`5555252f07aee5cc4fae03e6a25f7ac622dc0f708af86737a0504c9f63b00a3c`、`cb9c65c9940da4fff3f7adf37db07ef407b63033caafd3459717877abbc16b22`；修复证据 SHA256 `db6146c07cd0d4d76739d5786c5943fe89b54d8a30d36643706d85b315088fa8`。此前通过的 MATLAB/raw/GUI/CLI/契约证据按原报告复用；实际模型路由和 reviewer observed identity 仍为 `UNVERIFIED`，数据仍是合成夹具。

## 2026-10-09 — PYfNIRs 阶段二整合与证据

- 完成生产 registry 无 patch 的真实 MATLAB R2023a v7.3 合成 MAT→MATLAB helper→core→CSV/XLSX 闭环。第 07/14/24 项只有明确列出的 Pearson 静态 FC、非窗口 MVAR-Granger、持续同调 `TotalPersistence` 子形态为 `conditionally_supported`；其余 29 项及其它子形态继续 `unverified`。独立值为 `[2.5, 0.25, 0.3, NaN]`，mask `[true, true, true, false]`，缺失原因 `source_nonfinite`，身份 `OBS-SYN-17 / REC-SYN-17 / SUB-SYN-9`、标签 `synthetic_case`。没有真实研究数据验证。
- 核心、批次、adapter 和 I/O 定向测试 19 项通过；GUI 实际公共 API 联通、取消与呈现测试 4 项通过（取消当前文件 1、后续未处理 31）。共 23 项通过。GUI 截图 SHA256：`8D5E6110EFF4C386DADA186F5507E99DC090E4111B6B51B90D39F48E4F96B063`。
- CLI `inspect`、`preview` 和 `convert` 也用同一 RUN 中的批准 Study fixture 做了直接调用：预览 2 个样本、1 个缺失单元，转换成功生成完整 CSV 文件组；命令检查和结果哈希保存在 stage2 integration 证据中。
- 测试通过 `PYFNIRS_STUDY_EXPORT_FIXTURE` 和 `PYFNIRS_RAW_RESULTS_FIXTURE` 显式指向 RUN fixture；fixture 生成物保留在 RUN，测试在 fixture 未提供时按说明跳过，不依赖仓库内的生成 MAT/JSON。
- 使用流程见 `docs/PYfNIRs转换器使用说明.md`；范围与状态见 `docs/compatibility.md` 和 `pyfnirs_converter/capabilities.json`。CSV/XLSX 是当前输出；提议的 `MLInput.mat` 权威输出尚未实现，原生 MAT 输入仍通过 MATLAB 桥接。
- raw 闭环报告：`evidence/raw-feature-production-closure-r1.json`，SHA256 `9b22dc32ae80c558f3ff6394c1c60884aa078a08796408ff361becbb71b82a06`。当前阶段材料待独立整合验收；实际模型路由仍标记为 `UNVERIFIED`。

## 2026-10-08 — PYfNIRs 输入契约独立复核（R2）

- 修复后独立复核新执行的 24 项检查全部通过：原 15 个失败反例修复通过，另有 9 个受影响边界案例通过；此前通过的 30 项检查复用，原 45 项检查全部有通过证据。
- 复用的真实 PYfNIRs validateStudy 结果为基线 Valid=true 且拒绝 12 个坏定义；复用原 MATLAB v7.3 合成夹具和数值 oracle，不将此结果表述为真实研究数据验证。
- 正式独立 verdict 为 PASS，修复轮次保持 1。复核报告 SHA256：095d47f18626d79abaca5732f779bb48c2b04e0bcf45e600977e1432449977cc；机器结果 SHA256：89627d96234032b45a0d41b0fe7405c369afb1683e5d9ed9ba2b665f89edf5ce。
- 本步骤仅完成输入契约验收；32 项原生全适配、真实研究样例转换及后续转换界面/输出行为仍未验证。

## 2026-10-08 — PYfNIRs schema语义修复（第1轮）

- 首次独立检查按源 `PYfNIRsDA.features.validateDefinitions` 对比时，发现 Python 放过 12 类无效 `FeatureDefinitions`，并放过 3 类 `MLInput` 掩码/原因矛盾；已按正式独立 FAIL 进入 repair_round 1。
- `contracts.py` 现校验特征必填文本、Level/Hemoglobin/Transform/Direction/Dimension 枚举、edge 节点和 cross-brain 角色、频率/窗口范围及正 Scale；`MLInput` 要求有效值有限且原因为空，无效值为 NaN 或 null 且原因非空。
- 对原有 v7.3 合成 MAT 和 RUN 中 15 个失败反例执行针对性回归，另检查 NaN/null 两种无效值表示；18/18 通过，证据 `evidence/contract-repair-checks-r1.json`。未重新生成 MAT，也未重复成功的数值 oracle。
- 独立 MATLAB 源校验已在修复前验证原夹具 `Valid=true`，并拒绝 12 个坏定义；该结果用于对齐源规则，修复后独立复核仍待完成。

## 2026-10-08 — PYfNIRs 输入契约与 MATLAB v7.3 合成夹具复验

- MATLAB 9.14.0.2206163 (R2023a) 运行现有合成夹具生成器与导出桥，桥内 `validateStudyTables(study)` 检查通过；导出包含 2 个来源、3 个观察、1 个配对、2 个特征定义和 4 个值行。
- Python 独立 oracle 按显式观察/特征 ID核对矩阵值、顺序、目标、协变量、配对和有效/缺失状态，通过：3 个观察、2 个特征、4 个值行、2 个矩阵样本。夹具位于 HexiPlan RUN 的 `fixtures/pyfnirs-synthetic-v1-rerun-20261008-01`，仅为合成数据，不代表真实研究 MAT 验证。
- 本次 MATLAB 复验执行桥内 `validateStudyTables(study)`；随后独立检查在同一 MAT 上实际调用 PYfNIRs 源项目的 `PYfNIRsDA.io.validateStudy`，基线 `Valid=true`，并拒绝 12 个坏定义（详见 RUN 源校验报告）。
- 32 项能力注册表与兼容矩阵保持 planned/unverified；item 03 的频谱熵与 sample entropy 语义冲突仍明确标注。真实研究数据、转换器端到端支持尚未验证。

## 2026-10-08 — HyperEEG 0.1.0 r1 验收与清理限制

- 最终修订的正式 XLSX 清单 + 原生 MAT + 递归去重检查通过；EXE 的 CSV/MAT 转换及主程序实际导入与设置/菜单/独立进程启动复核通过。
- 最终目录 `dist/HyperEEG-0.1.0-r1/PYML-DataConversion`，本机用户插件设置已指向此目录；源码、使用说明、映射设计、验证摘要、截图及精简证据完整保留。
- 正式包 `dist/PYML-DataConversion-HyperEEG-0.1.0-r1-verified-windows-x64.zip`；SHA256：`1C70D97EF178D580BFAFF456DB662D355C70DB23F2F90D864ECF7D41BA639967`。
- 自动安全审查拒绝本轮过程脚本、合成数据、转换结果及中间构建/未采用发行的清理命令，返回 blocked by policy；未换工具或重试。过程文件保留在本地，不进入 Git 和正式交付包。
- 没有真实特征 MAT；不将合成验证表述为实际采集验证。多维/跨样本拟合表示和硬故障侧车完整资格仍需源项目明确导出及复核，具体限制见验证摘要。

## 2026-10-08 — HyperEEG 0.1.0 发行接入与补充

- 原生合成 MAT v7/v7.3 的 table/string、NaN、17 位 double 输出及 record 身份检查通过；复数载荷拒绝通过。
- 中文窗口、后台预览及取消检查通过；通过主程序真实设置类配置发行目录，数据转换入口由禁用变为启用，并经真实 QProcess 启动 EXE。
- 独立 EXE 的 CSV 转换、嵌入式 MATLAB 桥 v7.3 转换及实际 PY-ML 导入检查通过。
- 修正 Poppler ICU DLL 污染、PySide 导入检查冲突及中文字体加载；插件构建环境改用 Python 3.12.14，主程序环境保持原样。
- 收尾补充正式清单引用 MAT 的扫描去重，避免递归目录将清单及其载荷重复合并；补充检查与最终打包进行中。

## 2026-10-08 — HyperEEG 0.1.0 实现与初次验证

- 用户明确退出 HexiPlan 后按普通流程实施；未创建 HexiPlan RUN。
- 新增独立转换核心、中文 Qt 窗口、CLI、MATLAB 原生表格读取桥及 Windows 构建脚本。
- 支持统计长表、单导正式特征/频带功率/连接/网络表、明确映射的 MATLAB table；参考 XLSX 保留为附表，不自动成为 EEG 输入。
- 保留数值文本、样本顺序、缺失与零值、元数据及完整原始表；重复键、冲突连接及不明确矩阵显式拒绝。
- 基础数值、映射、标签和真实 PY-ML 读取接口、批处理容错/取消/防重入检查通过；8 份参考 XLSX 的完整值与表头往返通过。原生 MAT 与发行验证继续进行，尚不宣称真实采集 MAT 通过。
- 未改动主程序文件、HyperEEG 计算源码或原始数据。

## 2026-10-08 — 插件接入接口准备

- 代码仓库克隆至指定目录，使用 master 分支。
- 主程序插件菜单位于“分析”右侧、“帮助”左侧。
- 数据转换默认置灰，设置始终可用，通过目录和启动文件检测后启用。
- 独立进程接口支持未来 EXE 或外部 Python 环境。
- 批处理转换器按后续提供的项目逐个实现；当前没有转换器或转换 EXE。
- 主程序接入的 12 项定向检查和 GUI/worker 30 项源码比对通过，源码设置窗口截图及实际冻结菜单位置、禁用状态完成核对。
- 主程序标准版 EXE 与本机 APP 入口已刷新；转换器尚未加入，因此当前入口仍为灰色。
- 本仓库 master 初始内容为接入接口说明及实现计划；实际转换包在后续项目接入时加入。
