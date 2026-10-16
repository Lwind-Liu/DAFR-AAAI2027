"""Illustrative 2-D slice of the frozen high-dimensional surface and affine rule."""
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from relational_dafr.controller import features


def main():
    output = ROOT / 'results/summaries/flash_business_geometry_test_v1'
    p = json.loads((output / 'frozen_protocol.json').read_text())
    weights = np.array(p['weights'])
    scene = {'events': {f'e{i}': {'probability': .2} for i in range(3)},
             'paths': [{'field': 'recipient', 'events': ['e0', 'e1']},
                       {'field': 'body', 'events': ['e0', 'e2']}],
             'grants': [], 'revision': 1, 'severity': 1., 'budget': .2,
             'action': {'effect': 'send_email', 'arguments': {'recipient': 'owner', 'body': 'status'}}}
    axis = np.linspace(0, 1, 251)
    x, y = np.meshgrid(axis, axis)
    oracle = x * (y + .2 - y * .2)
    affine = np.empty_like(x)
    for i in range(len(axis)):
        for j in range(len(axis)):
            scene['events']['e0']['probability'] = float(x[i, j])
            scene['events']['e1']['probability'] = float(y[i, j])
            affine[i, j] = features(scene) @ weights + p['bias'] - p['threshold']
    plt.rcParams.update({'font.size': 10, 'pdf.fonttype': 42, 'ps.fonttype': 42})
    fig, ax = plt.subplots(figsize=(5.3, 4.2), layout='constrained')
    ax.contourf(x, y, oracle, levels=[0, .2, 1.01], colors=['#dceee7', '#f6dddd'])
    ax.contour(x, y, oracle, levels=[.2], colors=['#176b50'], linewidths=2)
    if affine.min() <= 0 <= affine.max():
        ax.contour(x, y, affine, levels=[0], colors=['#a44332'], linewidths=2, linestyles='--')
    ax.set(xlabel='Source event probability', ylabel='Target propagation probability',
           xlim=(0, 1), ylim=(0, 1), title='Declared joint-risk model: conditional slice')
    ax.legend(handles=[Line2D([0], [0], color='#176b50', lw=2, label='Joint-risk boundary'),
                       Line2D([0], [0], color='#a44332', lw=2, ls='--', label='Fitted affine boundary')],
              loc='upper right')
    ax.text(.03, .04, 'Other propagation = 0.2; budget = 0.2; severity = 1\nShared-source graph; no verified fields',
            transform=ax.transAxes, fontsize=8, bbox={'facecolor': 'white', 'alpha': .85, 'edgecolor': 'none'})
    target = ROOT / 'paper/figures'
    target.mkdir(exist_ok=True)
    fig.savefig(target / 'flash_joint_surface_slice.pdf')
    fig.savefig(target / 'flash_joint_surface_slice.png', dpi=220)
    plt.close(fig)
    print('Saved illustrative slice; it is not a test performance plot.')


if __name__ == '__main__':
    main()
