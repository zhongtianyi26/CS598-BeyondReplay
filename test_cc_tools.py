"""Offline invariants and failure-handling tests; all metric fixtures are synthetic."""
import copy
import csv
import importlib
import math
import random
import sys
import tempfile
import unittest
from pathlib import Path

import cc_tools as cc

ROOT = Path(__file__).resolve().parent


class TraceTests(unittest.TestCase):
    def setUp(self):
        self.trace = cc.load(ROOT/'examples/pilot_trace.json')
        self.config = cc.load(ROOT/'examples/pilot_config.json')

    def test_explicit_codec_and_physical_units(self):
        genes = [40,10,40,40,80,40,200,200,200,10]
        self.assertEqual(cc.encode(self.trace,'pair_678'),genes)
        decoded = cc.decode(genes,'pair_678')
        self.assertEqual(decoded['segments'],self.trace['segments'])
        self.assertEqual(decoded['queue_packets'],100)
        self.assertEqual(cc.decode(genes,'single_cc')['queue_packets'],1000)

    def test_lossy_export_rejected(self):
        bad = copy.deepcopy(self.trace)
        bad['segments'][0]['bandwidth_kbps'] += 1
        with self.assertRaises(ValueError): cc.encode(bad,'pair_678')

    def test_invalid_traces_and_vectors(self):
        for value in (-1,0,float('nan'),float('inf'),True):
            bad = copy.deepcopy(self.trace)
            bad['segments'][0]['bandwidth_kbps'] = value
            with self.assertRaises(ValueError): cc.validate_trace(bad)
        with self.assertRaises(ValueError): cc.decode([1,2,3,4,5],'pair_678')
        with self.assertRaises(ValueError): cc.decode([1,2,3,4],'unknown')

    def test_known_upstream_converter_parity(self):
        source = ROOT.parent/'abr-day1/vendor/AdvNet'
        if not source.exists():
            self.skipTest('Optional pinned upstream checkout absent')
        sys.path.insert(0,str(source))
        try:
            single = importlib.import_module('single_cc.convert').convert
            pair = importlib.import_module('mptcp.convert').convert
            for codec in ('single_cc','pair_678'):
                genes = cc.encode(self.trace,codec)
                if codec == 'single_cc':
                    bw,delay,duration,queue = single(genes)
                else:
                    converted = pair(genes,7)
                    split = importlib.import_module('mptcp.split_trace').split_trace
                    bw,delay,duration,bw2,delay2,queue = split(converted,7)
                    self.assertEqual(bw2,[])
                self.assertEqual(bw,[20000,5000,20000])
                self.assertEqual(delay,[40,80,40])
                self.assertEqual(duration,[10000]*3)
                self.assertEqual(queue,100)
        finally:
            sys.path.pop(0)

    def test_perturbations_only_change_selected_family(self):
        original = copy.deepcopy(self.trace)
        rng = random.Random(4)
        for family in ('bandwidth','delay','timing'):
            for _ in range(100):
                perturbed, detail = cc.perturb(self.trace,family,0.1,self.config,rng)
                self.assertEqual(perturbed['queue_packets'],original['queue_packets'])
                self.assertEqual(sum(s['duration_ms'] for s in perturbed['segments']),30000)
                self.assertLessEqual(abs(detail['actual_relative_change']),0.1)
                changed = []
                for i,(before,after) in enumerate(zip(original['segments'],perturbed['segments'])):
                    for field in cc.FIELDS:
                        if before[field] != after[field]: changed.append((i,field))
                field = {'bandwidth':'bandwidth_kbps','delay':'delay_ms','timing':'duration_ms'}[family]
                self.assertTrue(all(f == field for _,f in changed))
                self.assertEqual(len(changed),2 if family == 'timing' else 1)
        self.assertEqual(self.trace,original)

    def test_reproducible_plan_and_no_duplicates_per_cell(self):
        plan = cc.build_plan(self.trace,self.config)
        self.assertEqual(plan,cc.build_plan(self.trace,self.config))
        self.assertEqual(len(plan['variants']),46)
        self.assertEqual(plan['budget']['planned_pair_runs'],140)
        for cell in plan['cells']:
            ids = [v['trace_id'] for v in plan['variants'] if v['family']==cell['family'] and v['magnitude']==cell['magnitude']]
            self.assertEqual(len(ids),len(set(ids)))
        self.config['seed'] += 1
        self.assertNotEqual(plan,cc.build_plan(self.trace,self.config))

    def test_subgrid_and_single_segment_shortfall_not_noop(self):
        self.trace['segments'] = [self.trace['segments'][0]]
        self.config['magnitudes'] = [0.000001]
        self.config['samples_per_cell'] = 1
        plan = cc.build_plan(self.trace,self.config)
        self.assertEqual(len(plan['variants']),1)
        self.assertEqual(sum(c['shortfall'] for c in plan['cells']),3)

    def test_bounds_rejection_never_clamps(self):
        self.config['bounds']['bandwidth_kbps'] = [5000,20000]
        for seed in range(100):
            result = cc.perturb(self.trace,'bandwidth',0.2,self.config,random.Random(seed))
            if result:
                trace,change = result
                i = change['coordinate_index']
                self.assertEqual(trace['segments'][i]['bandwidth_kbps']-self.trace['segments'][i]['bandwidth_kbps'],change['delta'])
                cc.validate_trace(trace,self.config['bounds'])

    def test_export_does_not_overwrite_and_matches_formats(self):
        plan = cc.build_plan(self.trace,self.config)
        with tempfile.TemporaryDirectory() as temp:
            cc.export_plan(plan,temp)
            root = Path(temp)/'traces/baseline'
            self.assertEqual((root/'bandwidth.nonpdo').read_text(),'NON-PDO\n20000 10000\n5000 10000\n20000 10000\n')
            self.assertEqual((root/'delay.trace').read_text(),'1 40\n10000 40\n10001 80\n20000 80\n20001 40\n30000 40\n')
            with self.assertRaises(ValueError): cc.export_plan(plan,temp)


class SummaryTests(unittest.TestCase):
    def setUp(self):
        config = cc.load(ROOT/'examples/pilot_config.json')
        config.update(samples_per_cell=1,magnitudes=[0.1])
        self.plan = cc.build_plan(cc.load(ROOT/'examples/pilot_trace.json'),config)
        self.rows = []
        for run in self.plan['runs']:
            self.rows.append({**run,'status':'ok','reference_mbps':10,'target_mbps':2,
                              'wall_time_s':1,'protocol_executions':2,
                              'source_revision':config['source_revision'],
                              'kernel_version':'SYNTHETIC_FIXTURE','environment_id':'TEST_ONLY',
                              'measurement_id':run['run_id'],'log_path':'synthetic://test-only','error':''})

    def summarize(self,rows=None):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp)/'synthetic.csv'
            with file.open('w',newline='') as f:
                writer = csv.DictWriter(f,fieldnames=cc.CSV_FIELDS)
                writer.writeheader()
                writer.writerows(self.rows if rows is None else rows)
            return cc.summarize(self.plan,file)

    def test_complete_data_retention_and_budget(self):
        result = self.summarize()
        self.assertEqual(result['baseline']['score_from_median_throughputs'],0.8)
        self.assertTrue(all(c['retention_rate']==1 for c in result['cells']))
        self.assertEqual(result['budget']['protocol_executions_reported'],len(self.rows)*2)

    def test_aggregate_is_gap_of_medians_not_median_of_gaps(self):
        rows = [r for r in self.rows if r['variant_id']=='baseline']
        for row,ref,tar in zip(rows,[1,2,3,4,5],[0,1,1,4,5]):
            row.update(reference_mbps=ref,target_mbps=tar)
        result = self.summarize()
        self.assertAlmostEqual(result['baseline']['score_from_median_throughputs'],2/3)

    def test_nonfailure_baseline_has_no_retention_claim(self):
        for row in self.rows:
            if row['variant_id']=='baseline': row['target_mbps']=10
        self.assertTrue(all(c['retention_rate'] is None for c in self.summarize()['cells']))

    def test_missing_runs_excluded_not_treated_as_success(self):
        removed = next(r for r in self.rows if r['variant_id']!='baseline')
        self.rows.remove(removed)
        result = self.summarize()
        variant = next(v for v in result['variants'] if v['variant_id']==removed['variant_id'])
        self.assertFalse(variant['complete'])
        self.assertIsNone(variant['is_failure'])
        self.assertEqual(result['budget']['rows_missing'],1)

    def test_timeout_and_zerozero_accounted_separately(self):
        self.rows[0].update(status='timeout',reference_mbps='',target_mbps='',error='fixture timeout')
        self.rows[1].update(reference_mbps=0,target_mbps=0)
        result = self.summarize()
        self.assertEqual(sum(v['states'].get('timeout',0) for v in result['variants']),1)
        self.assertEqual(sum(v['states'].get('undefined_zero_zero',0) for v in result['variants']),1)
        self.assertEqual(result['budget']['protocol_executions_reported'],2*len(self.rows))

    def test_reject_duplicates_nans_and_mixed_context(self):
        with self.assertRaises(ValueError): self.summarize(self.rows+[self.rows[0]])
        for field,value in [('reference_mbps',float('nan')),('target_mbps',-1),
                            ('source_revision','other'),('score_scheme','wrong'),
                            ('kernel_version','different'),('measurement_id',self.rows[1]['measurement_id'])]:
            rows = copy.deepcopy(self.rows)
            rows[0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError): self.summarize(rows)

    def test_pending_template_has_no_performance_results(self):
        with tempfile.TemporaryDirectory() as temp:
            cc.export_plan(self.plan,temp)
            report = cc.summarize(self.plan,Path(temp)/'runs_template.csv')
            self.assertIsNone(report['baseline']['score_from_median_throughputs'])
            self.assertEqual(report['budget']['protocol_executions_reported'],0)
            self.assertTrue(all(c['complete_variants']==0 for c in report['cells']))


if __name__=='__main__':
    unittest.main(verbosity=2)
