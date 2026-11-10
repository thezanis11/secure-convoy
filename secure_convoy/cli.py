import argparse
from pathlib import Path

from .simulation import SCENARIOS, CONTROLLERS, ABLATIONS, simulate


def main():
    parser = argparse.ArgumentParser(description='Secure Convoy: control and V2X security research')
    sub = parser.add_subparsers(dest='command', required=True)
    bench = sub.add_parser('benchmark')
    bench.add_argument('--seeds', type=int, default=32)
    run = sub.add_parser('simulate')
    run.add_argument('--scenario', choices=SCENARIOS, default='insider_spoof')
    run.add_argument('--controller', choices=CONTROLLERS+ABLATIONS, default='defended_cacc')
    run.add_argument('--seed', type=int, default=1000)
    run.add_argument('--out', type=Path, default=Path('reports/custom_trace.csv'))
    sumo = sub.add_parser('sumo-validate')
    sumo.add_argument('--seeds', type=int, default=2)
    args = parser.parse_args()
    if args.command == 'benchmark':
        from .experiments import benchmark
        benchmark(args.seeds)
    elif args.command == 'sumo-validate':
        from .sumo_validation import validate
        validate(tuple(range(1000, 1000+args.seeds)))
    else:
        import json
        import pandas as pd
        result, trace = simulate(args.seed, args.scenario, args.controller, trace=True)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(trace).to_csv(args.out, index=False)
        print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
