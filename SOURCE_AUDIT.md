# AdvNet CC interface audit

Inspected locally on October 25, 2026 at revision `6390c47f9387857d3cee036ee3be2c01848ab8cf` of [Dariwala/AdvNet](https://github.com/Dariwala/AdvNet). Findings below are static source observations, not results from a Linux execution.

## Trace mapping

| Path | Finding |
| --- | --- |
| `single_cc/split_trace.py:1` | Splits `3*n+1` genes into bandwidths, latencies, durations, queue. |
| `single_cc/convert.py:4` | Scales bandwidth by 500, delay by 1, duration by 50, queue by 100. |
| `mptcp/split_trace.py` | Modes 6/7/8 use the single-path `3*n+1` layout despite the directory name; other modes can use a multipath layout. |
| `mptcp/convert.py:4` | Same bandwidth/delay/duration scales, but queue scales by 10. |
| `utils/generate_bandwidth_trace.py` | PDO generator uses 12,000-bit packet spacing in ms, implying Kbps. NON-PDO generator writes bandwidth and duration per segment. |
| `utils/generate_delay_trace.py:3` | Writes each segment's delay at `start+1` and `end`, in ms-valued trace coordinates; do not label it measured RTT. |

The pair backend imports `create_trace_non_pdo`. Our default export follows that path. Delay rounding in upstream and integer search grids mean very small nominal changes may disappear; our encoder rejects unrepresentable values.

## Which path is actually being evaluated?

`search_adv_traces.py --type=0` selects `single_cc.evaluate.evaluate`. This compares a selected protocol with a computed maximum-throughput baseline; it is not the assumed BBR-vs-CUBIC experiment.

`mptcp/evaluate.py` modes 7/8 contain repeated executions of two single-path protocols, with parallel and serial arrangements respectively. They are candidate integration routes, **not a claim that the checkout is turnkey**. The exact entry point and emulator build must be verified by Member B before execution.

The default type-0 path has visible integration defects in this checkout:

- `single_cc/evaluate.py:115` sets `tot_bytes` and `duration` from `ord(alg[0])` rather than measured log data.
- `run_iperf_client` returns three items, while `get_throughput` at line 192 unpacks two.
- The parallel helper also returns placeholder leading fields; pair paths discard those fields and parse logs, so the serial defect alone does not prove that the pair path is unusable.

Record these as checks for the person operating Linux. Do not repair the whole upstream project or assume the paper's methods fail based on these code issues. This week's offline tooling does not import evaluator modules or run their process-management commands.

## Score semantics

- `single_cc/evaluate.py:218`: capacity-based score `(baseline - protocol)/baseline`, median over repeated evaluations.
- `mptcp/evaluate.py:160`: checked-out pair evaluator sets `t_coeff=1`, but constructs utilities through `SingleCCProtocolScore.w_sum`.
- `scoring/scoring.py:88`: utility normalizes throughput and clips it at 1; delay is also computed. Confirm the consistent units of `t_ref` and measured throughput before reproduction (raw parser uses a 1024-based denominator while trace generation uses Kbps).
- `scoring/scoring.py:104`: final score uses `(median(ref utilities) - median(target utilities)) / max(...)`.
- `mptcp/evaluate.py:329,385`: pair modes use that final score. Their per-repeat log column uses another denominator. Do not average that log column and call it the returned search objective.
- `GA/problem.py::_evaluate`: pymoo minimizes `-score`. A positive adversarial score becomes a negative optimizer objective; preserve that sign convention when a future scoring modification is added.

Our week-1 raw-throughput estimator is explicitly named and separate. It agrees with the final normalized form only when common scaling cancels and clipping/other utility terms do not change the result. Collect raw per-repeat metrics so alternative definitions can be recomputed later.

## Integration decisions still needed

1. Linux kernel, BBR version, emulator binary/version, exact runner command and any patches.
2. A known trace with raw target/reference measurements and retained logs.
3. Throughput units and measurement-window convention, including connection startup.
4. Whether the team prioritizes exact upstream scoring reproduction or the explicitly proposed throughput-only estimator.
5. Whether to use a serial scheduler with randomized target/reference order; do not silently mix that with fixed-order or parallel runs.

These decisions do not block offline trace generation or invariant testing. They do block claims about real CC behavior and exact paper reproduction.
