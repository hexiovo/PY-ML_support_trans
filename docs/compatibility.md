# PYfNIRs → PY-ML 32项能力兼容矩阵

RUN：`pyfnirs-pyml-converter-20261008-01` · stage 2：少数明确 raw Results 子形态已按合成 MATLAB oracle 完成生产路径闭环。

本矩阵记录上游 MATLAB 源能力、计划投影和转换器实际验证状态。A/B/C描述源数据现状，不代表 PY-ML 支持结论。当前仅第 07 项的静态 Pearson、第 14 项的非窗口 MVAR-Granger 和第 24 项的持续同调 `TotalPersistence` 精确条件子形态为 `conditionally_supported`；其余 29 项以及这三项的其它形态仍为 `unverified`。验证使用 MATLAB R2023a v7.3 合成 MAT，不代表真实研究数据验证。

A＝已有固定科学输出；B＝已有输出但需专门汇总/投影/身份核验；C＝函数返回但无固定自动 MAT 保存接口，需显式调用和导出。

目标组织为 `analysis_input.mat` 中的 `study.Values` 长表（唯一键 `(ObservationID, FeatureID)`），并由 `FeatureDefinitions`、`Observations`、`PairLinks` 描述列与样本身份。该长表不表示32类原始MAT源均可直接读取。

| # | 源类别 | 能力 | 源字段与形状证据 | 转换器状态 | 计划投影 | 明确拒绝/暂缓 |
|---:|:---:|---|---|:---:|---|---|
| 01 | A | Hurst 指数 H | 路径：R.data.all{1}.(Hb)，double 节点向量，通常 1×N。；来源：CHHurst / ROIHurst，独立文件通常为 *-Hurst.mat。；路径：R.data.all{1}.(Hb)，double 节点向量，通常 1×N。 | planned / unverified | 用法：每个 CH/ROI、每种实际 Hb 各一列，记录级特征。 | 未由本项方案确认的投影暂缓；仍遵守全局身份、缺失和防泄漏规则。 |
| 02 | A | Shannon 微分熵 | 路径：R.data.all.(Hb)，double，通常 1×N。；来源：CHSE / ROISE / SE_caculate。；路径：R.data.all.(Hb)，double，通常 1×N。 | planned / unverified | 用法：每节点/每 Hb 一列，保留 KDE/标准化版本。 | 实际含义：信号先按本记录标准化，再用 KDE 估计的微分熵，log2，不能称为离散计数熵。 |
| 03 | A | 归一化频谱熵 | 路径：R.data.all.(Hb)，double，通常 1×N。；来源：CHSpEn / ROISpEn / SpEn_caculate。；路径：R.data.all.(Hb)，double，通常 1×N。 | planned / unverified | 用法：每节点/每 Hb 一列，频率支持和 Welch 设置一致。 | 这是 SpEn Pipeline 的实际实现；不能因为某个目录描述写了 sample entropy 就当作样本熵。 |
| 04 | A | 多尺度样本熵与复杂度指数 | 路径：R.data.all.(Hb){n}，cell 每节点一个 struct。；尺度向量：.ScaleFactors，double，1×S；样本熵：.SampEn，double，1×S。；复杂度：.ComplexityIndex，double 标量。；来源：calculateMultiscaleEntropyFolder，文件 *-MSE.mat。；路径：R.data.all.(Hb){n}，cell 每节点一个 struct。；尺度向量：.ScaleFactors，double，1×S；样本熵：.SampEn，double，1×S。；复杂度：.ComplexityIndex，double 标量。 | planned / unverified | 用法：固定节点/Hb/尺度的 SampEn 各一列；或固定尺度集合的 ComplexityIndex 各一列。 | 要求：所选尺度有效，采样率/实际尺度秒数可比；复杂度若使用的有效尺度集合不同，不可直接当作同一特征。 |
| 05 | A | RQA 有效递归结构量 | 路径：R.data.all.(Hb){n}.(Metric)，cell→struct→double 标量。；路径：R.data.all.(Hb){n}.(Metric)，cell→struct→double 标量。 | planned / unverified | 用法：节点×Hb×指标展开。线长指标按当前采样/嵌入步长的点数解释，不能未经换算称为秒。 | 用法：节点×Hb×指标展开。线长指标按当前采样/嵌入步长的点数解释，不能未经换算称为秒。 |
| 06 | B | HbO-HbR 相位差编码 | 全段路径：R.data.all.HbO，double，通常 1×N。；窗口路径：R.data.all{w}.HbO，cell 每窗口一个节点向量。；来源：CHHpod / ROIHpod，文件 *-Hpod.mat。；全段路径：R.data.all.HbO，double，通常 1×N。；窗口路径：R.data.all{w}.HbO，cell 每窗口一个节点向量。；窗口起点当前文件可能需要由显式窗长、步长和已验证采样率恢复，并记录其来源；仅凭 cell 序号不能猜测实际时间。 | planned / unverified | ML 列：sin(θ)、cos(θ)。全段已有 θ，编码为新增整理步骤。 | 窗口汇总：先规定窗口范围，再计算平均 sin(θ)、平均 cos(θ)，也可由二者求圆均值；不能直接对跨 ±π 的角度做算术均值。；当前 DA 的 HPOD 窗口汇总是算术 mean，不具备本方案的圆统计处理。跨窗口圆统计需补提取步骤，不能视为现成能力。；窗口起点当前文件可能需要由显式窗长、步长和已验证采样率恢复，并记录其来源；仅凭 cell 序号不能… |
| 07 | A | 静态 FC 边 | 路径：R.data.all.(Hb)，double，N×N。；来源：StaticFC / FC_pipeline，文件 *-FC.mat。；用法：无向边只取节点顺序 i<j。 | conditionally_supported：仅 `Kind=static`、`ModelIndex=1`（Pearson）、有限对称 N×N 矩阵、唯一明确 NodeOrder 和非空参数指纹；其余模型仍 unverified | 用法：按固定节点标签和实际 Hb 展开无向边；示例 ROI-A/ROI-B，HbO=0.25。 | WTC 的全矩阵平均相干不能标成指定频带 WTC；Pearson 之外的模型、MI、lag 特征均无证据，不能套用 Pearson 变换或虚构 lag。 |
| 08 | A/B | 动态 FC 窗口均值 | 路径：R.data.all{w}.(Hb)，cell，W 份 N×N double 矩阵。；时间元数据：R.Metadata.FC.WindowStartSeconds / WindowLengthSeconds / WindowStepSeconds。；路径：R.data.all{w}.(Hb)，cell，W 份 N×N double 矩阵。 | planned / unverified | 用法：预定义区间内逐边 mean；当前 DA 支持 equal_windows 均值及最低覆盖检查。 | 窗口不能在记录级预测中被随意当作独立样本；按被试/配对分组后才允许形成窗口级训练单元。 |
| 09 | A | PLV 边 | 路径：R.data.all.(Hb)，double，N×N。；来源：CHPLV / ROIPLV。；路径：R.data.all.(Hb)，double，N×N。 | planned / unverified | 用法：严格上三角，每边一列，取值范围 0–1，参数/信号阶段一致。 | 未由本项方案确认的投影暂缓；仍遵守全局身份、缺失和防泄漏规则。 |
| 10 | A | 频带相干性 | 路径：R.data.all.(Hb){i,j}，N×N cell，每格 F×1 double 相干谱。；频率：R.frequency，F×1 double。；来源：CHCoherence / ROICoherence。；路径：R.data.all.(Hb){i,j}，N×N cell，每格 F×1 double 相干谱。；频率：R.frequency，F×1 double。 | planned / unverified | 用法：事先指定频带 [f_low,f_high]，逐边取频带 mean，严格上三角。 | 未由本项方案确认的投影暂缓；仍遵守全局身份、缺失和防泄漏规则。 |
| 11 | A | OD 频带功率 | 路径：R.data.all{n}，节点 cell，每项 F×1 double。；频率：R.frequencies，F×1 double。；来源：Welch_pre / PSD_pipeline 的谱计算阶段。；路径：R.data.all{n}，节点 cell，每项 F×1 double。；频率：R.frequencies，F×1 double。 | planned / unverified | 用法：同一频带 trapezoidal integral，单位 OD²；或 mean PSD，单位 OD²/Hz。应分别定义，不能混为一列。 | 用法：同一频带 trapezoidal integral，单位 OD²；或 mean PSD，单位 OD²/Hz。应分别定义，不能混为一列。 |
| 12 | A | OD 交叉谱投影 | 路径：R.data.all{i,j}，N×N cell，每格 F×1 complex double。；频率：R.frequency，F×1 double。；来源：CSDcaculate，文件 *-CSD.mat。；路径：R.data.all{i,j}，N×N cell，每格 F×1 complex double。；频率：R.frequency，F×1 double。 | planned / unverified | 用法：固定上三角边和频带，选择 magnitude 的均值/积分，或 real 的均值/积分。 | 复数本体不能当作一个实数特征；谱幅值、实部、相位是不同列定义。 |
| 13 | A | 动态 FC 边的 Hurst 指数 | 路径：R.data.all{1}.(Hb)，double，N×N。；来源：FCHurst，针对每条动态连接序列计算 H。；路径：R.data.all{1}.(Hb)，double，N×N。 | planned / unverified | 用法：仅取原单脑网络严格上三角，保留动态窗口步长与方法定义。 | 窗口序列的采样率是动态窗口时间尺度，不能沿用原始 Hb 时间点的采样率解释。 |
| 14 | A/B | 脑内 MVAR-Granger 有向边 | 路径：R.data.WithinBrainMVARGranger.(Hb).GrangerStrength，double，N×N。；来源：MVARGranger_pipeline，文件 *-MVAR-GRANGER.mat。 | conditionally_supported：仅完整记录、`Status=ok`、冻结公式与方向约定、匹配节点顺序，且 `Window.Enabled=false`；窗口 cell 仍 unverified | 保持有向 i→j 轴，不转成无向上三角；示例 ROI-A→ROI-B=0.3，反向=0.7 | 当前证据不覆盖窗口化输出、其他公式/参数或真实研究数据；仅矩阵可读不足以证明同一 Granger 含义。 |
| 15 | A | IBS 跨脑连接强度 | 路径：R.data.all{1}.(Hb)，double，NA×NB。；来源：runPairedIBS（CH2IBS / ROI2IBS 调用）。；路径：R.data.all{1}.(Hb)，double，NA×NB。；用法：A 脑节点×B 脑节点全矩阵展开，包括 A_i-B_i；两个人的同名节点不是单脑自身连接，不得删除“对角线”。；同步、事件时钟、分析支持或配对语义未核实时，不进入可用脑间特征矩阵。 | planned / unverified | 用法：A 脑节点×B 脑节点全矩阵展开，包括 A_i-B_i；两个人的同名节点不是单脑自身连接，不得删除“对角线”。 | 用法：A 脑节点×B 脑节点全矩阵展开，包括 A_i-B_i；两个人的同名节点不是单脑自身连接，不得删除“对角线”。 |
| 16 | A | IBS 互相关时滞 | 路径：R.data.all{2}.(Hb)，double，NA×NB，单位 samples。；来源：runPairedIBS 中 IBScaculate 的 model=5。；路径：R.data.all{2}.(Hb)，double，NA×NB，单位 samples。 | planned / unverified | 用法：逐跨脑边一列，可按实际信号采样率另算 lag_seconds=lag_samples/Fs。 | 必须记录 A/B 顺序、符号约定、所用记录信号的实际采样率。其它模型的初始化零 lag 不作为科学特征。 |
| 17 | B | 跨脑 WTC 频带相干谱 | 路径：R.data.all{1}.(Hb){i,j}，NA×NB cell，每格 F×1 double，已沿时间平均。；来源：CHFOI / ROIFOI / FOIcaculate，单配对文件 *-FOI.mat；这是群体选频检验之前的科学相干谱。；路径：R.data.all{1}.(Hb){i,j}，NA×NB cell，每格 F×1 double，已沿时间平均。；对应频率：R.data.all{2}.(Hb){i,j}，double 频率向量，逐边核对。；用法：A_i-B_j 全跨脑矩阵，预定义频带平均或同一网格谱向量。保留角色轴，不强行当作单脑对称上三角。；当前 DA WTC 谱提取不是此双… | planned / unverified | 用法：A_i-B_j 全跨脑矩阵，预定义频带平均或同一网格谱向量。保留角色轴，不强行当作单脑对称上三角。 | 当前 DA WTC 谱提取不是此双 cell 层级/跨脑轴的通用读取器，需要单独适配。；旧文件若仅有文件名配对，必须借真实研究表补充双方记录身份、角色与同步证据后才纳入，不能从名称推断已对齐。 |
| 18 | B | 显式对称化的频带 IBS | 单配对路径：R.data.all.(Hb)，N×N double，来源 IBS_mean_caculate，文件 *-FOI-IBS.mat。；列身份：R.group；边标签：R.label。group 在此来自文件名，不是可以直接作为 y 的实验组标签。；单配对路径：R.data.all.(Hb)，N×N double，来源 IBS_mean_caculate，文件 *-FOI-IBS.mat。；聚合文件 TaskIBS.mat / RestIBS.mat：R.data.all.(Hb)，[E×M] double，E=N(N+1)/2，为含对角线的边数，M 为配对观察数。；用法：单配对按上三角含对角线展… | planned / unverified | 用法：单配对按上三角含对角线展开；聚合矩阵转置为 [M×E] 并严格匹配文件标签与真实 PairObservationID。 | 它与第 15/17 项保留角色的全矩阵定义不同，不能沿用同一 FeatureID。多个频段被现有函数合并为一个均值，不能宣称文件已分别保存每个频段列。 |
| 19 | A | 节点图指标 | 来源：AutoGraphic / GraphicMetrics_pipeline，文件 *_Graphic.mat。；统一路径：R.data.all{d}.(Hb).(Metric)，struct 内 double 节点向量。 | planned / unverified | 用法：节点×Hb×固定密度×binary/weighted，各一列；不同图类型是不同定义。 | 社区依赖指标仅在可用且有限时纳入。不能把每份数据中的社区编号直接当作统一类别。 |
| 20 | A | 全局图指标 | ；统一路径：R.data.all{d}.(Hb).(Metric)，double 标量。 | planned / unverified | 固定密度单独取值，或预定义共同密度区间的图指标曲线/AUC；AUC为新增整理。 | charpath/radius/diameter 等非有限值按缺失处理，不能把 Inf 填成零。若改用可达路径语义，必须另建列定义，不能静默替换。 |
| 21 | A | 任务 GLM 系数与预登记对比 | 路径：Results.Analyses.TaskResponse.(LEVEL)(r).Outputs(o).Beta，double 系数向量。；路径：Results.Analyses.TaskResponse.(LEVEL)(r).Outputs(o).Beta，double 系数向量。 | planned / unverified | 用法：按任务条件与设计列精确选择 Beta；或固定、按完整列顺序匹配的 c'β。 | 当前 DA selectedTask 还要求统一 Designs。多设计/个体化情况下应单独核对，不能声称所有任务响应都已可直接提取。 |
| 22 | B | 任务响应曲线 | 路径：Results.Analyses.TaskResponse.(LEVEL)(r).Outputs(o).ResponseCurves(c).EstimatedResponse，double 时序向量。；路径：Results.Analyses.TaskResponse.(LEVEL)(r).Outputs(o).ResponseCurves(c).EstimatedResponse，double 时序向量。；曲线是已有输出，摘要提取是新步骤。不同条件不能混合为一个未注明条件的向量。 | planned / unverified | 用法：在预先指定的共同时间范围和网格上，作为固定曲线输入；或新增计算响应 PeakValue、PeakTime、Mean、Area、Slope 等摘要。 | 曲线是已有输出，摘要提取是新步骤。不同条件不能混合为一个未注明条件的向量。 |
| 23 | B | 正则化 HRF 去卷积估计时序 | 路径：Results.Analyses.TaskResponse.(LEVEL)(r).Outputs(o).Deconvolution.EstimatedNeuralActivity。；类型：T×1 double。要求 .Status='complete'，明确观察掩码及共同 HRF、Lambda、DifferenceOrder 和边界处理。 | planned / unverified | 用法：固定网格的模型估计序列或预登记时段摘要；不要把它解释为直接测得的神经活动。 | 放在实验性候选块，先用训练数据验证增量价值，不作为第一版默认输入。 |
| 24 | A | 持续同调标量 | 路径：R.data.PersistentHomology.(Hb).Features.H0 / H1；类型：double 标量；来源：PersistentHomology_pipeline，文件 *-PH.mat。 | conditionally_supported：仅 `Status=ok`、节点顺序及输入语义/阈值/距离定义一致的 `TotalPersistence` 标量；其他组件仍 unverified | 示例 HbO H0 `TotalPersistence=2.5`；源 NaN 按 invalid + `source_nonfinite` 保留 | 不覆盖其它同调统计量、外部库语义或真实研究数据；无效值不补 0。 |
| 25 | B | Betti 曲线和 Persistence Image | ；曲线路径：R.data.PersistentHomology.(Hb).BettiCurve.H0 / H1，double 向量。；图像路径：R.data.PersistentHomology.(Hb).PersistenceImage.H0 / H1.Image，double 二维矩阵，仅启用时存在。 | planned / unverified | 用法：共同 filtration 网格上展开曲线；共同 birth/persistence 范围和固定分辨率下展开 Image 或作为图像输入。 | 必须固定轴范围、网格、Sigma、权重和归一化。当前自动按各记录范围生成的图像不能仅因像素数相同就拼接。 |
| 26 | A/B | 共享 Gaussian HMM 状态占比 | 来源文件：Shared-GHMM.mat，顶层 Results，显式 -v7.3。；逐记录占比：.Result.PosteriorOccupancy，1×K double；.Result.ViterbiOccupancy，1×K double。；逐记录转移：.Result.TransitionCounts，K×K double；新增行归一化形成每记录的…；逐记录占比：.Result.PosteriorOccupancy，1×K double；.Result.ViterbiOccupancy，1×K double。；逐记录转移：.Result.TransitionCounts，K×K double；新增行归一化形成每记录的经验转移概率，零访问行记为缺失。；停留：.Result.DwellDurations… | planned / unverified | 逐记录占比：.Result.PosteriorOccupancy，1×K double；.Result.ViterbiOccupancy，1×K double。 | 未由本项方案确认的投影暂缓；仍遵守全局身份、缺失和防泄漏规则。 |
| 27 | B | 多模态早期融合表示 | 路径：Results.Data.EarlyFusion.Training(r).FusedValues / Validation(r).FusedValues。；类型：double，T_r×P，并非自动一记录一行。；列名：同一条目 .FeatureNames，cell 文本；模态来源：.ModalitySource；可用行：.CommonValidMask。 | planned / unverified | 用法：固定序列或预登记记录级摘要；已有融合只对提供的上游 EEG/fNIRS 特征进行同步/融合，不据此虚构原始 EEG 自动特征提取能力。 | 当前 DA 不是该表示的通用直接适配器，需要独立整理。 |
| 28 | B | 预处理 Hb 时序 | 累计路径：Results.Data.CH.Subjects(r).Results.dc.dataTimeSeries。；累计路径：Results.Data.ROI.Subjects(r).Results.data.all{n}.(Hb)。；CH 独立路径：R.dc.dataTimeSeries，T×(3N) double。；ROI 独立路径：R.data.all{n}.(Hb)，每节点 T×1 double；时间 R.timeseries。 | planned / unverified | 用法：经验证的共同时间单位/采样网格，统一节点次序和固定任务窗，整理为 [样本×时间×节点×Hb]。 | 第一版普通表格模型优先用上述已计算摘要。HbT=HbO+HbR 的冗余是否有必要保留，在训练折中评估，不能把三者视为独立测量。 |
| 29 | B | 已明确登记的特征基线差值 | 路径：Results.Analyses.BaselineCorrection.Feature(r).Difference，double，形状与目标特征一致。；定义/轴：同一条目 .FeatureDefinition / .DefinitionFingerprint / .AxisLabels。；路径：Results.Analyses.BaselineCorrection.Feature(r).Difference，double，形状与目标特征一致。；差值矩阵是差值特征，不能继续当成 raw Pearson 相关或距离。 | planned / unverified | 用法：已认可的单节点/边等特征 task-minus-baseline 或预登记参照差值。 | 差值矩阵是差值特征，不能继续当成 raw Pearson 相关或距离。；当前 DA BASELINE_CORRECTION 为 preview，需专门映射到 ML 列；校正来源元数据本身不作为特征。 |
| 30 | C | 通用信号摘要 | 函数：calculateSignalFeatures，返回 MATLAB table，每信号一行。；函数：calculateSignalFeatures，返回 MATLAB table，每信号一行。；SignalName 为 string 键，其余候选为 double。这里只选一套峰/谷名称，避免与同义极值列重复。 | planned / unverified | 函数：calculateSignalFeatures，返回 MATLAB table，每信号一行。；可用候选列：Mean、Median、StandardDeviation、Rms、Range、PeakValue、PeakTimeSeconds、TroughValue、TroughTimeSeconds、AbsoluteArea、LinearSlope、… | 未由本项方案确认的投影暂缓；仍遵守全局身份、缺失和防泄漏规则。 |
| 31 | C | 单尺度样本熵 | 函数：calculateSampleEntropy，返回 double 标量。；函数：calculateSampleEntropy，返回 double 标量。 | planned / unverified | 函数：calculateSampleEntropy，返回 double 标量。；存储现状：没有自动固定 MAT 路径；如实施，新增明确节点/Hb/参数的长表保存。 | 与 SpEn 分开命名，不能相互替代；与 MSE scale=1 重复时只保留一套。 |
| 32 | C | 通用双信号连接摘要 | 函数：calculateConnectivityMetrics，返回 struct，各数值候选为 double 标量。；函数：calculateConnectivityMetrics，返回 struct，各数值候选为 double 标量。 | planned / unverified | 用法：按单脑边或跨脑边明确登记；Pearson/FisherZ 二选一，LagSamples/LagSeconds 二选一，角度用 sin/cos 编码。 | 未由本项方案确认的投影暂缓；仍遵守全局身份、缺失和防泄漏规则。 |

## 通用身份与数据约束

- 记录级来源须按稳定记录键联结 `study.Observations`；配对结果使用 `PairObservationID` 和 `study.PairLinks`，保留双方身份与角色。cell下标、XLSX行序、文件名都不能作为样本身份。
- 每列保留Hb、节点/角色、频带、窗口、尺度、单位、变换、方向、维度、参数指纹及映射指纹。
- 无效/缺失用 `IsValid`、`MissingReason` 和mask表达；不补0，不静默删行/列。标签和协变量须显式联结并核对预测时点。
- 统计型 `results.xlsx` 不含完整 `study.Values`，不能替代逐样本训练矩阵。

## 已核实的语义边界

- 第03项依 `SpEn_caculate.m`：Welch功率谱概率分布归一化后计算Shannon频谱熵。DA `adapterCatalog.m` 却把SPEN标为sample entropy，且 `adaptResult.m` 将SE/SPEN映射到同一负载字段。转换必须按算法实现和定义消解冲突，不能仅凭SPEN名字判为样本熵。
- 第04项folder exporter当前保存HbO/HbR尺度结果；第06项Hpod的HbO字段承载HbO-HbR相位差，不能按字段名推断普通HbO浓度。
- 第30–32项分别返回table、标量和struct但没有固定自动MAT保存接口；须增加显式调用、稳定身份键和FeatureDefinition后才能导出。
- 可读格式不等于科学语义兼容；有向MVAR、IBS角色轴、曲线/图像、基线差值和去卷积时序需遵循逐项条件。

## Stage 2 状态更新

实际使用 MATLAB R2023a（9.14.0.2206163）的 v7.3 合成 raw Results MAT，经 MATLAB helper、生产 registry 和转换核心生成 CSV/XLSX，并按独立 expected 核对身份、FeatureDefinition、参数、值、掩码和缺失原因。已验证的限定条件如下：

- 第 07 项仅静态 Pearson（`ModelIndex=1`），要求非空参数指纹、唯一节点顺序及与其匹配的对称 N×N 矩阵。其余 FC 模型、WTC 频带、MI 和 lag 仍未验证。
- 第 14 项仅非窗口 MVAR-Granger，要求 `Status=ok`、冻结公式 `conditional_log_residual_variance_ratio_v1`、方向约定 `row_source_column_target`、匹配节点顺序以及 `Window.Enabled=false`。窗口输出和其它公式仍未验证。
- 第 24 项仅 `TotalPersistence` 标量，要求 `Status=ok`，并核对节点顺序、输入语义、阈值和距离定义。其它组件及外部库语义仍未验证。
- 独立 expected 核对得到的顺序值为 `[2.5, 0.25, 0.3, NaN]`，有效掩码为 `[true, true, true, false]`，缺失原因是 `source_nonfinite`；身份为 `OBS-SYN-17 / REC-SYN-17 / SUB-SYN-9`，目标标签为 `synthetic_case`。这证明的是合成夹具闭环，不是真实研究数据验证。
- 其余 29 项保持 `unverified`；跨脑 IBS 第 15 项也保持 `unverified`。当前支持目录提供 CSV 文件组和 XLSX；提议的 `MLInput.mat` 权威输出尚未实现，读取原生 MAT 仍通过 MATLAB bridge。

完整运行记录：RUN `evidence/raw-feature-production-closure-r1.json`，SHA256 `9b22dc32ae80c558f3ff6394c1c60884aa078a08796408ff361becbb71b82a06`。顶层状态与每个限定条件的来源证据见 [`../pyfnirs/pyfnirs_converter/capabilities.json`](../pyfnirs/pyfnirs_converter/capabilities.json)。操作流程见[转换器使用说明](PYfNIRs转换器使用说明.md)。
