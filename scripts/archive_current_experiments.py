"""Snapshot the approved main table and complete fixed-104 experiments."""
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import zipfile

import export_catalog_baseline_comparison as comparison

ROOT = Path(__file__).resolve().parents[1]
MAIN = Path(r'C:\Users\Administrator\AppData\Roaming\Kim\localData\userData\fc37d4df0fa447e08d1626d6e816ccf6\Kim file\2026-10\AgentDojo_Main_Table.tex')


def main():
    stamp = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M%S')
    target = ROOT / 'archives' / ('DAFR_Tables_Data_Records_' + stamp)
    assert not target.exists()
    target.mkdir(parents=True)
    origins = {}

    def copy(source, destination):
        source = Path(source)
        destination = target / destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        origins[str(destination.relative_to(target)).replace('\\', '/')] = str(source)

    def tree(source, destination):
        source = ROOT / source
        for file in sorted(source.rglob('*')):
            if file.is_file() and '__pycache__' not in file.parts:
                copy(file, Path(destination) / file.relative_to(source))

    folder = ROOT / 'results/summaries/catalog_fixed104_adapter_v11_104'
    _, results, protocol = comparison.read_complete(folder)
    ablation = json.loads((ROOT / 'results/summaries/workflow_catalog_104/summary.json').read_text())
    audit = json.loads((ROOT / 'results/summaries/workflow_catalog_104/audit.json').read_text())
    assert ablation['complete'] and audit == {'replayed_episodes': 1040, 'errors': 0, 'complete': True}
    traces = []
    for name in ('workflow_catalog_v2', 'workflow_catalog_104'):
        for file in sorted((ROOT / 'results/summaries' / name).glob('CAT-*.jsonl')):
            traces.extend(json.loads(line) for line in file.read_text().splitlines())
    assert len(traces) == len({(r['id'], r['arm']) for r in traces}) == 1040
    for row in ablation['rows']:
        actual = comparison.metrics([r for r in traces if r['arm'] == row['arm']])
        assert all(abs(actual[k] - row[k]) < 1e-9 for k in actual)
    full = next(r for r in results if r['method'] == 'full')
    assert all(abs(full[k] - ablation['rows'][0][k]) < 1e-9 for k in ('CU', 'UA', 'ASR', 'total_tool_calls'))

    copy(MAIN, '01_AgentDojo_Main_Table/AgentDojo_Main_Table.tex')
    text = MAIN.read_text(encoding='utf-8-sig')
    models = ['DeepSeek V4 Flash', 'GPT-5.4-mini', 'Claude Haiku 4.5']
    methods = ['No Defense', 'PIGuard', 'ProtectAI', 'Progent', 'DRIFT', 'DAFR']
    rows = []
    for line in text.splitlines():
        if '&' not in line:
            continue
        parts = line.split('&')
        if len(parts) != 17 or not all(re.search(r'\d+\.\d+', item) for item in parts[2:]):
            continue
        values = [float(re.search(r'\d+\.\d+', item).group()) for item in parts[2:]]
        index = len(rows) // 5
        assert methods[index % 6] in parts[1]
        for i, domain in enumerate(['Workspace', 'Slack', 'Travel', 'Banking', 'Overall']):
            rows.append({'Model': models[index // 6], 'Method': methods[index % 6],
                         'Domain': domain, 'CU (%)': values[3*i],
                         'UA (%)': values[3*i+1], 'ASR (%)': values[3*i+2]})
    assert len(rows) == 90
    comparison.write_csv(target / '01_AgentDojo_Main_Table/main_table.csv', rows)

    for name in ('agentdojo_deepseek_main_raw.zip', 'agentdojo_gpt54mini_raw.zip',
                 'agentdojo_claudehaiku45_raw.zip', 'agentdojo_deepseek_ablation_raw.zip',
                 'asb_and_margin_raw.zip'):
        copy(ROOT / 'release_assets' / name, '04_AgentDojo_Records/raw/' + name)
    for name in ('agentdojo_v122_clafr_final_full_4suite_v1',
                 'agentdojo_v122_clafr_full_ablation_4suite_20260728',
                 'agentdojo_v122_gpt54mini_multillm_frozen_v1',
                 'agentdojo_v122_claudehaiku45_multillm_frozen_v1'):
        tree('results/summaries/' + name, '04_AgentDojo_Records/summaries/' + name)
    copy(ROOT / 'data/manifests/agentdojo_v122_clafr_multillm_four_suite_71_585.json',
         '04_AgentDojo_Records/manifests/agentdojo_v122_clafr_multillm_four_suite_71_585.json')
    copy(ROOT / 'paper/main/DAFR_AAAI2027_Main_Current.tex', '05_Method_Snapshot/paper/DAFR_AAAI2027_Main_Current.tex')
    copy(ROOT / 'paper/method_proposals/DAFR_Joint_Risk_Replacement_Draft.tex',
         '05_Method_Snapshot/paper/DAFR_Joint_Risk_Replacement_Draft.tex')

    tree('data/workflow_catalog_104', '02_Synthetic_104/data/workflow_catalog_104')
    tree('data/workflow_catalog_v2', '02_Synthetic_104/data/workflow_catalog_v2')
    for name in ('summary.json', 'protocol.json', 'audit.json', 'rows.jsonl', 'usage.json',
                 'main_table.csv', 'per_domain.csv', 'final_comparison.json', 'compatibility.json', 'attempts.log'):
        copy(folder / name, '02_Synthetic_104/comparison_records/' + name)
    tree('results/summaries/workflow_catalog_104', '03_Synthetic_Ablation/records/workflow_catalog_104')
    tree('results/summaries/workflow_catalog_v2', '03_Synthetic_Ablation/records/workflow_catalog_v2')
    for suffix in ('Table.tex', 'Preview.tex', 'Preview.pdf', 'Preview.png'):
        name = 'DAFR_Custom_Dataset_Ablation_' + suffix
        copy(ROOT / 'paper/supplement' / name, '03_Synthetic_Ablation/tables/' + name)

    tables = target / '02_Synthetic_104/tables'
    tables.mkdir()
    comparison.render_preview(results, tables)
    latex = [r'\begin{table}[ht]', r'\centering\small', r'\begin{tabular}{lrrrr}', r'\toprule',
             r'Method & CU (\%) $\uparrow$ & UA (\%) $\uparrow$ & ASR (\%) $\downarrow$ & Total Tool Calls \\', r'\midrule']
    for row in results:
        cells = []
        for key in ('CU', 'UA', 'ASR'):
            value = f"{row[key]:.1f}"
            best = (min if key == 'ASR' else max)(r[key] for r in results)
            cells.append(r'\textbf{' + value + '}' if row[key] == best else value)
        if row['method'] == 'full':
            latex.append(r'\rowcolor{black!12}')
        latex.append(row['label'] + ' & ' + ' & '.join(cells) + ' & ' + str(row['total_tool_calls']) + r' \\')
    latex += [r'\bottomrule', r'\end{tabular}', r'\caption{' + comparison.CAPTION + '}',
              r'\label{tab:custom-dataset-comparison}', r'\end{table}']
    (tables / 'DAFR_Custom_Dataset_Comparison_Table.tex').write_text('\n'.join(latex) + '\n', encoding='utf-8')

    for directory in ('src/workflow_benchmark', 'src/relational_dafr'):
        for file in (ROOT / directory).glob('*.py'):
            copy(file, '05_Method_Snapshot/' + str(file.relative_to(ROOT)))
    for name in ('catalog_baseline_adapter_v11.py', 'flash_catalog_client.py',
                 'run_catalog_fixed104_adapter_v11_full.py', 'resume_catalog_fixed104.py',
                 'run_workflow_catalog_v2.py', 'extend_catalog_104.py', 'resume_catalog_v2.py',
                 'run_mixed_workflow_pilot.py', 'run_queued_workflow_case.py',
                 'run_workflow_benchmark.py', 'run_targeted_payment_case.py', 'run_single_dojo_case.py',
                 'run_flash_other_methods.py', 'export_catalog_baseline_comparison.py',
                 'render_catalog_v2_results.py', 'archive_current_experiments.py'):
        copy(ROOT / 'scripts' / name, '05_Method_Snapshot/scripts/' + name)

    readme = '''# DAFR 当前实验归档

归档时间：{stamp}（Asia/Shanghai）。

## 文件索引

- `01_AgentDojo_Main_Table/`：用户确认的最新 AgentDojo 主表原始 LaTeX，以及逐项提取的 90 行 CSV（三模型 × 六方法 × 五组指标）。主表以这份原稿为准。
- `02_Synthetic_104/`：固定 104 个任务的干净/攻击配对数据、六方法完整结果、1248 次有效执行轨迹、协议、审计、逐领域结果及最新对比表 LaTeX/PDF/PNG。
- `03_Synthetic_Ablation/`：五配置消融表 LaTeX/PDF/PNG、1040 次执行记录及对应协议和审计。前 100 个任务的轨迹在 workflow_catalog_v2，新增四个任务在 workflow_catalog_104。
- `04_AgentDojo_Records/`：仓库现有的三模型原始结果包、原论文消融包、ASB/间隔记录和历史汇总、运行清单。历史汇总保留原样，不覆盖最新主表；这里未重新核算历史结果包与最新表的逐项一致性。
- `05_Method_Snapshot/`：本次合成实验使用的算法、环境和运行脚本，以及当前正文与联合风险替换草稿的版本快照。
- `MANIFEST.csv`：全部归档文件的来源、字节大小及 SHA-256。

## 固定实验版本

合成数据 SHA-256：`{dataset_hash}`。六方法使用 deepseek-v4-flash-0731，每方法 104 条干净任务和 104 条攻击任务。对比审计 1248/1248，消融审计 1040/1040，均为零回放错误。完整 DAFR 在对比与消融中的分数和工具调用次数一致。

CU/UA 分别表示干净/攻击任务完成率；ASR 为攻击目标达成率；总工具调用次数包含被拒绝的提交。合成实验按任务计数汇总；AgentDojo 最新主表 Overall 按四领域等权平均。API 失败尝试另存 attempts.log，未计入方法分数。usage.json 中开销是客户端估算，非账单金额。

合成实验使用路径依赖联合风险实现；原 AgentDojo 主表对应原风险锥实现。两者的代码、论文描述与结果分别保存，版本关系可追溯。

对比表 PDF/PNG 由实测结果通过 Matplotlib 渲染；同目录同时提供 LaTeX 表格源码。
'''.format(stamp=stamp, dataset_hash=protocol['data_sha256'])
    (target / 'README.md').write_text(readme, encoding='utf-8')
    # Check for credential-shaped strings without emitting any matched value.
    sensitive = re.compile(rb'sk-ws-[A-Za-z0-9._-]{25,}|sk-proj-[A-Za-z0-9_-]{25,}|sk-[a-f0-9]{32}\b')
    for file in target.rglob('*'):
        if not file.is_file():
            continue
        if file.suffix == '.zip':
            with zipfile.ZipFile(file) as archive:
                assert archive.testzip() is None
                for item in archive.infolist():
                    if not item.is_dir():
                        assert not sensitive.search(archive.read(item)), 'Credential-shaped content in raw package'
        elif file.suffix in ('.py', '.json', '.jsonl', '.log', '.md', '.tex', '.csv'):
            assert not sensitive.search(file.read_bytes()), 'Credential-shaped content in snapshot'
    manifest = []
    for file in sorted(target.rglob('*')):
        if file.is_file():
            relative = file.relative_to(target).as_posix()
            manifest.append({'file': relative, 'source': origins.get(relative, 'generated from verified archived results'),
                             'bytes': file.stat().st_size, 'sha256': hashlib.sha256(file.read_bytes()).hexdigest()})
    comparison.write_csv(target / 'MANIFEST.csv', manifest)
    zipped = target.with_suffix('.zip')
    with zipfile.ZipFile(zipped, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for file in sorted(target.rglob('*')):
            if file.is_file():
                archive.write(file, target.name + '/' + file.relative_to(target).as_posix())
    with zipfile.ZipFile(zipped) as archive:
        assert archive.testzip() is None
    receipt = {'archive': str(target), 'zip': str(zipped), 'files': len(manifest) + 1,
               'zip_bytes': zipped.stat().st_size, 'zip_sha256': hashlib.sha256(zipped.read_bytes()).hexdigest(),
               'comparison_episodes': 1248, 'ablation_episodes': 1040, 'credential_scan': 'passed'}
    (zipped.parent / (target.name + '.receipt.json')).write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
