# Member C to Member B: CC pilot integration contract

Prepared for sharing; no message has been sent automatically.

## Proposed pilot

Single-path continuous transfer; target BBR, reference CUBIC. Keep queue size, workload, topology, protocol versions, and total trace duration fixed. Start with throughput only. Please confirm the exact kernel and BBR implementation, emulator revision, and command that has actually run successfully.

Before collecting a whole batch, return one original trace and a few repeat pairs with raw logs. The supplied trace is synthetic, not a reproduced failure. Candidate pair execution code lives under `mptcp_type=7/8`, not the default type-0 capacity comparison. See the source audit before choosing a runner.

## Input to the runner

Read `plan.json` and the shuffled schedule from `runs_template.csv`. For each row, look up its `variant_id` and evaluate the corresponding physical trace on both algorithms, in the specified `reference_first` or `target_first` order. Reset each protocol execution to an independent initial state. Do not interpret the perturbation seed as controlling kernel randomness.

For the default pair codec, `encoded_trace` has layout `[bw genes, delay genes, duration genes, queue gene]`, with scales 500 Kbps / 1 ms / 50 ms / 10 packets. Physical JSON, NON-PDO bandwidth, and delay files are also provided. Do not scale either form twice. Confirm that this emulator's delay trace describes the intended path delay; it is not a direct RTT measurement.

## CSV columns

| Columns | How to fill |
| --- | --- |
| `run_id`, `variant_id`, `repeat_index`, `order`, `target`, `reference`, `score_scheme` | Preserve the scheduled values. A row is one target/reference pair, not one protocol execution. |
| `status` | `pending`, `ok`, `error`, or `timeout`. |
| `reference_mbps`, `target_mbps` | Nonnegative decimal Mbps from the same declared measurement-window rule; fill only for `ok`. Do not put a precomputed AdvNet score here. |
| `wall_time_s` | Actual wall-clock cost of the pair including its setup/retries; record for errors/timeouts too. |
| `protocol_executions` | Actual count of protocol launches including retries. A successful pair has at least two. |
| `source_revision` | Must match the plan. If patching upstream, pin the patched code (or record a new commit) and generate a new plan rather than mislabel the code. |
| `kernel_version` | Actual kernel/CC build identifier. |
| `environment_id` | A stable identifier for host, emulator build, workload, startup/window rules, and any configuration patches. Save that mapping in an accompanying environment description. |
| `measurement_id` | Unique ID for this independently executed pair; never reuse one measurement as multiple repeats. |
| `log_path` | Path/URI to the retained raw logs; not automatically fetched by Member C's summarizer. |
| `error` | Reason for `error`/`timeout`. Leave throughput values blank for those rows. |

Use one kernel/environment ID per batch. Run a fresh plan for changed protocol versions, measurement conventions, or scoring. A successful zero/zero result is counted as undefined, not as a non-failure. Failed runs consume budget and must remain in the results. Keep detailed per-attempt logs when retrying; one row reports aggregate launch count/cost.

## What Member C returns

For each fully measured trace, the score is computed from median raw target/reference throughputs. Outputs show original-trace replay variability, per-variant scores, failure fraction, retention conditional on the original being a failure, completion counts, and total reported execution cost. Missing measurements are never filled with fabricated values.

Default threshold 0.2 and repeat counts are pilot settings. Freeze the threshold and sampling design after the pilot and before evaluating the final held-out traces. No confidence or real-world occurrence probability should be inferred from these initial descriptive summaries.

## Small first handoff

Before the full 140-pair template, use `examples/integration_config.json` (`samples_per_cell=1`, `magnitudes=[0.1]`). A ready-made example batch is in `runs/integration-pilot/`. This gives 14 pairs (5 original repeats + 3 perturbed variants x 3 repeats), at least 28 protocol executions. Resolve missing logs, timing, and score-unit issues on that batch first. This remains a synthetic integration fixture; use a new plan for a real counterexample.
