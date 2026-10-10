"""Export verified final six-row results as paper-ready text, table and CSV."""
import csv
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/summaries/paper_geometry_synthetic_v2'
DATA=ROOT/'data/paper_geometry_synthetic_v2'
PAPER=ROOT/'paper/supplement/DAFR_Synthetic_Geometry_Experiment.tex'


def main():
    r=json.loads((OUT/'summary.json').read_text(encoding='utf-8'))
    manifest=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))
    assert all(hashlib.sha256((DATA/name).read_bytes()).hexdigest()==sha for name,sha in manifest['data_sha256'].items())
    assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha for name,sha in manifest['source_sha256'].items())
    names={'full':'DAFR (synthetic adapter)','simple_linear_rule':'Simple linear rule',
           'no_projection':'w/o Evidence Projection','no_lifting':'w/o Action--Evidence Lifting',
           'no_geometry':'w/o Geometric Constraints','no_feedback':r'w/o Decision \& Feedback'}
    assert set(r['quadratic'])==set(names)
    q=r['quadratic'];n=q['full']['cases']
    delta=r['paired_intervals']['simple_linear_rule']['success_rate']
    lo,hi=[100*v for v in delta['paired_group_95pct']]
    with (OUT/'paper_table.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.writer(f);writer.writerow(['method','cases','initial_accuracy_pct','task_success_pct','unsafe_admission_pct','successful_tasks','unsafe_admissions','false_allow','false_block'])
        for a,title in names.items():
            s=q[a];writer.writerow([title,n,100*(1-(s['false_allow']+s['false_block'])/n),
                 100*s['successful_tasks']/n,100*s['unsafe_admissions']/n,s['successful_tasks'],s['unsafe_admissions'],s['false_allow'],s['false_block']])
    rows={}
    for a,title in names.items():
        s=q[a]
        rows[a]=f"{title} & {100*s['successful_tasks']/n:.1f} & {100*s['unsafe_admissions']/n:.1f} " + chr(92)*2
    def table(arms,caption,label):
        return (r'''\begin{table}[t]
\centering
\small
\setlength{\tabcolsep}{3pt}
\begin{tabular}{lrr}
\toprule
Configuration & Task $\uparrow$ & UAR $\downarrow$\\
\midrule
'''+ '\n'.join(rows[a] for a in arms) + r'''
\bottomrule
\end{tabular}
\caption{''' + caption + '}\n'+r'\label{'+label+'}\n'+r'\end{table}'+'\n')
    comparison_table=table(('full','simple_linear_rule'),
        'Joint geometry versus a simple linear rule on 1,800 quadratic test episodes. Values are percentages. Both methods use the same synthetic adapter, support constraints, evidence, and revision grammar.',
        'tab:synthetic-geometry')
    ablation_table=table(('full','no_projection','no_lifting','no_geometry','no_feedback'),
        'Single-module ablations on the same 1,800 quadratic test episodes. Values are percentages. Each row changes only the specified module of the synthetic implementation.',
        'tab:synthetic-module-ablation')
    tex=r'''% Standalone section fragment; uses the main paper's booktabs package.
% No existing AgentDojo/ASB numbers are reassigned or rerun.
\section{Controlled Synthetic Geometry Study}
\label{sec:synthetic-geometry}

We supplement the benchmark results with a controlled study of the joint-risk
representation. The comparison holds evidence projection, action--evidence
lifting, individual support constraints, and feedback fixed, and replaces
only the curved joint budget with one affine risk rule. Its weights are
trained on the training set and its threshold is selected on the development
set. No nonlinear feature expansion is given to the affine rule.

\subsection{Synthetic Dataset}

\paragraph{Environment and data.}
We construct six-channel tool-action environments with declared quadratic
dissipation: current is determined by a channel-mixing matrix, the proposed
allocation, and current background load. A temperature limit depends on
available capacity and observed cooling support. An independent simulator
computes temperature from raw arguments and state, without reading controller
coordinates or margins. This is a synthetic, uncalibrated engineering model,
not measured hardware or a sampled production workload.
For allocation $q$, the current in channel $j$ is
\begin{equation}
 I_j(q)=B_j+\sum_{i=1}^{6}A_{ji}q_i,
\end{equation}
where $A$ is the channel-mixing matrix and $B$ is the observed background
load. The simulator computes
\begin{equation}
 T(q)=T_{\mathrm{amb}}+\gamma\sum_{j=1}^{6}I_j(q)^2,
\end{equation}
with limit $T_{\max}=T_{\mathrm{amb}}+\gamma(K+C)^2$, where $K$ is base
capacity and $C$ is current cooling support. These raw-state equations
determine the labels; they imply a curved capacity boundary. A matched
linear-law control replaces both quadratic terms with their linear forms.

The generator varies diagonal mixing coefficients in $[0.65,1.3]$,
off-diagonal coefficients in $[0.03,0.15]$, background load in $[0,0.15]$,
base capacity in $[0.9,1.3]$, and initial cooling support in $[0,0.7]$.
Broad proposals, near-capacity proposals, and axis-concentrated proposals
occur equally often among base instances. The throughput floor is sampled
between 45\% and 80\% of the original proposal's throughput. The state
counterfactuals subsequently modify cooling, background load, or locked
allocations without changing the task identity.

The dataset contains 6,480 episodes from 360 base instances. Each instance
has six physical counterfactuals (natural state, no cooling, extra cooling,
concurrent load, a locked channel, and a linear-law control), crossed with
three evidence settings (user-specified target, verified-lookup target, and
an untrusted redirection). Entire base instances are assigned to training,
development, or test, giving 2,160 episodes per split. All generated episodes
are retained. The 1,800 quadratic test episodes and 360 linear controls are
reported separately. The six-channel extension follows an exploratory
three-channel diagnostic; no external preregistration is claimed.

\paragraph{Shared execution protocol.}
A domain-specific deterministic adapter maps verified lookup records and
tool arguments to the paper's action--evidence coordinates. The unchanged
native geometric evaluator instantiates the support halfspaces and joint
norm budget. This experiment is a domain instantiation of the paper's
decision equations, not a rerun of the production natural-language encoder
or an LLM planner. Both comparison arms share a finite revision grammar:
unlocked allocations are jointly scaled from 100\% to 0\% in one-percentage-point
steps, while locked allocations remain fixed. Candidates violating the
allocation caps or throughput floor are excluded. The target identifier
cannot be changed by load revision. No controller receives simulator labels
when constructing or selecting candidates.

\paragraph{Metrics.}
Task success (Task) requires both safe execution and the throughput goal.
The unsafe admission rate (UAR) measures whether the controller forwards an unsafe physical
setting or a wrong-target action. It is not benchmark ASR or an unsafe-commit
rate: the independent physical simulator atomically rejects unsafe settings.

\subsection{Joint Geometry versus a Simple Linear Rule}

The linear comparator replaces only the joint budget by the single rule
$w^\top r+w_c c+b\leq\tau$, with the same channel-risk coordinates $r$
and cooling-support coordinate $c$. All target, grounding, and prerequisite
constraints remain unchanged. Weights are fitted on training data; the
development threshold minimizes five times the unsafe false-allow rate
plus the safe false-block rate. The quadratic test set is used only after
these parameters are frozen.

'''+comparison_table+fr'''
Table~\ref{{tab:synthetic-geometry}} shows that the joint region safely completes {q['full']['successful_tasks']} episodes with zero unsafe
admissions, compared with {q['simple_linear_rule']['successful_tasks']} completions and
{q['simple_linear_rule']['unsafe_admissions']} unsafe admissions for the affine rule.
The task-success difference is {100*delta['full_minus_arm']:.2f} percentage points
(paired base-instance bootstrap, 4,000 resamples; 95\% interval
[{lo:.2f}, {hi:.2f}]). The interval is exploratory and is not adjusted for multiple
comparisons.
'''+r'''

On the 360 linear-law control episodes, the full method and the simple linear
rule both complete 28 tasks with zero unsafe admissions. The evidence
therefore supports the contribution of the curved budget relative to this
simple linear representation under the declared coupled process. It does
not establish superiority over equivalent nonlinear arithmetic, arbitrary
rule systems, or real-world distributions.

\subsection{Module Ablations}

We remove one module at a time while preserving the remaining configuration.
Without Evidence Projection, raw observations remain available with the
declared fallback confidence 0.65, below the critical grounding requirement
0.8. This tests the synthetic adapter's verified-state projection, rather
than the performance of an arbitrary natural-language parser.
Without Action--Evidence Lifting, schema/action-only coordinates replace
provenance and cross-channel relations. Without Geometric Constraints,
schema validity remains active but all geometric filters are removed.
Without Decision \& Feedback, the initial decision is unchanged and
load revision is disabled.

'''+ablation_table+fr'''
Table~\ref{{tab:synthetic-module-ablation}} separates the module effects.
Removing projection reduces safe completions from {q['full']['successful_tasks']}
to {q['no_projection']['successful_tasks']}: lookup-established targets no longer
meet the grounding threshold. Removing feedback reduces completions to
{q['no_feedback']['successful_tasks']}, losing {q['full']['successful_tasks']-q['no_feedback']['successful_tasks']}
tasks recoverable by load revision. Removing lifting yields
{q['no_lifting']['unsafe_admissions']} unsafe admissions because action-only
coordinates omit target provenance and coupled state relations. Removing
geometric constraints yields {q['no_geometry']['unsafe_admissions']} unsafe admissions.
These results concern the paper-aligned synthetic implementation; they
supplement the existing benchmark ablation without replacing it.
'''
    PAPER.write_text(tex,encoding='utf-8')
    (OUT/'paper_table.tex').write_text(comparison_table+'\n'+ablation_table,encoding='utf-8')
    (OUT/'comparison_table.tex').write_text(comparison_table,encoding='utf-8')
    (OUT/'ablation_table.tex').write_text(ablation_table,encoding='utf-8')
    report=['# 最终自建数据与模块消融','',
        '最终比较仅包含一个简单线性加权规则，以及论文定义的四项模块消融。没有重新运行 AgentDojo/ASB，也没有改写现有主表。',
        '',
        '## 数据','',
        '共 6,480 条：360 个基础实例 × 6 个物理状态版本 × 3 个证据版本。训练、开发、测试各 2,160 条；同一基础实例的全部版本留在同一集合。测试中 1,800 条为二次耦合过程，360 条为线性过程控制。',
        '',
        '六通道电流经混合矩阵与背景负载耦合，原始电流平方和产生温度，当前冷却能力决定上限。任务同时要求最低吞吐、分配上限和锁定字段。独立模拟器按原始动作与状态生成标签，不读取几何特征、模型判断或 margin。',
        '',
        '证据版本包括：用户给定目标、可信查询返回目标标识、未可信内容指向错误目标。完整流程与线性对照使用相同证据、特征、授权/目标条件和修订候选；唯一差别是联合风险边界。线性规则的权重只用训练集拟合，阈值只在开发集确定。',
        '',
        '## 结果','',
        '| 配置 | 安全完成 | 错误放行 | 初始误拦截 |','|---|---:|---:|---:|']
    chinese={'full':'完整联合曲面','simple_linear_rule':'简单线性规则','no_projection':'移除 Evidence Projection',
             'no_lifting':'移除 Action–Evidence Lifting','no_geometry':'移除 Geometric Constraints',
             'no_feedback':'移除 Decision & Feedback'}
    for a in names:
        s=q[a];report.append(f"| {chinese[a]} | {s['successful_tasks']} | {s['unsafe_admissions']} | {s['false_block']} |")
    report+=['',f"完成率提高 {100*delta['full_minus_arm']:.2f} 个百分点，按 120 个基础测试实例分组配对 bootstrap，95% 区间 [{lo:.2f}, {hi:.2f}] 个百分点。",
        '',
        '360 条线性控制中，完整方法和简单线性规则均安全完成 28 条，错误放行均为 0。完整曲面在共享候选语法下达到 936 条可恢复任务的独立枚举上限。该上限不表示任意规划器的全局最优。',
        '',
        '## 消融定义','',
        '- Evidence Projection：保留原始观察，移除高置信目标事实投影；原始回退置信度 .65，关键目标 grounding 门槛 .8。这是明确的适配器参数，结果不应解释为任意解析器的普遍优势。',
        '- Action–Evidence Lifting：保留 schema/动作坐标，移除来源关系和跨通道映射。',
        '- Geometric Constraints：移除整个几何过滤，保留 schema 和共享候选语法。',
        '- Decision & Feedback：保留初始几何判断，移除失败后的分配修订。',
        '',
        '## 论文文件及复现','',
        '可插入正文/补充材料的英文实验段落及表格：paper/supplement/DAFR_Synthetic_Geometry_Experiment.tex。独立表格：paper_table.tex；表格数据：paper_table.csv。',
        '',
        '运行 scripts/run_paper_geometry_synthetic.py --channels 6，再运行 scripts/export_paper_geometry_synthetic.py。OPENBLAS_NUM_THREADS=1 和 OMP_NUM_THREADS=1 可避免小矩阵多线程开销。manifest.json 保存模型、参数、数据及源码哈希。inputs、evaluator、labels 分文件保存。',
        '',
        '这批结果属于声明的合成工程过程，采用论文公式对应的确定性领域适配器与原生几何 evaluator；未验证生产自然语言编码器或 LLM 规划器。错误放行表示控制器送出不安全动作，不能写成真实环境已经发生违规提交，也不能写成 benchmark ASR。',
        '',
        '数据全部保留，未按结果筛掉失败样本。三维诊断保存在 v1；最终六维实验属于探索性扩展。当前段落保留这些范围限定，现有论文与 benchmark 主表不自动修改。','']
    (OUT/'final_report.md').write_text('\n'.join(report),encoding='utf-8')
    print('Verified hashes; exported',PAPER)


if __name__=='__main__':main()
