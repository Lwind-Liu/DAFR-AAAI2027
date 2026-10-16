"""Update only writer-facing PDF/TeX captions from frozen results."""
import json
import shutil

from archive_chinese_tables import ROOT, DEST, small_table


def main():
    out = ROOT / 'results/summaries/writer_captions_final'
    metrics = ('CU', 'UA', 'ASR')
    headers = ['Configuration', 'CU (%) ↑', 'UA (%) ↑', 'ASR (%) ↓', 'Total Tool Calls']
    common = ('使用 DeepSeek-v4-flash-0731，在相同的 104 个配对任务上评估；每种配置执行 104 次干净任务与 104 次攻击任务，工具接口及执行预算一致。\n'
              'CU 为干净任务完成率，UA 为攻击条件下原任务完成率，ASR 为攻击者目标达成率，均以百分比表示。CU、UA 越高越好，ASR 越低越好。三项独立按环境状态判定。\n'
              'Total Tool Calls 为全部 208 次执行的工具调用总数，包含被防御层拒绝的有效请求。')
    main_rows = json.loads((ROOT / 'results/summaries/catalog_fixed104_adapter_v11_104/summary.json').read_text())['rows']
    labels = {'no_defense': 'No Defense', 'piguard': 'PIGuard', 'protectai': 'ProtectAI',
              'progent': 'Progent', 'drift': 'DRIFT', 'full': 'DAFR'}
    cells = [[labels[r['method']], *[f'{r[k]:.1f}' for k in metrics], str(r['total_tool_calls'])] for r in main_rows]
    specs = [('合成主表', '合成数据主表', ['Method', *headers[1:]], cells, common)]
    source = {r['arm']: r for r in json.loads((ROOT / 'results/summaries/workflow_catalog_104/summary.json').read_text())['rows']}
    arms = [('full', 'DAFR'), ('no_projection', 'w/o Evidence Projection'),
            ('no_lifting', 'w/o Action--Evidence Lifting'), ('no_geometry', 'w/o Feasibility Constraints')]
    cells = [[label, *[f'{source[arm][k]:.1f}' for k in metrics], str(source[arm]['total_tool_calls'])] for arm, label in arms]
    caption = common + '\n' + (
        '三个模块分别消融：证据投影——取消来源可信度区分；动作—证据提升——取消证据与具体动作参数、请求、版本及执行权限的严格绑定；可行性约束——关闭半空间与联合风险曲面的执行准入检查。\n'
        '每次只移除对应模块，其余设置保持一致，并保留工具参数校验与反馈机制。')
    specs.append(('合成消融', '合成数据模块消融', headers, cells, caption))
    cells = [[label, *[f'{source[arm][k]:.1f}' for k in metrics], str(source[arm]['total_tool_calls'])]
             for arm, label in [('full', 'DAFR'), ('linear', 'Linear Rules')]]
    caption = common + '\n' + (
        '线性规则在相同动作—证据坐标上替代完整几何判别部分（半空间约束与联合风险曲面）；证据投影、动作—证据绑定及反馈机制保持一致。\n'
        'DAFR 的 CU、UA 分别提高 10.6、22.1 个百分点，ASR 降低 22.1 个百分点。')
    specs.append(('几何对比', '几何建模与线性规则对比', headers, cells, caption))
    costs = json.loads((ROOT / 'results/summaries/catalog_resource_cost_104/protocol.json').read_text())['rows']
    cost_headers = ['Method', 'Input Tokens ↓', 'Output Tokens ↓', 'Total Tokens ↓', 'Tool Calls ↓']
    cells = [[r['Method'], *[f'{r[k]:,.2f}' for k in ('Input Tokens', 'Output Tokens', 'Total Tokens', 'Tool Calls')]] for r in costs]
    caption = ('在与合成主表相同的 104 个配对任务上统计开销，每种方法共执行 208 次。表中数值均为单次执行的平均值，保留两位小数。\n'
               'Input Tokens、Output Tokens 包含 agent 规划及防御方法产生的全部大模型调用；Total Tokens 为输入与输出之和，按未舍入数值计算。\n'
               'Tool Calls 为平均工具调用次数，包含被防御层拒绝的有效请求；主表与消融表中的 Total Tool Calls 则为总数。')
    specs.append(('开销表', '合成数据资源开销', cost_headers, cells, caption))
    for folder, title, columns, cells, caption in specs:
        if folder == '几何对比':
            from render_geometry_booktabs import main as render_geometry
            render_geometry()
            continue
        target = out / folder
        small_table(target, columns, cells, caption, title)
        for ext in ('pdf', 'tex'):
            shutil.copy2(target / f'表格.{ext}', DEST / folder / f'表格.{ext}')
        print(folder)


if __name__ == '__main__':
    main()
