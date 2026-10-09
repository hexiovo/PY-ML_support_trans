# PYfNIRs 验证摘要

RUN 证据根路径：H:/AIcode/HexiPlan/runs/pyfnirs-pyml-converter-20261008-01（下文的 reports、evidence 与 approvals 均相对此目录）。

截至 2026-10-09，PYfNIRs 输入契约和转换器 UI 已正式接受；PY-ML host 接入的独立阶段三复核已正式 PASS。本文记录已注册证据与边界，不代表真实研究数据或模型训练验证。

## 阶段一：输入契约（已接受）

- G5 报告 reports/G5-pyfnirs-input-contract-v1/report.json，SHA-256 7614015d2118047050c488f87d58449cb9cdc52a8ac2912f66370a9f3e0dbb6b；接受记录 approvals/0005-step_acceptance.json，SHA-256 9608bf4e8c5f7758e40568ca2bb2cd7d00ee1dcb1c50e54fdaa156acc0816e87。
- 独立 R2 verdict evidence/independent-verdict-r2.json，SHA-256 c1ed7d45ff5bc01382346ff3c8e53d09461b60549b039a50c803d4c82eee11f0，为 PASS；24 项新检查通过，30 项既有通过项有记录复用，原 45 项检查均有通过证据，repair round 1 保留。
- 32 项 raw 候选中只有 3 个明确子形态为条件支持，其余 29 项和其他子形态保持 unverified。

## 阶段二：转换器 UI（已接受）

- G5 报告 reports/G5-pyfnirs-converter-ui-v1/report.json，SHA-256 7043361d9172655a696e0e3439c04f63426259974172ebadc2342ba563e13adc；接受记录 approvals/0007-step_acceptance.json，SHA-256 e3af1ab0c0caba0d37b95e2a5fa93230d2ff883c2c7486490a85fa28f00aed36。
- 独立阶段二 verdict evidence/independent-stage2-verdict-r2.json，SHA-256 1495748819f732745e5ac46fd06c73e00432c7f6fb04f0d889b1e13d0f3873ca，为 PASS，repair round 1 保留；R2 检查结果 evidence/independent-stage2-results-r2.json，SHA-256 cb9c65c9940da4fff3f7adf37db07ef407b63033caafd3459717877abbc16b22，记录 19 项新检查通过、17 项此前通过项复用。
- MATLAB R2023a raw 合成闭环报告 evidence/raw-feature-production-closure-r1.json，SHA-256 9b22dc32ae80c558f3ff6394c1c60884aa078a08796408ff361becbb71b82a06。原生 raw MAT 使用外部 MATLAB；没有真实研究数据验证，MLInput.mat 输出尚未实现。

## 阶段三：PY-ML host 接入（独立复核 PASS）

- 实际 host 接口报告 evidence/independent-stage3-interface-results-r1.json，SHA-256 372ce16e617e09fc5fbbcb1f06bad0045dde0ad99ef087c86a82889663a5f651：16/16 检查通过，覆盖冻结转换器 CSV/XLSX 经 host reader 的精确值与列选择、负零与 binary64 边界、缺失掩码、空行/混合列、大整数、独立设置、旧 HyperEEG 检测及冻结文件哈希。
- 正式验证报告 evidence/independent-stage3-verification-r1.md，SHA-256 4c411a8091a60b7b390edbb978c0b6ab3577c72eef89c0eb2790576d673e7db4；正式 verdict evidence/independent-stage3-verdict-r1.json，SHA-256 abbbdc10f2bc8457327bbc3ee3644e2ab0b9792b709038dc6d36f81281768a65，为 PASS，21/21 criteria PASS（16 项接口检查逐项映射，另 5 项复用已冻结材料/运行证据）。最终材料索引 evidence/independent-stage3-final-materials-r1.json，SHA-256 f64f580a2297bf1d4ead7b214c066df424342ca28339fe30345995b016a8ac03。
- G4 冻结证据索引 evidence/pyml-integration-release-20261009/evidence-index.json 保持不变，SHA-256 9aecd489d103775e1c7b7d5c7f0c56253a4dd26175072e113fbf7d52bd073ed6。正式 EXE SHA-256 cb77fe424a0f90d455263e49ac93e5834dcbc6fd98b8ff37b311baaf07045229；manifest SHA-256 bd021cf74ec6313678ac4ed34471547d081b35cefad9887564d3958e032ffd56。
- 上述 PASS 是阶段三独立技术复核结论；本次 G5 最终交付报告另行记录 Git 实绩、限制和清理状态，不将 Git 操作作为该技术 verdict 的断言。

## 交付边界

- 新菜单由 run_pyml_workbench.bat 源码入口提供；已安装的 PY-ML 桌面应用未重建。发行时须将 EXE、_internal 和 pyml-plugin.json 整个目录一起复制。
- host 补丁和 before hashes 已保存于 docs/host-patches/PYfNIRs/。host patch 是以记录的 dirty baseline 为前置的增量，不可直接应用于缺少 generic plugins.py 与 plugin_dialog.py 的旧 clean HEAD。
- 实际模型路由仍为 UNVERIFIED。仅合成夹具用于上述检查；没有真实研究数据验证。raw MAT 需外置 MATLAB R2023a；29 项候选仍未验证，且当前不输出 MLInput.mat。
- 自动清理被策略拒绝（RUN adapter note seq 79）；没有删除文件，保留的生成材料仍留在 RUN/工作树。support/master 选择性源码交付的实际 commit 与远端推送确认见本次 RUN 最终交付记录；本摘要不把 Git 状态写作技术验收结论。
