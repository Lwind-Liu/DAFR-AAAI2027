# 2026-10-16 实验工作区更新

发布分支：`geometry-synthetic-ablation`。本次更新不合并 `main`、`jianghao` 或 `mapper-handoff`。

## 使用入口

| 内容 | 路径 |
|---|---|
| 原始 104 个任务，干净/攻击共 208 条 | `data/workflow_catalog_104/cases.jsonl` |
| 原始数据的多模型主表运行入口 | `scripts/run_synthetic_main_table.py` |
| 原始 104 任务主表实测记录 | `results/summaries/catalog_fixed104_adapter_v11_104/` |
| 原始消融汇总与新增四条任务记录 | `results/summaries/workflow_catalog_104/` |
| 原始前 100 条任务消融记录 | `results/summaries/workflow_catalog_v2/` |
| 104 任务的工具协议分步版本 | `data/workflow_catalog_104_protocol_v1/` |
| 分步接口与回放验证脚本 | `scripts/catalog_protocol_refinement.py`、`scripts/refine_catalog_104.py` |
| 分步版本回放审计与概览表 | `results/summaries/catalog_protocol_refinement_v1/` |
| 桌面“表”中的最新 PDF / TeX 副本 | `paper/writer_bundle_20261016/` |

`scripts/run_synthetic_main_table.py` 继续使用原始 104 任务，不会自动切换到协议分步版本。

## 版本与结果口径

- `workflow_catalog_104` 为已有实测使用的数据，保留其任务、攻击和方法实现。
- `workflow_catalog_104_protocol_v1` 只细化读取、核验和对账接口。已对 1,040 条原动作轨迹回放，核验 1,144 个防御判定点；业务状态和最终结果保持一致。
- 上述协议分步版本的调用数与轨迹长度来自确定性回放，尚未进行新接口下的模型自主全量评测；不能将旧 CU / UA / ASR 作为新版独立实测成绩。
- `heterogeneous_native_pilot_v1` 是另行探索的原生工具试验，包含部分执行/异常记录，不作为 104 任务的替代版或最终主表。
- 其他带 `pilot`、`probe`、版本号的目录保留探索过程。写论文时按各目录协议、模型与完成状态选择记录，不能混合不同运行。
- 写作者附件保留英文图表、中文解释；这是桌面当前版本的快照，各图表的实测或回放口径以表下注释为准。

## 下载与复现

GitHub Release 的 `DAFR-workspace-update-20261016.zip` 包含完整 Git 可见工作区快照和历史归档；无需覆盖已有实验目录，建议解压到新目录。

包内 `WORKSPACE_PACKAGE_MANIFEST.json` 给出每个文件的 SHA-256；Release 同时提供压缩包的 `SHA256SUMS.txt`。本机虚拟环境、缓存、API 密钥和被 Git 忽略的配置不包含在包内。

分步版本的离线检查（不调用 API）：

```text
python scripts/refine_catalog_104.py
python -m pytest tests/test_catalog_protocol_refinement.py -q
python scripts/render_refined_catalog_profile.py
```

绘表脚本沿用本地 Windows 中文字体与桌面输出路径；在其他机器上使用时需调整字体和输出目录。模型运行需要自行配置 API，原始多模型交付说明见此前的 `synthetic104-v1-20261013` Release。
