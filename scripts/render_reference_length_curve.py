"""Plot matched archived AgentDojo attacks by official reference-tool-call count."""
import json
import hashlib
from pathlib import Path
import shutil
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from render_geometry_booktabs import wrap_measured

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results/summaries/agentdojo_reference_length'
DEST=Path('C:/Users/Administrator/Desktop/表/轨迹长度分析')


def main():
    data=json.loads((OUT/'inspection.json').read_text(encoding='utf-8'))
    bins=['1','2','3','4+']
    specs=[('clafr_no_dynamic_geometry','w/o Geometric Constraints','#287FA1','o'),
           ('clafr','DAFR','#EF8A32','s')]
    plt.rcParams.update({'font.family':'Times New Roman','font.size':12,'pdf.fonttype':42})
    fig,ax=plt.subplots(figsize=(6.5,4.6))
    fig.subplots_adjust(left=.14,right=.95,bottom=.20,top=.94)
    for arm,label,color,marker in specs:
        rows=[next(r for r in data['metrics'] if r['bin']==b and r['arm']==arm) for b in bins]
        ax.plot(range(4),[r['ASR'] for r in rows],color=color,marker=marker,linewidth=1.8,markersize=6,label=label)
        for x,r in enumerate(rows):
            ax.annotate(f"{r['ASR']:.1f}",(x,r['ASR']),xytext=(0,8),textcoords='offset points',ha='center',color=color,fontsize=11)
    ax.set_xticks(range(4),bins)
    ax.set(xlabel='Reference trajectory length',ylabel='Attack success rate (%)',ylim=(-2,38),xlim=(-.2,3.2))
    ax.set_yticks(range(0,36,5));ax.grid(color='#dddddd',linewidth=.8)
    ax.legend(loc='upper left',fontsize=10,framealpha=.95)
    for ext in ['pdf','png']:fig.savefig(OUT/('轨迹长度与安全性.'+ext),dpi=220,bbox_inches='tight',pad_inches=.1)
    caption=('AgentDojo 中几何约束的安全收益与参考轨迹长度。采用 DeepSeek V4 Flash 的归档消融记录，'
             '按官方参考解的工具调用数分为 1、2、3、至少 4 步；每组分别包含 10、20、9、32 个用户任务，'
             '对应 111、192、64、218 次攻击执行，两个配置使用相同任务与攻击。ASR 按组内攻击执行记录求平均。'
             '去掉几何约束时，各组 ASR 为 4.5%、7.3%、31.2%、20.2%；完整 DAFR 各组均为 0%。'
             '这是一项跨任务的长度分组分析，各组领域与任务组成不同，不表示只增加步骤就会产生同等幅度的变化。')
    fp=FontProperties(fname='C:/Windows/Fonts/simsun.ttc',size=9)
    fig.text(.08,-.02,wrap_measured(fig,caption,fp,fig.bbox.width*.88),fontproperties=fp,va='top',linespacing=1.4)
    fig.savefig(OUT/'轨迹长度与安全性.pdf',bbox_inches='tight',pad_inches=.1)
    fig.savefig(OUT/'preview.png',dpi=150,bbox_inches='tight',pad_inches=.1)
    plt.close(fig)
    plots=[]
    for arm,label,color,marker in specs:
        ys=[next(r['ASR'] for r in data['metrics'] if r['bin']==b and r['arm']==arm) for b in bins]
        coords=' '.join(f'({i},{y:.8f})' for i,y in enumerate(ys,1))
        plots.append(r'\addplot+[thick,mark='+('square*' if arm=='clafr' else '*')+r'] coordinates {'+coords+'};'+r'\addlegendentry{'+label+'}')
    tex=r'''% XeLaTeX; editable vector plot.
\documentclass[UTF8]{ctexart}
\usepackage[a4paper,margin=20mm]{geometry}
\usepackage{fontspec,pgfplots,caption}
\pgfplotsset{compat=1.18}
\setmainfont{Times New Roman}
\pagestyle{empty}
\definecolor{curveblue}{HTML}{287FA1}
\definecolor{curveorange}{HTML}{EF8A32}
\begin{document}\begin{figure}[ht]\centering
\begin{tikzpicture}\begin{axis}[width=13cm,height=9cm,xmin=.8,xmax=4.2,ymin=-2,ymax=38,
xtick={1,2,3,4},xticklabels={1,2,3,4+},ytick={0,5,...,35},grid=major,grid style={gray!25},
xlabel={Reference trajectory length},ylabel={Attack success rate (\%)},legend pos=north west,
cycle list={{curveblue},{curveorange}}]
'''+ '\n'.join(plots)+r'''
\end{axis}\end{tikzpicture}
\caption{'''+caption.replace('%',r'\%')+r'''}
\end{figure}\end{document}
'''
    (OUT/'轨迹长度与安全性.tex').write_text(tex,encoding='utf-8')
    data['archive_sha256']=hashlib.sha256((ROOT/data['archive']).read_bytes()).hexdigest()
    data['api_requests']=0
    (OUT/'inspection.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    DEST.mkdir(exist_ok=True,parents=True)
    for ext in ['pdf','png','tex']:shutil.copy2(OUT/('轨迹长度与安全性.'+ext),DEST/('轨迹长度与安全性.'+ext))
    print('Matched episodes:',data['matched_episodes'],'; tasks:',len(data['task_lengths']))


if __name__=='__main__':main()
