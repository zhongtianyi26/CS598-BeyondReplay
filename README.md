# Member C - Week 1 CC perturbation toolkit

This is the **shared methodology / CC search** track, not ABR. The implementation is offline and uses only Python's standard library. No emulator, protocol process, server, or Linux configuration is launched.

## What is ready

- Explicit physical trace schema and lossless AdvNet integer-vector conversion.
- Seeded bandwidth, delay, and transition-time perturbations, one coordinate at a time.
- Constant total duration and queue size; bounded rejection sampling; no silent rounding or clipping.
- Experiment manifest, randomized run schedule, blank result template, and emulator input files.
- Result validation, repeated-run variability, descriptive failure-retention summaries, and execution-budget accounting.
- Tests for physical invariants, upstream converter agreement, and error/missing-data handling.

Real CC evaluation and search integration are not implemented here yet. Member B must first provide a verified Linux runner and initial traces. `examples/pilot_trace.json` is a synthetic plumbing fixture, **not a known failure**. Proposed target/reference names and the 0.2 failure threshold are pilot choices, not paper-mandated settings or validated research choices.

## Run locally

From `C:\college\cs598fyy` in PowerShell:

```powershell
& .\member-c-week1\run-week1.ps1
```

This runs the tests, creates a fresh timestamped plan, and checks the still-empty result template. It uses an existing bundled Python or accepts `-PythonPath`. It does not require NumPy, a GPU, or a Linux machine. A test additionally checks conversion against the already downloaded AdvNet checkout at `../abr-day1/vendor/AdvNet`; that test is skipped if the checkout is absent. Production code does not depend on the ABR directory.

On any machine with Python 3.10+ (verified here on 3.12), from this directory:

```text
python -m unittest -v test_cc_tools
python cc_tools.py build --trace examples/pilot_trace.json --config examples/pilot_config.json --out runs/my-pilot
python cc_tools.py summarize --plan runs/my-pilot/plan.json --runs runs/my-pilot/runs_template.csv --out runs/my-pilot/pending_report.json
```

The output directory must be empty; generation refuses to overwrite collected results. Copy `runs_template.csv` to a working results file before filling it. Actual experiment scheduling remains manual / external; the script does not execute the template.

## Trace representation and encoder

```json
{
  "schema_version": 1,
  "queue_packets": 100,
  "segments": [
    {"bandwidth_kbps": 20000, "delay_ms": 40, "duration_ms": 10000},
    {"bandwidth_kbps": 5000, "delay_ms": 80, "duration_ms": 10000}
  ]
}
```

Use positive integer physical values, with durations at least 2 ms. Delay denotes the value passed to the emulator delay trace, **not an asserted end-to-end RTT**. Queue is fixed in packets.

The upstream vector consists of `[all bandwidth genes, all delay genes, all duration genes, queue gene]`, of length `3*n+1`. Scale factors are 500 Kbps, 1 ms, and 50 ms. Queue scaling differs: `single_cc` uses 100 packets per gene; the pair comparison modes `mptcp_type=6/7/8` use 10. The workflow deliberately builds only `pair_678` plans; `single_cc` decoding/encoding is available for audit, not for launching that legacy runner.

Import a real vector only after confirming its encoder with Member B:

```text
python cc_tools.py decode --codec pair_678 --genes 40 10 40 40 80 40 200 200 200 10 --out examples/decoded_trace.json
```

This example is the supplied synthetic fixture. Do not substitute a multipath (`5*n+1`) vector or a physical-units vector for these encoded genes. Off-grid exports fail rather than round small perturbations away.

## Perturbation distribution

Each candidate is drawn relative to the original trace, never by accumulating previous perturbations:

| Family | One proposal changes | Preserved |
| --- | --- | --- |
| Bandwidth | One segment's bandwidth by a nonzero integer-grid offset within the relative radius | Delays, durations, queue |
| Delay | One segment's emulator delay by a nonzero integer-grid offset within the relative radius | Bandwidths, durations, queue |
| Timing | One shared segment boundary; add delta to its left duration and subtract delta from its right duration | Total time, segment bandwidth/delay levels, queue |

Timing radius = magnitude x the shorter of the two original adjacent durations. It moves the joint bandwidth/delay boundary; it does **not** isolate only bandwidth timing or preserve the bandwidth-time integral. This distinction must appear in the experiment interpretation.

Sample a coordinate, a grid-offset magnitude, and a sign uniformly at each proposal. Reject invalid proposals and duplicates within each family/magnitude cell. Accepted samples therefore follow a bounded, conditional distribution, not continuous Gaussian noise. A physical variant can reappear in a different magnitude cell. Requests that cannot produce enough distinct legal changes report a shortfall after a bounded number of attempts. A relative radius below the emulator/encoding grid does not produce fake no-op samples.

The seed controls the proposed traces, protocol order labels, and shuffled run schedule; it does not control Linux nondeterminism.

## Default pilot and cost

The user authorized a provisional single-path setup while Member B's runner is undecided. Defaults:

- Target `bbr`, reference `cubic`; exact kernel and BBR implementation still need to be recorded.
- Three families x three radii (5%, 10%, 20%) x five distinct variants = 45 variants.
- Original trace repeated five times; each variant repeated three times = 140 pair records, at least 280 protocol executions.
- All traces last 30 seconds: 8,400 seconds (2 h 20 min) of nominal sequential protocol runtime, plus setup, retries, and other overhead. **This budget has not been run.**

For first runner integration, reduce to one radius and one sample per family. Do not launch the full schedule until per-pair cost and runner reliability are known. Replace the fixture with Member B's actual counterexamples before drawing scientific conclusions.

## Generated artifacts

`plan.json` contains configuration, source revision, physical hashes, parent/variant relationships, seeds, realized changes, encoded vectors, schedule, and planned budget. Each `traces/<variant_id>/` contains canonical JSON, NON-PDO bandwidth input and delay input, matching the pair backend's generators. They are data files, not a launch command. `runs_template.csv` is the interface for Member B. The summary of a pending template contains no scores or performance conclusions.

## Score and interpretation

For this pilot, record raw target/reference throughput in **decimal Mbps** over the same specified measurement window. For each complete variant, compute:

```text
R = median(reference throughput repeats)
T = median(target throughput repeats)
score = (R - T) / max(R, T)
failure = score > predeclared threshold
```

The score is positive when target is worse. Both medians being zero is undefined. Per-run score range/stdev are diagnostics of replay variation, not a confidence interval on the median score. We deliberately do not average all repeated runs as if they were independent environmental perturbations.

The estimator is tagged `throughput_symmedian_v1`. It is **not automatically identical** to upstream AdvNet: upstream pair modes pass clipped/normalized utility samples to `compute_score`, and `log=True` exposes a different per-run formula. See `SOURCE_AUDIT.md`. Raw throughput has consistent direction and is easy to audit, but any paper-reproduction claim requires freezing an exact compatible scoring definition.

Retention is the fraction of fully measured perturbed variants above threshold, and is reported only when the original trace is itself a confirmed failure under the same threshold and repeat count. Missing runs, timeouts, undefined values, and incomplete variants are explicitly counted; they are not successes or non-failures. Reports must include completion counts because selective execution failure can bias the completed subset.

The result is a descriptive local statistic under the chosen perturbation design, not an Internet failure probability or proof of global robustness. Wider regions are not automatically more important than narrow, severe bugs.

## Team handoff

See `HANDOFF_MEMBER_B.md` for the result contract and pending integration decisions. See `WEEK1_STATUS.md` for your immediate priorities. Existing upstream repositories and the ABR work were not edited.
