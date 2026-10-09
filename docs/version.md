# 版本记录

## 2026-10-09 — 收整为 docs、hypereeg、pyfnirs 三个目录

- GitHub 内容收整为 `docs`、`hypereeg`、`pyfnirs` 三个顶层目录；README 和本版本记录归入 docs，两套源码、启动入口、依赖清单及构建配置归入对应转换器目录。prompts、tests、测试工具、旧计划及原根目录文件不再纳入 GitHub。
- 按用户选择，完整冻结 EXE 仅留本地，分别位于 `hypereeg` 和 `pyfnirs` 目录，可直接由主程序选择；目录内 `.gitignore` 排除 EXE、`_internal`、成品清单及构建产物。既有 HyperEEG 设置同步更新，未设置的 PYfNIRs 槽仍由用户自行选择。
- 成品 1,183 个文件及所有迁移源码/配置的迁移前后 SHA-256 均一致；两套迁移后源码 GUI 实际启动、全部 Python 源码 AST 解析、host 普通及 PYfNIRs 来源检测、两个 PowerShell 构建脚本语法检查通过。HyperEEG 构建脚本调整共享 docs 的相对位置，操作说明更新目录及开发环境创建方式；未重新构建 EXE或执行数据转换核心回归。
- 本地 `.venv`、prompts、tests、tools、六个原根目录文件及测试专用 MATLAB 夹具生成器的删除被自动审批拒绝，仅返回 blocked by policy，尚未删除。已生成 docs/cleanup-once.cmd（纯 ASCII、CRLF）供用户执行；真实 CMD `/check` 成功识别全部 11 个目标，未执行删除，成功后脚本删除自身。脚本及本地待清理内容不会提交 GitHub，`.git` 仅作为本地仓库元数据保留。
- 发布目标为 support/master；本次仅调整目录与路径，插件版本保持 0.1.0。

## 2026-10-09 — 修正一次性清理 CMD 的编码与换行

- 初版脚本在用户 CMD 中出现断行、路径错误和中文乱码；检查确认文件使用 UTF-8、仅 LF 换行，六个待删文件均仍存在。
- 修正为无 BOM 的纯 ASCII 脚本及 CRLF 换行，旧 spec 通过 `%~dp0` 定位。增加 `/check` 只读模式；真实 CMD 检查成功识别全部六个目标，退出码为 0，未执行删除。
- 用户可再次运行原 `call` 命令。全部文件删除成功后脚本删除自身，失败则保留脚本并报告剩余文件；此前自动审批拒绝的删除仍待用户执行。

## 2026-10-09 — 可直接选择的插件整理与项目清理

- 将最终 HyperEEG 发行完整迁至仓库根目录 `HyperEEG-DataConversion`，将 PYfNIRs 发行完整迁至 `PYfNIRs-DataConversion`。在 PY-ML 分别通过“插件 → 设置…”和“格式 → 数据转换 → PYfNIRs 设置…”选择具体插件目录，保留 EXE、manifest 和 `_internal`。
- 迁移后逐项核对 HyperEEG 923 个文件、PYfNIRs 260 个文件的 SHA-256，全部与迁移前一致；既有 HyperEEG 用户设置同步更新。当前 host 的普通及 PYfNIRs 来源检测均通过，两个冻结 EXE 在新位置实际创建 Qt 窗口并正常退出；此次没有重新测试转换核心。
- 清理本仓库 `build`、旧 `dist`（含失败 staging 目录、重复/旧 ZIP）、生成的合成测试数据和 Python 缓存。源码、正式测试及夹具生成脚本、requirements 清单、`.venv`、正式 spec、使用说明和 Git 历史保留；与 PY-ML 合计清理 95 项目标、41,204 个原有文件，逻辑体积约 15.396 GiB，这些目标全部删除成功。旧自动生成 `PYML-DataConversion.spec` 收尾删除被自动审批拒绝，尚未删除。
- README、PYfNIRs 使用说明和 HyperEEG 验证摘要更新当前路径；根目录 `SHA256SUMS.txt` 记录两个 EXE 与两个 manifest 的现有哈希，`.gitignore` 排除整理后的二进制目录。原构建脚本仍生成 `dist`，之后的新发行需选择其实际目录。
- C:/Users/Lenovo/.codex 未发现可确认属于本项目的 temp/tmp；当前 Codex 数据目录为 E:/CodexData，共享插件和运行文件保留。本轮临时脚本、清理清单及 smoke 产物的收尾删除也被自动审批拒绝（仅返回 blocked by policy）；一次性清理剩余文件.cmd 精确列出旧 spec 和本轮五个临时文件，供用户执行，全部成功后删除自身。两个插件版本保持 0.1.0。

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

## 2026-10-08 — HexiPlan 项目接入提示词

- 新增一份可直接粘贴并附项目对话链接的完整 TXT 提示词，包含解析、实现、验证与交付流程。
- 按用户要求另保存三个可独立执行的阶段 TXT；完整提示词无需逐份粘贴。
- 模板使用默认常规档和无需人工审核流程，按固定入口核对真实模型/代理能力，保留必要权限与关键数据映射确认。
- 明确独立插件目录、现有菜单与清单接口、批处理正确性、发行验证、共享文件协调、版本维护及 Git master 范围。
- 本轮只编写提示词，没有启动 HexiPlan、实现具体转换器或改动主程序。

## 2026-10-08 — 插件接入接口准备

- 代码仓库克隆至指定目录，使用 master 分支。
- 主程序插件菜单位于“分析”右侧、“帮助”左侧。
- 数据转换默认置灰，设置始终可用，通过目录和启动文件检测后启用。
- 独立进程接口支持未来 EXE 或外部 Python 环境。
- 批处理转换器按后续提供的项目逐个实现；当前没有转换器或转换 EXE。
- 主程序接入的 12 项定向检查和 GUI/worker 30 项源码比对通过，源码设置窗口截图及实际冻结菜单位置、禁用状态完成核对。
- 主程序标准版 EXE 与本机 APP 入口已刷新；转换器尚未加入，因此当前入口仍为灰色。
- 本仓库 master 初始内容为接入接口说明及实现计划；实际转换包在后续项目接入时加入。

## 2026-10-08 — PYfNIRs 步骤二执行包拆分与路由前置状态

- 新增 `prompts/11a-results.txt` 与 `prompts/11b-gui.txt`，将已批准执行包 11 拆为 core/results 与 GUI 两个窄执行范围；两份文件引用 G4 内容哈希 `388c512da6b20913c2917be276b7ebc83a9ead64c434b5b76438b3951cd9962c`，不复制或重写 32 项注册内容。
- RUN 步骤二保持 `execution`，首步仍为 `ACCEPTED`、修复轮次未重置；记录 adapter 与 GUI Luna lease，旧 pending_init 实例不计入。实际模型路由仍为 `UNVERIFIED`。
- 依据原 prompt 11，业务文件写入仍受可信路由元数据前置条件约束；这次只完成执行范围整理和状态登记，没有宣称转换器实现、测试或数据验证完成。
## 2026-10-08 — 步骤二恢复授权记录与公共 API 骨架

- 保留 `prompts/10`、`11`、`12` 的旧路由前置原文，并追加只适用于本 RUN 的恢复说明；另在 `11a-results.txt`、`11b-gui.txt` 中保持一致。RUN note seq 56记录用户真实“执行”、常规档偏好、协调上下文解释及Astra/Sol补充确认，且继续将 actual model routing 标记为 `UNVERIFIED`。
- 新增 `pyfnirs_converter/api.py` 公共类型与函数签名骨架，绑定步骤二 G4 哈希 `388c512da6b20913c2917be276b7ebc83a9ead64c434b5b76438b3951cd9962c`。四个公共入口的签名导入检查通过；核心转换逻辑仍待完成。
- GUI 所需 `PySide6==6.11.2` 已存在于现有 `requirements.txt` 和锁文件中，本次未添加依赖。此记录不宣称转换、GUI 或真实数据验证已完成。

## 2026-10-09 — XLSX 字符串字面值保真补充

- XLSX writer 将所有字符串显式保存为文本单元格，防止以 `=` 开头的 ObservationID、标签、FeatureID 或来源字符串被识别为公式；CSV 仍原样写出，不添加改变数据的前缀。
- IO 回读检查覆盖 `=OBS-42`、`=control`、`=F-O2` 和 Provenance 来源字符串；openpyxl 普通视图及 `data_only=True` 均读回原值。合成 I/O 检查不代表真实研究数据验证。
- `.venv\Scripts\python.exe -m unittest discover -s tests -t . -v`：23 项通过，1 项 GUI 集成检查因未设置 `PYFNIRS_STUDY_EXPORT_FIXTURE` 按门控跳过。指定经批准的 fixture 路径后，该 GUI 集成流程另有 4 项通过证据。
