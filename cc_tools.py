"""Offline CC trace perturbation and experiment accounting (Python standard library).

Never imports or executes an AdvNet emulator. Physical units are explicit.
Synthetic fixtures are only infrastructure checks, not experimental evidence.
"""
import argparse
import copy
import csv
import hashlib
import json
import math
import random
import statistics
from collections import defaultdict
from pathlib import Path

FIELDS = ('bandwidth_kbps', 'delay_ms', 'duration_ms')
CODECS = {'single_cc': 100, 'pair_678': 10}
SCORE = 'throughput_symmedian_v1'
CSV_FIELDS = ['run_id', 'variant_id', 'repeat_index', 'order', 'target', 'reference',
              'score_scheme', 'status', 'reference_mbps', 'target_mbps', 'wall_time_s',
              'protocol_executions', 'source_revision', 'kernel_version',
              'environment_id', 'measurement_id', 'log_path', 'error']


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


def finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number')
    return value


def integer(value, name, minimum=1):
    finite(value, name)
    if int(value) != value or value < minimum:
        raise ValueError(f'{name} must be an integer >= {minimum}')
    return int(value)


def validate_trace(trace, bounds=None):
    if trace.get('schema_version') != 1:
        raise ValueError('Unsupported trace schema')
    segments = trace.get('segments')
    if not isinstance(segments, list) or not segments:
        raise ValueError('At least one segment is required')
    integer(trace.get('queue_packets'), 'queue_packets')
    for segment in segments:
        for name in FIELDS:
            integer(segment.get(name), name, 2 if name == 'duration_ms' else 1)
            if bounds and not bounds[name][0] <= segment[name] <= bounds[name][1]:
                raise ValueError(f'{name} outside bounds')
    if bounds and not bounds['queue_packets'][0] <= trace['queue_packets'] <= bounds['queue_packets'][1]:
        raise ValueError('queue_packets outside bounds')
    return trace


def trace_id(trace):
    validate_trace(trace)
    physical = {'segments': trace['segments'], 'queue_packets': trace['queue_packets']}
    return hashlib.sha256(json.dumps(physical, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:20]


def encode(trace, codec):
    """Strict integer-gene export: never round away a small perturbation."""
    validate_trace(trace)
    if codec not in CODECS:
        raise ValueError('Unknown codec; single_cc and pair_678 have different queue scales')
    values = []
    for field, scale in zip(FIELDS, (500, 1, 50)):
        for segment in trace['segments']:
            if segment[field] % scale:
                raise ValueError(f'{field}={segment[field]} is off the {scale}-unit encoder grid')
            values.append(segment[field] // scale)
    if trace['queue_packets'] % CODECS[codec]:
        raise ValueError('Queue is off the selected encoder grid')
    return values + [trace['queue_packets'] // CODECS[codec]]


def decode(genes, codec):
    if codec not in CODECS or len(genes) < 4 or (len(genes) - 1) % 3:
        raise ValueError('Expected 3*n+1 integer genes and a supported codec')
    genes = [integer(v, 'gene') for v in genes]
    n = (len(genes) - 1) // 3
    return validate_trace({'schema_version': 1, 'queue_packets': genes[-1] * CODECS[codec],
                           'segments': [dict(zip(FIELDS, (genes[i]*500, genes[n+i], genes[2*n+i]*50)))
                                        for i in range(n)]})


def validate_config(config):
    if config.get('schema_version') != 1 or config.get('score_scheme') != SCORE:
        raise ValueError('Unsupported config or score scheme')
    if config.get('codec') != 'pair_678':
        raise ValueError('Week-1 experiment plans use pair_678; single_cc is decode/encode-only for audit')
    for key in ('target', 'reference', 'source_revision', 'status'):
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise ValueError(f'Missing {key}')
    if config['target'] == config['reference']:
        raise ValueError('Reference and target must differ')
    finite(config['failure_threshold'], 'failure_threshold')
    if not 0 < config['failure_threshold'] <= 1:
        raise ValueError('Failure threshold must be in (0,1]')
    for key in ('samples_per_cell', 'baseline_repeats', 'variant_repeats'):
        integer(config[key], key)
    integer(config['seed'], 'seed', 0)
    if not config['magnitudes'] or len(set(config['magnitudes'])) != len(config['magnitudes']):
        raise ValueError('Magnitudes must be nonempty and unique')
    for amount in config['magnitudes']:
        finite(amount, 'magnitude')
        if not 0 < amount < 1:
            raise ValueError('Relative magnitude must be in (0,1)')
    for field in (*FIELDS, 'queue_packets'):
        lo, hi = config['bounds'][field]
        integer(lo, 'lower bound', 2 if field == 'duration_ms' else 1)
        integer(hi, 'upper bound')
        if lo > hi:
            raise ValueError('Bounds are reversed')
    for field, grid in zip(FIELDS, (500, 1, 50)):
        step = integer(config['steps'][field], 'step')
        if step % grid:
            raise ValueError(f'{field} step must be a multiple of codec grid {grid}')


def perturb(base, family, magnitude, config, rng):
    """One coordinate per draw; reject invalid proposals rather than clipping.

    timing: shift one shared bandwidth/delay boundary, preserving total duration.
    Relative timing radius is a fraction of the shorter adjacent ORIGINAL segment.
    """
    trace = copy.deepcopy(base)
    segments = trace['segments']
    n = len(segments)
    if family == 'timing':
        if n < 2:
            return None
        index = rng.randrange(n-1)
        field = 'duration_ms'
        radius_base = min(segments[index][field], segments[index+1][field])
    else:
        field = {'bandwidth': 'bandwidth_kbps', 'delay': 'delay_ms'}[family]
        index = rng.randrange(n)
        radius_base = segments[index][field]
    step = config['steps'][field]
    count = math.floor(radius_base * magnitude / step + 1e-10)
    if count == 0:
        return None
    delta = rng.randint(1, count) * step * rng.choice((-1, 1))
    segments[index][field] += delta
    if family == 'timing':
        segments[index+1][field] -= delta
    try:
        validate_trace(trace, config['bounds'])
        encode(trace, config['codec'])
    except ValueError:
        return None
    return trace, {'coordinate_index': index, 'delta': delta,
                   'delta_unit': 'ms' if field != 'bandwidth_kbps' else 'kbps',
                   'relative_to': radius_base, 'actual_relative_change': delta/radius_base}


def build_plan(base, config):
    validate_config(config)
    validate_trace(base, config['bounds'])
    encode(base, config['codec'])
    rng = random.Random(config['seed'])
    parent = trace_id(base)
    variants = [{'variant_id': 'baseline', 'trace_id': parent, 'parent_trace_id': parent,
                 'family': 'baseline', 'magnitude': 0, 'trace': base,
                 'encoded_trace': encode(base, config['codec']), 'perturbation': None}]
    cells = []
    for family in ('bandwidth', 'delay', 'timing'):
        for magnitude in config['magnitudes']:
            seen, attempts = {parent}, 0
            generated = 0
            while generated < config['samples_per_cell'] and attempts < config['samples_per_cell'] * 200:
                attempts += 1
                result = perturb(base, family, magnitude, config, rng)
                if result is None:
                    continue
                trace, detail = result
                key = trace_id(trace)
                if key in seen:
                    continue
                seen.add(key)
                generated += 1
                variants.append({'variant_id': f'v{len(variants):04}', 'trace_id': key,
                                 'parent_trace_id': parent, 'family': family, 'magnitude': magnitude,
                                 'trace': trace, 'encoded_trace': encode(trace, config['codec']),
                                 'perturbation': detail})
            cells.append({'family': family, 'magnitude': magnitude, 'requested': config['samples_per_cell'],
                          'generated': generated, 'attempts': attempts,
                          'shortfall': config['samples_per_cell'] - generated})
    runs = []
    for variant in variants:
        repeats = config['baseline_repeats'] if variant['family'] == 'baseline' else config['variant_repeats']
        for rep in range(repeats):
            runs.append({'run_id': f"{variant['variant_id']}-r{rep:03}",
                         'variant_id': variant['variant_id'], 'repeat_index': rep,
                         'order': rng.choice(('reference_first', 'target_first')),
                         'target': config['target'], 'reference': config['reference'], 'score_scheme': SCORE})
    rng.shuffle(runs)
    return {'schema_version': 1, 'config': config, 'parent_trace_id': parent,
            'trace_description': base.get('description', ''), 'cells': cells,
            'variants': variants, 'runs': runs,
            'budget': {'planned_pair_runs': len(runs), 'minimum_protocol_executions': 2*len(runs)},
            'notes': ['Unique nonzero perturbations within each cell; rejection sampling, no clipping.',
                      'Same physical variant may appear in different magnitude cells; retain IDs.',
                      'Timing moves a joint bandwidth/delay boundary; total duration and queue stay fixed.',
                      'Seed controls perturbation and schedule only, not kernel nondeterminism.']}


def export_plan(plan, folder):
    folder = Path(folder)
    if folder.exists() and any(folder.iterdir()):
        raise ValueError('Output folder is not empty; choose a new folder to preserve collected results')
    folder.mkdir(parents=True, exist_ok=True)
    save(folder / 'plan.json', plan)
    with (folder / 'runs_template.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for run in plan['runs']:
            writer.writerow({**run, 'status': 'pending', 'source_revision': plan['config']['source_revision']})
    for variant in plan['variants']:
        path = folder / 'traces' / variant['variant_id']
        path.mkdir(parents=True)
        trace = variant['trace']
        save(path / 'trace.json', trace)
        # Mirrors the pair_678 backend's NON-PDO and delay generator formats.
        (path / 'bandwidth.nonpdo').write_text('NON-PDO\n' + ''.join(
            f"{s['bandwidth_kbps']} {s['duration_ms']}\n" for s in trace['segments']), encoding='utf-8')
        elapsed, delay_lines = 0, []
        for segment in trace['segments']:
            delay_lines.extend([f"{elapsed+1} {segment['delay_ms']}\n",
                                f"{elapsed+segment['duration_ms']} {segment['delay_ms']}\n"])
            elapsed += segment['duration_ms']
        (path / 'delay.trace').write_text(''.join(delay_lines), encoding='utf-8')


def symmetric_gap(ref, target):
    for value in (ref, target):
        finite(value, 'throughput')
        if value < 0:
            raise ValueError('Negative throughput')
    if max(ref, target) == 0:
        raise ValueError('Both throughputs are zero: undefined score')
    return (ref-target)/max(ref, target)


def summarize(plan, csv_path):
    config = plan['config']
    validate_config(config)
    expected = {r['run_id']: r for r in plan['runs']}
    variants = {v['variant_id']: v for v in plan['variants']}
    seen, measurements, environments = set(), set(), set()
    successes, states = defaultdict(list), defaultdict(lambda: defaultdict(int))
    wall_time, executions = 0.0, 0
    with Path(csv_path).open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        if not set(CSV_FIELDS).issubset(reader.fieldnames or []):
            raise ValueError('Result CSV is missing required columns')
        for row in reader:
            key = row['run_id']
            if key not in expected or key in seen:
                raise ValueError(f'Unknown or duplicate run_id: {key}')
            seen.add(key)
            run = expected[key]
            for field in ('variant_id', 'repeat_index', 'order', 'target', 'reference', 'score_scheme'):
                if row[field] != str(run[field]):
                    raise ValueError(f'{key}: mismatched {field}')
            if row['source_revision'] != config['source_revision']:
                raise ValueError(f'{key}: source revision mismatch; make a new plan')
            status = row['status']
            if status not in ('pending', 'ok', 'error', 'timeout'):
                raise ValueError(f'{key}: invalid status')
            vid = row['variant_id']
            if status == 'pending':
                if any(row[f] for f in ('reference_mbps','target_mbps','wall_time_s','protocol_executions')):
                    raise ValueError(f'{key}: pending rows must not contain measurements')
                states[vid][status] += 1
                continue
            seconds = float(row['wall_time_s'])
            finite(seconds, 'wall_time_s')
            if seconds < 0:
                raise ValueError('Negative wall time')
            count = integer(float(row['protocol_executions']), 'protocol_executions', 0)
            wall_time += seconds
            executions += count
            if status in ('error', 'timeout'):
                if row['reference_mbps'] or row['target_mbps'] or not row['error'].strip():
                    raise ValueError(f'{key}: errors need a reason and no success metrics')
                states[vid][status] += 1
                continue
            if count < 2:
                raise ValueError('Each successful pair must account for at least two protocol executions')
            for field in ('kernel_version','environment_id','measurement_id','log_path'):
                if not row[field].strip():
                    raise ValueError(f'{key}: missing {field}')
            if row['measurement_id'] in measurements:
                raise ValueError('Duplicate measurement_id: do not reuse one measurement as an independent run')
            measurements.add(row['measurement_id'])
            environments.add((row['kernel_version'], row['environment_id']))
            if len(environments) > 1:
                raise ValueError('Mixed kernel/environment IDs; analyze separate plans')
            ref, target = float(row['reference_mbps']), float(row['target_mbps'])
            try:
                score = symmetric_gap(ref, target)
            except ValueError:
                # Nonfinite/negative metrics are data errors, not non-failures.
                if ref == 0 and target == 0:
                    states[vid]['undefined_zero_zero'] += 1
                    continue
                raise
            states[vid]['ok'] += 1
            successes[vid].append((ref, target, score))
    for key in set(expected) - seen:
        states[expected[key]['variant_id']]['missing'] += 1
    expected_counts = defaultdict(int)
    for run in expected.values():
        expected_counts[run['variant_id']] += 1
    per_variant = []
    for vid, variant in variants.items():
        samples = successes[vid]
        complete = len(samples) == expected_counts[vid]
        median_score = symmetric_gap(statistics.median(s[0] for s in samples),
                                     statistics.median(s[1] for s in samples)) if complete else None
        per_variant.append({'variant_id': vid, 'trace_id': variant['trace_id'],
                            'family': variant['family'], 'magnitude': variant['magnitude'],
                            'expected_pairs': expected_counts[vid], 'valid_pairs': len(samples),
                            'states': dict(states[vid]), 'complete': complete,
                            'score_from_median_throughputs': median_score,
                            'is_failure': median_score > config['failure_threshold'] if complete else None,
                            'run_score_stdev': statistics.stdev(s[2] for s in samples) if len(samples)>1 else None,
                            'run_score_range': [min(s[2] for s in samples),max(s[2] for s in samples)] if samples else None})
    baseline = next(v for v in per_variant if v['family'] == 'baseline')
    cells = []
    for cell in plan['cells']:
        data = [v for v in per_variant if v['family'] == cell['family'] and v['magnitude'] == cell['magnitude']]
        complete = [v for v in data if v['complete']]
        fails = sum(v['is_failure'] for v in complete)
        rate = fails/len(complete) if complete else None
        cells.append({**cell, 'complete_variants': len(complete), 'incomplete_variants': len(data)-len(complete),
                      'failure_fraction_of_complete_variants': rate,
                      'retention_rate': rate if baseline['is_failure'] is True else None,
                      'retention_reason': 'defined' if baseline['is_failure'] is True else 'baseline_not_confirmed_failure'})
    return {'schema_version':1, 'config_status':config['status'], 'score_scheme':SCORE,
            'failure_threshold':config['failure_threshold'], 'failure_rule':'score > threshold',
            'baseline':baseline, 'cells':cells, 'variants':per_variant,
            'budget': {**plan['budget'], 'rows_present':len(seen), 'rows_missing':len(expected)-len(seen),
                       'protocol_executions_reported':executions, 'sum_pair_wall_time_s':wall_time},
            'interpretation':'Descriptive local results only; not real-world failure probabilities or confidence intervals.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    build = commands.add_parser('build')
    build.add_argument('--trace', required=True)
    build.add_argument('--config', required=True)
    build.add_argument('--out', required=True)
    decode_cmd = commands.add_parser('decode')
    decode_cmd.add_argument('--codec', choices=CODECS, required=True)
    decode_cmd.add_argument('--genes', nargs='+', type=int, required=True)
    decode_cmd.add_argument('--out', required=True)
    analyze = commands.add_parser('summarize')
    analyze.add_argument('--plan', required=True)
    analyze.add_argument('--runs', required=True)
    analyze.add_argument('--out', required=True)
    args = parser.parse_args()
    try:
        if args.command == 'build':
            plan = build_plan(load(args.trace), load(args.config))
            export_plan(plan, args.out)
            print(json.dumps({'variants':len(plan['variants']), **plan['budget'],
                              'shortfalls':sum(c['shortfall'] for c in plan['cells'])}, indent=2))
        elif args.command == 'decode':
            save(args.out, decode(args.genes, args.codec))
        else:
            report = summarize(load(args.plan), args.runs)
            save(args.out, report)
            print(json.dumps(report['budget'], indent=2))
    except (ValueError, KeyError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
