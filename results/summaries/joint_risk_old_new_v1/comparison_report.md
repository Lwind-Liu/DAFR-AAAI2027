# 新旧联合风险：同流程对照

仅替换联合风险判定，来源、授权、版本、误差区间、核验预算、字段顺序、动作和执行流程相同。
旧形状调用原生 RiskBudgetCone，但使用新的共享因果路径适配器；不等于原版完整 45 维生产方法。
独立新种子 20261014；训练/开发/测试按基础实例分组。旧锥形状提供等权及仅训练/开发校准的两个配置，训练包含核验后状态。

| 环境法则 | 风险方法 | 初始错误 | 安全完成 | 越界执行 |
|---|---|---:|---:|---:|
| union_world | new_union_surface | 12 | 635 | 0 |
| union_world | old_cone_equal_weights | 33 | 623 | 37 |
| union_world | old_cone_fitted_weighted | 45 | 594 | 9 |
| union_world | old_cone_fitted_safety_1pct | 42 | 605 | 15 |
| cone_policy_control | new_union_surface | 57 | 635 | 0 |
| cone_policy_control | old_cone_equal_weights | 12 | 660 | 0 |
| cone_policy_control | old_cone_fitted_weighted | 80 | 603 | 0 |
| cone_policy_control | old_cone_fitted_safety_1pct | 65 | 620 | 0 |

两个环境法则各使用全部 1,200 条测试，不混合加权得出“全面更好”。联合概率环境与新法则一致、二次预算控制环境与旧形状一致，均为受控机制诊断。
只有真实工具轨迹上的配对结果、干净任务效用、攻击成功率及必要消融支持收益且控制场景无重大退化，才足以考虑改变论文主线。API 自然语言测试尚未执行。
