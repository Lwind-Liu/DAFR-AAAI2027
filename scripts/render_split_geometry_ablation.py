"""Separate geometric-versus-linear comparison from component ablations."""
import json
from pathlib import Path
import shutil

from archive_chinese_tables import ROOT, DEST, small_table


def main():
    summary = json.loads((ROOT / 'results/summaries/workflow_catalog_104/summary.json').read_text())
    assert summary['complete'] and summary['completed_episodes'] == 1040
    source = {r['arm']: r for r in summary['rows']}
    out = ROOT / 'results/summaries/catalog_table_split_v1'
    specs = [
        ('合成消融', '合成数据模块消融',
         [('full', 'DAFR'), ('no_projection', 'w/o Evidence Projection'),
          ('no_lifting', 'w/o Action--Evidence Lifting'),
          ('no_geometry', 'w/o Feasibility Constraints')],
         '模块消融：在完整 DAFR 上分别移除证据投影、动作–证据绑定和可行性约束，考察各模块对任务效用与安全性的贡献。\n'
         '每种配置使用相同的 104 个配对任务、DeepSeek-v4-flash-0731、工具接口和执行预算，共执行 104 次干净任务与 104 次攻击任务。\n'
         'CU 为干净任务完成率，UA 为攻击条件下原任务完成率，ASR 为攻击者目标达成率，单位均为百分比。Total Tool Calls 为 208 次执行的工具调用总数，包含被拒绝的有效提交。\n'
         'w/o Evidence Projection：取消按来源区分证据可信度，工具观察中的声明也进入证据表示。\n'
         'w/o Action–Evidence Lifting：取消证据与具体动作参数、请求、版本及执行权限的严格绑定。\n'
         'w/o Feasibility Constraints：关闭半空间和联合风险的执行准入检查。各配置保留工具参数校验和反馈机制。',
         'DAFR_Custom_Dataset_Ablation'),
        ('几何对比', '几何建模与线性规则对比',
         [('full', 'DAFR'), ('linear', 'Linear Rules')],
         '几何建模对比：在相同动作–证据坐标上，比较 DAFR 的完整几何可行域与简单线性判别规则。完整几何可行域同时包含半空间约束和联合风险曲面；线性规则替代整个几何判别部分。\n'
         '两种配置保留相同的证据投影、动作–证据绑定、工具参数校验和反馈机制，使用相同的 104 个配对任务、模型和执行预算，每种配置共执行 208 次。\n'
         'CU、UA、ASR 分别为干净任务完成率、攻击条件下原任务完成率和攻击者目标达成率，单位为百分比。Total Tool Calls 为全部执行的工具调用总数，包含被拒绝的有效提交。\n'
         '该对比用于展示几何建模相对于线性判别在任务效用与安全性上的收益。',
         'DAFR_Custom_Dataset_Geometry_Comparison'),
    ]
    for folder, title, configurations, caption, stem in specs:
        destination = out / folder
        headers = ['Configuration', 'CU (%) ↑', 'UA (%) ↑', 'ASR (%) ↓', 'Total Tool Calls']
        cells = [[label, *[f"{source[arm][metric]:.1f}" for metric in ('CU', 'UA', 'ASR')],
                  str(source[arm]['total_tool_calls'])] for arm, label in configurations]
        small_table(destination, headers, cells, caption, title)
        writer_folder = DEST / folder
        writer_folder.mkdir(exist_ok=True)
        for extension in ('pdf', 'tex'):
            shutil.copy2(destination / ('表格.' + extension), writer_folder / ('表格.' + extension))
        paper = ROOT / 'paper/supplement'
        for extension in ('pdf', 'png', 'tex'):
            shutil.copy2(destination / ('表格.' + extension), paper / (stem + '_Preview.' + extension))
        shutil.copy2(destination / '表格片段.tex', paper / (stem + '_Table.tex'))
        print(json.dumps({'folder': str(writer_folder), 'rows': len(cells)}, ensure_ascii=True))
    (out / 'protocol.json').write_text(json.dumps({
        'source': 'results/summaries/workflow_catalog_104/summary.json',
        'ablation_arms': ['full', 'no_projection', 'no_lifting', 'no_geometry'],
        'geometry_comparison_arms': ['full', 'linear'],
        'new_api_calls': 0}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
