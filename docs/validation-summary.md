# HyperEEG 0.1.0 r1 验证摘要

日期：2026-10-08。按用户授权退出 HexiPlan 后执行。此摘要记录实际运行结果，不表示真实采集数据或训练结果已验证。

## 交付与环境

- 最终发行目录：`F:/桌面/程序/PY-ML-support/dist/HyperEEG-0.1.0-r1/PYML-DataConversion`。
- EXE：`PYML-DataConversion.exe`；清单 v1 的启动路径指向该真实文件，窗口启动验证通过后才生成。
- 插件独立环境：Python 3.12.14、pandas 3.0.6、NumPy 2.5.3、openpyxl 3.1.5、PySide6 6.11.2、PyInstaller 6.22.3；完整版本见 requirements-lock.txt。
- Windows 发行自带 Python/表格/Qt 运行依赖；CSV/XLSX 转换不需外部 Python。MAT 仍需已安装且有许可的 MATLAB，本机验证使用 `G:/matlab/bin/matlab.exe`。
- 主程序源码与已有发行未修改或重建；其原有未提交改动保持。系统插件设置通过主程序真实 PluginSettingsDialog 保存至 `%APPDATA%/PY-ML/plugins.json`。

## 已通过的检查

| 检查组 | 实际证据 |
| --- | --- |
| 长表原值/身份/精度 | 2 个样本 × 2 个坐标；保持 001/002 身份及原顺序，1.2345678901234567 文本保持，NaN 与真实 0 分开 |
| 无歧义映射/失败保护 | 重复样本×特征、重复表头、CSV 行列不齐、缺映射列均显式失败；没有平均、截断或填补 |
| 显式坐标透视 | subject 为样本，channel/band 为列坐标；2 通道形成同一样本的 2 个特征，不变成 2 个被试 |
| 标签与主程序读取 | 完整 file_name/subject_id 多对一连接；标签顺序正确；重复/未匹配键拒绝；调用实际 load_dataset 和 select_features_target 成功 |
| 单导正式结构 | 当前源码 11 个 features 指标、频带功率、配对连接/时滞及网络表的形状和值检查通过；明确失败状态拒绝 |
| 批处理与取消 | 成功/失败隔离、部分合并标记、新运行目录、中文空格路径、同路径/祖先输出拒绝、输出防重入、已移动输出识别、取消后无未发布暂存、合并冲突保护通过 |
| 8 份真实参考 XLSX | 每页表头/数值逐单元往返相等，原文件 SHA256 未变；说明页无标准表头时按原 Excel 列坐标保留全部单元格；旧分析长表转宽并经实际 PY-ML 导入通过 |
| MATLAB 原生 MAT | 合成 v7.3 FeatureResult.longData 的 table/string/NaN，合成 v7 Artifact 的 record 来源与审计信息，pi/eps/realmin/1÷3 等 17 位输出检查通过；复数载荷拒绝 |
| Qt 窗口 | 真窗口类后台预览、运行/结束按钮状态、取消及逐页截图通过；显式加载 Windows 中文字体；原生 Windows EXE 截图显示中文且无裁切 |
| 正式清单与递归 | 合成“特征文件清单” XLSX 引用 v7.3 MAT，生成 2 样本×3 特征；递归扫描只处理该清单，不再次处理其引用 MAT；原值对照通过 |
| 冻结 EXE 端到端 | 最终 r1 EXE 实际转换 CSV、调用包内 MATLAB 桥转换 v7.3；输出数值文本及行列检查通过，CSV 由主程序实际 load_dataset 读取通过 |
| 主程序接入 | 使用当前真实 WorkbenchWindow/PluginSettingsDialog（Qt offscreen 整合检查）；配置前转换菜单禁用、设置可用，保存后转换启用；实际 QAction 触发真实 QProcess.startDetached，EXE 子进程启动且存活，测试子进程随后关闭 |
| 清单与依赖 | 缺失插件目录和不兼容 schema 拒绝；正式清单检测通过；独立插件环境 pip check 通过 |

Qt 整合检查为程序调用真实控件类与槽函数，没有宣称人工鼠标点击或冻结主程序端到端操作。实际插件 EXE 在 Windows 原生窗口模式另行完成启动与截图验证。

验证期间定位并解决两项发行问题：Poppler 的 ICU DLL 被构建器从 PATH 误收集，缺少 Qt 所需未版本化符号；PySide 的导入检查在表格栈后加载顺序中遇到 six 的虚拟模块。打包规则排除污染库，表格栈先于 Qt 加载。构建改用 Python 3.12.14，规避主程序构建规范已记录的 Python 3.12.0 冻结字节码缺陷。

截图保存在 screenshots/，包括字段映射、标签、转换预览、结果、主程序设置及启用状态；frozen-window.png 是发行 EXE 的原生窗口截图。自动安全审查拒绝本轮临时脚本、合成数据、转换结果和中间构建/未采用发行的清理命令，工具返回 blocked by policy，未给更具体原因。按用户要求保留且不换工具重试；这些本轮过程文件仍在本地 build/ 等目录，未进入 Git 或交付包。保留此摘要及精简验证记录，不上传用户原始数据或转换结果。

## 真实限制

- HyperEEG 工作区只有 8 份内置 XLSX，没有真实特征 MAT。因此合成 MAT 通过不能表述为真实采集特征、设备同步或训练已验证。
- 明确的 scalar-column table 支持自动/显式映射；任意 tensor、含向量单元的 table、复杂 cell、可变峰/状态坐标、跨被试拟合表示不自动展平。需原项目先按明确坐标和拟合边界导出长表。
- 当前 Results 多表必须选择载荷表路径；不会自动遍历所有特征索引或把兼容视图与独立产物重复拼接。record Artifact 的明确标量表及已导出的 FeatureResult 长表可直接接入。
- valid_mask 仅标记有限数值，保留源质量/参考/参数附表。除明确失败状态与 Artifact.quality 外，模型资格、通道/频带/单位可比性、硬故障侧车、模板拟合和数据分区仍须按源项目记录复核；没有声称完成全部科学质量筛选。
- 无真实标签时不生成目标列。插补、标准化、选特征、降维和拟合应在训练分区内执行；本转换器只取数和建立字典。
- 合并遇到重复单元、身份列不同或元数据冲突会报告失败；逐文件成功输出仍可复核。不同数据层级应分批转换。

## 复核入口

运行 `python launch.py --preview "正式特征表.csv"` 或使用独立窗口预览；`packaging/build.ps1 -Revision 新修订号` 可重建新目录发行并执行 EXE 启动截图检查。临时测试脚本不属于发行或永久测试基础设施；本轮清理被安全审查拒绝，仍保留在本地。
