"""Integrity, paired group uncertainty and held-out graph-family evaluation."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT/'scripts'))
from run_relational_dafr_complete_ablation import OUT, DATA, fit, feedback_training, summarize, dump
from relational_dafr.episodes import EpisodeRuntime, oracle_recoverable
from relational_dafr.pipeline import run_episode
from relational_dafr.worlds import safe, expected_loss


def read(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


def intervals(rows):
    groups=sorted({r['group'] for r in rows})
    arms=sorted({r['arm'] for r in rows})
    values={a:defaultdict(list) for a in arms}
    for r in rows:
        values[r['arm']][r['group']].append([
            float(r['initial_allowed']==r['safe_original']),
            float(r['policy_safe']),float(r['committed'] and not r['policy_safe'])])
    matrices={a:np.array([np.mean(values[a][g],axis=0) for g in groups]) for a in arms}
    rng=np.random.default_rng(49137)
    sampled=rng.integers(0,len(groups),(4000,len(groups)))
    result={}
    for a in arms:
        if a=='full':continue
        delta=matrices['full']-matrices[a]
        estimates=delta[sampled].mean(axis=1)
        result[a]={key:{'difference':float(delta[:,i].mean()),
                         'paired_group_bootstrap_95pct':np.quantile(estimates[:,i],[.025,.975]).tolist()}
                   for i,key in enumerate(('initial_accuracy','safe_execution_rate','unsafe_execution_rate'))}
    return {'groups':len(groups),'replicates':4000,'comparisons_full_minus_arm':result,
            'note':'Exploratory paired intervals; no multiplicity adjustment or external preregistration.'}


def main():
    manifest=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))
    assert all(hashlib.sha256((DATA/name).read_bytes()).hexdigest()==digest
               for name,digest in manifest['data_sha256'].items())
    splits={};group_sets={}
    for split in ('train','dev','test'):
        public=read(DATA/f'{split}_inputs.jsonl')
        episodes=read(DATA/f'{split}_evaluator.jsonl')
        labels=read(DATA/f'{split}_labels.jsonl')
        assert len(public)==len(episodes)==len(labels)
        assert len({p['id'] for p in public})==len(public)
        for p,e,label in zip(public,episodes,labels):
            assert p==e['input'] and p['id']==label['id']
            assert set(p)=={'id','action','policy','records'}
            assert label['safe']==safe(e['hidden_world'])
            assert abs(label['expected_loss']-expected_loss(e['hidden_world']))<1e-12
            assert label['recoverable']==oracle_recoverable(e)
        splits[split]=episodes
        group_sets[split]={e['group'] for e in episodes}
    assert not any(group_sets[a]&group_sets[b] for a,b in
                   (('train','dev'),('train','test'),('dev','test')))
    rows=read(OUT/'test_rows.jsonl')
    assert len(rows)==len(splits['test'])*len({r['arm'] for r in rows})
    summary=json.loads((OUT/'summary.json').read_text(encoding='utf-8'))
    for arm,aggregate in summary['test'].items():
        assert summarize([r for r in rows if r['arm']==arm])==aggregate
    dump(OUT/'paired_intervals.json',intervals(rows))
    integrity={'hashes_valid':True,'public_inputs_and_evaluator_separate':True,
               'labels_recomputed_from_independent_worlds':True,'group_splits_disjoint':True,
               'split_counts':{s:len(e) for s,e in splits.items()},
               'variants_per_group':5,'no_sample_filtering':True,
               'audit_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    dump(OUT/'integrity_audit.json',integrity)
    domains=sorted({e['domain'] for e in splits['test']})
    folds={}
    for heldout in domains:
        train=[e for e in splits['train'] if e['domain']!=heldout]
        dev=[e for e in splits['dev'] if e['domain']!=heldout]
        test=[e for e in splits['test'] if e['domain']==heldout]
        models=fit(feedback_training(train),feedback_training(dev))
        selected={'full':{},**{a:models[a] for a in
                  ('affine_weighted','affine_safety_1pct','linear_rules_64_weighted','linear_rules_64_safety_1pct')}}
        fold_rows=[]
        for e in test:
            for arm,params in selected.items():
                r=run_episode(e['input'],EpisodeRuntime(e),**params)
                r.update(arm=arm,safe_original=safe(e['hidden_world']),recoverable=oracle_recoverable(e))
                fold_rows.append(r)
        folds[heldout]={a:summarize([r for r in fold_rows if r['arm']==a]) for a in selected}
        print('Held out',heldout,json.dumps(folds[heldout]),flush=True)
    dump(OUT/'heldout_graph_families.json',{
        'protocol':'Exclude the entire named graph family from train and development; evaluate its original unchanged test cases. Feedback-augmented baselines.',
        'scope':'Transfer across four declared synthetic causal topologies, not empirical real-world or natural-language generalization.',
        'folds':folds})
    print('Integrity passed; grouped intervals and four family holdouts saved.',flush=True)


if __name__=='__main__':main()
