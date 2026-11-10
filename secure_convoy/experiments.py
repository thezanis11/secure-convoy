"""Fixed, resumable experiments with paired seeds and explicit uncertainty."""
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import platform
import time

import numpy as np
import pandas as pd

from .simulation import Config, SCENARIOS, CONTROLLERS, ABLATIONS, simulate

ROOT = Path(__file__).resolve().parents[1]


def wilson(successes, total):
    if total == 0:
        return [None, None]
    z = 1.959963984540054
    p = successes/total
    center = (p + z*z/(2*total))/(1+z*z/total)
    radius = z*np.sqrt(p*(1-p)/total + z*z/(4*total*total))/(1+z*z/total)
    return [max(0, float(center-radius)), min(1, float(center+radius))]


def paired_difference(frame, baseline='trusting_cacc', candidate='defended_cacc'):
    a = frame.loc[frame.controller == baseline].set_index('seed').collision.astype(float)
    b = frame.loc[frame.controller == candidate].set_index('seed').collision.astype(float)
    shared = a.index.intersection(b.index)
    diff = a.loc[shared].to_numpy() - b.loc[shared].to_numpy()
    rng = np.random.default_rng(923)
    boots = np.mean(rng.choice(diff, size=(2000, len(diff)), replace=True), axis=1)
    return dict(paired_seeds=len(diff), collision_rate_reduction=float(diff.mean()),
                bootstrap_95=[float(x) for x in np.quantile(boots, [0.025, 0.975])])


def run_grid(tasks, name, config, trace_keys=()):
    signature = hashlib.sha256((Path(__file__).with_name('simulation.py').read_text(encoding='utf-8') +
                                json.dumps(asdict(config), sort_keys=True) + json.dumps(tasks)).encode()).hexdigest()
    cache = ROOT / 'data/runs'
    cache.mkdir(parents=True, exist_ok=True)
    checkpoint = cache / f'{name}-{signature[:12]}.jsonl'
    completed = {}
    if checkpoint.exists():
        for line in checkpoint.read_text(encoding='utf-8').splitlines():
            result = json.loads(line)
            completed[(result['scenario'], result['controller'], result['seed'], result['dt'])] = result
    results = []
    started = time.monotonic()
    traces = ROOT / 'reports/traces'
    traces.mkdir(parents=True, exist_ok=True)
    with checkpoint.open('a', encoding='utf-8') as stream:
        for index, (scenario, controller, seed, dt) in enumerate(tasks):
            key = (scenario, controller, seed, dt)
            if key in completed:
                result = completed[key]
            else:
                keep_trace = (scenario, controller, seed) in trace_keys
                result, frames = simulate(seed, scenario, controller, replace(config, dt=dt), trace=keep_trace)
                result['dt'] = dt
                stream.write(json.dumps(result, allow_nan=False) + '\n')
                stream.flush()
                if frames:
                    pd.DataFrame(frames).to_csv(traces / f'{scenario}--{controller}--{seed}.csv', index=False)
            results.append(result)
            if (index+1) % 32 == 0 or index+1 == len(tasks):
                print(f'{name}: {index+1}/{len(tasks)} runs, {time.monotonic()-started:.0f}s', flush=True)
    return pd.DataFrame(results), signature


def summarize(frame):
    records = []
    for (scenario, controller), group in frame.groupby(['scenario', 'controller'], sort=True):
        hits = int(group.collision.sum())
        lo, hi = wilson(hits, len(group))
        records.append(dict(scenario=scenario, controller=controller, trials=len(group), collisions=hits,
                            collision_rate=hits/len(group), collision_ci_low=lo, collision_ci_high=hi,
                            median_min_gap_m=float(group.min_gap_m.median()),
                            gap_p05=float(group.min_gap_m.quantile(.05)),
                            median_jerk_rms=float(group.jerk_rms_mps3.median()),
                            attack_packets_accepted=int(group.attack_packets_accepted.sum()),
                            benign_rejected=int(group.benign_packets_rejected.sum()),
                            packets_received=int(group.packets_received.sum())))
    return pd.DataFrame(records)


def benchmark(seeds=32):
    if seeds < 2:
        raise ValueError('At least two seeds are needed')
    cfg = Config()
    out = ROOT / 'reports'
    out.mkdir(exist_ok=True)
    # Parameters are fixed before test seeds. Seeds 0..9 are development only.
    test_seeds = list(range(1000, 1000+seeds))
    tasks = [(s, c, seed, cfg.dt) for s in SCENARIOS for c in CONTROLLERS for seed in test_seeds]
    traces = [(s, c, test_seeds[0]) for s in ('emergency_brake', 'external_spoof', 'insider_spoof') for c in CONTROLLERS]
    protocol = dict(config=asdict(cfg), seeds=test_seeds, scenarios=list(SCENARIOS), controllers=list(CONTROLLERS),
                    selection='fixed factorial grid; no favorable-seed selection; source hash identifies cached recipe',
                    collision_definition='front bumper gap <= 0; simulation stops at first contact',
                    security='public demo HMAC-SHA256 keys; replay/freshness checks; radar consistency; headway supervisor',
                    python=platform.python_version(), numpy=np.__version__)
    (out / 'protocol.json').write_text(json.dumps(protocol, indent=2), encoding='utf-8')
    primary, signature = run_grid(tasks, 'primary', cfg, traces)
    primary.to_csv(out / 'trials.csv', index=False)
    summary = summarize(primary)
    summary.to_csv(out / 'summary.csv', index=False)
    ablation_scenarios = ('external_spoof', 'insider_spoof', 'replay', 'subtle_insider')
    ablation_tasks = [(s, c, seed, cfg.dt) for s in ablation_scenarios for c in ABLATIONS for seed in test_seeds[:8]]
    ablation, ablation_hash = run_grid(ablation_tasks, 'ablations', cfg)
    ablation.to_csv(out / 'ablation_trials.csv', index=False)
    summarize(ablation).to_csv(out / 'ablation_summary.csv', index=False)
    convergence_tasks = [(s, c, seed, dt) for s in ('emergency_brake', 'insider_spoof')
                         for c in ('trusting_cacc', 'defended_cacc') for seed in test_seeds[:3] for dt in (.1, .05, .025)]
    convergence, convergence_hash = run_grid(convergence_tasks, 'time-step', cfg)
    convergence.to_csv(out / 'time_step_study.csv', index=False)
    differences = {s: paired_difference(primary.loc[primary.scenario == s]) for s in SCENARIOS}
    manifest = dict(protocol=protocol, primary_runs=len(primary), ablation_runs=len(ablation),
                    time_step_runs=len(convergence), simulation_source_sha256=hashlib.sha256(Path(__file__).with_name('simulation.py').read_bytes()).hexdigest(),
                    recipe_sha256=signature, ablation_recipe_sha256=ablation_hash,
                    convergence_recipe_sha256=convergence_hash, paired_comparisons=differences,
                    limitations=['longitudinal single-lane model', 'no tire/road friction model or lateral dynamics',
                                 'public keys demonstrate protocol checks, not deployment security',
                                 'insider holds a signing key; authentication alone cannot establish state truth',
                                 'supervisor uses radar and conservative bounds; no formal guarantee under noisy actuator lag',
                                 'collision-truncated comfort metrics have unequal horizons',
                                 'acceleration-energy gain is a finite-horizon proxy, not proof of string stability'])
    (out / 'experiment.json').write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding='utf-8')
    from .report import build_report
    build_report(primary, summary, manifest, out)
    print('Scientific benchmark complete.', flush=True)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--seeds', type=int, default=32)
    benchmark(parser.parse_args().seeds)
