#!/usr/bin/env python3
import argparse
import csv
import hashlib
import json
import random
from pathlib import Path

PROFILES = ('100-0', '90-10', '70-30', '50-50')
VIRTUAL_USERS = (25, 50, 100, 250, 500)
K6_IMAGE = 'grafana/k6:1.6.0@sha256:be2a9ceb1b6ffc573277af4157135882a6d6433968b41e858ab02c5fd5847532'


def build_plan(manifest_path, seed):
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get('schema_version') != 1 or manifest.get('active_company_count') != 25:
        raise ValueError('Manifesto incompatível.')
    pairs = [(profile, users, repetition) for profile in PROFILES
             for users in VIRTUAL_USERS for repetition in range(1, 6)]
    generator = random.Random(seed)
    generator.shuffle(pairs)
    runs = []
    for profile, users, repetition in pairs:
        pair_id = f'{profile}-vu{users:03d}-r{repetition}'
        pair_seed = hashlib.sha256(f'{seed}|{pair_id}'.encode()).hexdigest()[:16]
        modes = ['off', 'on']
        generator.shuffle(modes)
        for mode in modes:
            runs.append({
                'sequence': len(runs) + 1,
                'run_id': f'{pair_id}-{mode}',
                'pair_id': pair_id,
                'profile': profile,
                'virtual_users': users,
                'repetition': repetition,
                'cache_mode': mode,
                'seed': pair_seed,
            })
    return {
        'schema_version': 1,
        'plan_seed': seed,
        'manifest_path': str(manifest_path.resolve()),
        'manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
        'k6_image': K6_IMAGE,
        'active_companies': 25,
        'warmup_seconds': 120,
        'measurement_seconds': 300,
        'runs': runs,
    }


def main():
    parser = argparse.ArgumentParser(description='Prepara a matriz pareada de 200 execuções sem executar carga.')
    parser.add_argument('--manifesto', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=20261017)
    parser.add_argument('--saida', type=Path, required=True)
    arguments = parser.parse_args()
    plan = build_plan(arguments.manifesto, arguments.seed)
    arguments.saida.mkdir(parents=True, exist_ok=False)
    (arguments.saida / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n', encoding='utf-8')
    with (arguments.saida / 'plan.csv').open('w', newline='', encoding='utf-8') as output:
        writer = csv.DictWriter(output, fieldnames=list(plan['runs'][0]))
        writer.writeheader()
        writer.writerows(plan['runs'])
    print(f'Plano gerado: {arguments.saida}; 200 execuções; duração nominal mínima de 23h20.')


if __name__ == '__main__':
    main()
