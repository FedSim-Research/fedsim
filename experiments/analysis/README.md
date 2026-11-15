# Manuscript analysis

Commands that generate paper tables and plots require `--paper` explicitly; the
conditional calculation uses `--output`. Relocating these scripts does not select
or rewrite a producing experiment revision.
The analysis code is covered by the software repository's [Apache-2.0 license](../../LICENSE).
Install the fully pinned plotting dependencies from this directory's
`requirements.txt` in a separate environment matching `environment.json`.
Raw archives are read and checksum-verified; generated outputs are written only
to the supplied paper directory. These scripts do not start training jobs.

Analysis uses Python 3.14.10 and Matplotlib 3.11.2. Install the analysis-only
dependencies with `python -m pip install -r experiments/analysis/requirements.txt`. They are
separate from the software runtime lock. None of these scripts submits jobs
or changes archived measurements.

## Six-client study (revision 2f724ba1767e)

Run from the software repository root. Examples assume sibling `paper/` and
`experiment-runs/` directories; adjust the explicit paths for your checkout:

`--paper` accepts any existing output directory. Create `../paper` before using
these examples; regenerating tables and plots does not require the manuscript
sources. The raw, sealed experiment archives must be supplied separately.

~~~powershell
python experiments/analysis/generate_primary_results.py --archive ../experiment-runs/cifar10-main-study-2f724ba-2026-11-13 --paper ../paper
~~~

The archive must include its completed status and original checksum manifest.
The script verifies every manifest entry before reading the 24 primary cases,
checks all three seeds and six evaluation times per case, and checks the
derived accuracy means and standard deviations against the archived summary.
Calibration cases are excluded. Run archives are read without modification.

Outputs:

- generated/primary-results.tex: final accuracy and loss, with sample SD.
- generated/primary-network.tex: the two configured network profiles.
- generated/primary-exchanges.tex: observed asynchronous protocol counters.
- generated/primary-numbers.tex: numerical macros used in manuscript prose.
- generated/primary-evidence.json: archive identity and derived contrasts.
- generated/primary-run-values.csv: unrounded individual run values.
- figures/primary-learning-curves.pdf and .png: means with sample-SD bands.

The statistical unit is a seeded run. A Spyker-inspired run contributes one
mean over its three server metrics, not three independent repetitions.
The bands describe seed variation; they are not confidence intervals.
The PDF output omits creation/modification timestamps. Repeated generation
in the recorded analysis environment produced identical bytes for all eight
outputs; this does not assert deterministic replay of asynchronous training.

For an author checkout containing the manuscript and its build helper, refresh
the PDF after regeneration:

~~~powershell
python ../paper/scripts/build.py
~~~

The paper build command creates its own ignored build directory and refreshes
the root PDF after references settle. `environment.json` records the analysis environment.
No empirical scalability claim should be added from these six-client runs.

## 200-client comparison (revision 20d507096582)

~~~powershell
python experiments/analysis/generate_population_results.py --archive ../experiment-runs/cifar10-population-cohort-20d5070-2026-11-14 --paper ../paper
~~~

This requires all 12 measurements, their final whole-archive manifest,
seven periodic points per case, genuine automatic Loki evidence, complete
per-server checkpoint mappings, and raw orchestrator logs. It rejects
incomplete experiments. Calibration and capacity probes are excluded.

Outputs use the `population-` prefix under `generated/` and `figures/`.
Work counts distinguish dispatched client-fit callbacks from delivered updates.
The former include terminal look-ahead training whose result can fall beyond
the virtual horizon. Peer merges and round initiations count different events.
Spyker-inspired accuracy is an equal-weight mean of four separately evaluated
server models, not an ensemble or a merged checkpoint.
The generated server CSV preserves all24 final asynchronous server records;
they are model-level details, not24 independent repetitions. Placement contrasts
include the individual seed-paired differences and their sample standard deviation.

## Predeclared learning-rate sensitivity

~~~powershell
python experiments/analysis/generate_lr_ablation.py --primary ../experiment-runs/cifar10-population-cohort-20d5070-2026-11-14 --ablation ../experiment-runs/cifar10-lr-factorial-cohort-20d5070-2026-11-14 --paper ../paper
~~~

The follow-up selects six Spyker cases from a canonical twelve-case parent
plan: three seeds in each placement. The original balanced-only control was
recorded before the first completed primary asynchronous outcome; after the
primary grid, it was prospectively extended before any intervention run.
`PROTOCOL-AMENDMENT.json` and the original protocol retain both decisions.
The original balanced-only archive was never executed and is not evidence.

The feedback measurements span two preserved execution segments after a Ray
reference-count assertion interrupted concentrated seed43. All four completed
cases are retained; only failed seed43 and unsubmitted seed44 are run in the
second segment with identical scientific inputs. The derived six-case cohort
binds copies to both original manifests and parses work separately by segment,
excluding the failed attempt. It is not an uninterrupted execution, and the
failure's precise cause is unresolved. Restarting does not establish a fix.

The selection manifest must match its parent checksum. Both complete archives,
source/lock/image, dataset, resources and planned partitions are checked. Only
campaign names and beta changing from .05 to 0 may differ. Every case must retain
all four peers/checkpoints, completed exchange, actual updates from all 200 clients
and matching server/log counters. Initial metrics must agree within tolerance.

Outputs use `lr-ablation-` prefixes: a four-cell table, six full-precision paired
rows, evidence JSON, numerical macros and a two-panel curve. Per-placement
feedback contrasts and their three seed-paired interaction contrasts are
reported descriptively. All six outcomes remain regardless of direction;
three seeds per cell do not establish significance or a universal optimum.

For all cohorts the statistical unit remains the seeded run. Sample-SD bands
are descriptive; time points and server models are not extra repetitions.
Different client populations, virtual budgets and source revisions must not
be pooled as if they were one controlled comparison. The generators reject incomplete or unsealed experiment archives.

## Conditional feedback calculation

`learning_rate_sweep.py` checks the frozen feedback method by AST comparison and
calculates next-rate assignments under an equal-count update-sweep assumption.
It never executes code from the ZIP. Its JSON is an analytical illustration, not
observed runtime learning-rate data. The original first interrupted population
attempt is retained separately and excluded. The restarted cohort retains all
six fully verified balanced cases from its first retained segment, four verified
concentrated cases from its second, and one final seed44 case from each of its third and fourth segments. This is
documented in the derived cohort's COHORT-ASSEMBLY.json and cohort-membership.json.
Every case retains its raw source segment. The work-count parser handles segments
separately so interrupted-case activity cannot contaminate completed-case counts.

The conditional calculation takes an original execution-segment archive containing
`source.zip`, `source-record.json` and `input-checksums-measurement.json`, rather than
an assembled cohort:

```sh
python experiments/analysis/learning_rate_sweep.py --archive ../experiment-runs/cifar10-population-study-20d5070-2026-11-14 --output ../paper/generated/lr-feedback-sweep.json
```

## Post-hoc feedback reconstruction

~~~powershell
python experiments/analysis/reconstruct_feedback.py --primary ../experiment-runs/cifar10-population-cohort-20d5070-2026-11-14 --feedback ../experiment-runs/cifar10-lr-factorial-cohort-20d5070-2026-11-14 --paper ../paper
~~~

This addition uses the existing twelve Spyker cases (six reference and six
zero-penalty cases). It does not submit jobs or create new training evidence.
Both whole-archive manifests, case-level source origins and final peer counters
are checked. The script is restricted to the reviewed producing source ZIP;
it checks the feedback AST and rate-to-training path without executing ZIP code.

Reconstruction preserves physical line order in each case's single orchestrator
dispatch log. Rounded virtual timestamps must not be sorted to resolve ties.
Synchronous server actors use default same-submitter FIFO execution; no
failed/retried callbacks are assumed within the included completed cases.
Client counts start at zero and the mean includes only clients that have
already delivered an update. Peer messages do not alter these counters.

The first completed update per client uses the base rate; subsequent completed
updates use that client's previous rate assignment. The final next-rate decisions
include look-ahead work that can fall outside the virtual horizon. These two
denominators are exported separately. Completed per-client counts are checked
against all 200 planned clients, server-local endpoint counters and independent
work totals. The difference between next-rate and completed-rate floor counts
must equal the number of final floor assignments.

Outputs are `feedback-reconstruction-values.csv`, a 2,400-row per-client CSV,
numerical TeX macros and an evidence JSON with raw-log paths/hashes and ordering
assumptions. In each reference case 11,360 of 14,600 completed updates have a
reconstructed rate at the floor (77.81%); next-rate decisions give 11,520 (78.90%).
Both counts are zero at beta=0. Identical incidence across placements means that
frequency alone cannot explain their different accuracy response. This is
source-implied control state, not captured optimizer telemetry, a unique causal
attribution or an empirically calibrated intermediate penalty.

## Operational repeat audit

~~~powershell
python experiments/analysis/generate_operational_repeat.py --interrupted ../experiment-runs/cifar10-population-study-20d5070-2026-11-14 --restarted ../experiment-runs/cifar10-population-cohort-20d5070-2026-11-14 --paper ../paper
~~~

The first excluded attempt contains only two completed cases, one per method at
balanced seed42. These can be compared with their retained counterparts as an
operational replay observation. They are never pooled as extra seeds or selected
as better endpoints. One contrast per method does not estimate replay variance.

## Short functional capacity probes

~~~powershell
python experiments/analysis/generate_capacity_results.py --candidate ../experiment-runs/bounded-clients-shared-model-candidate-2026-11-14 --paper ../paper
~~~

Add `--four-workers` with the sealed 1,000-client Spyker follow-up root. A separate,
conditionally launched 2,000-client HierFL diagnostic can be included with
`--additional-four-workers` and its sealed root. Prepared but unexecuted probes
are not reported as outcomes. Every root must
have its final manifest. The analysis checks runtime equivalence for pre-commit
candidate probes without replacing their original provenance, counts distinct
client-update senders from raw orchestrator logs, and requires every requested
client to contribute for a completed probe. Failed/guard-aborted probes remain
visible. A two-second horizon supports functional capacity, not convergence or
controlled throughput. The 500-client HierFL probe's overlap exclusion remains.

## Internal timing consistency

`generate_timing_consistency.py --archive <population-cohort>` checks the
configured homogeneous cost model against the per-client event counts already
verified by the population analysis. It also checks all twelve captured definition
checksums, group populations, client compute factors, endpoint bandwidths,
latencies and zero noise/loss/jitter. Its report binds the derived population
evidence by SHA-256. Verified checkpoint tensor bytes and planned
200-example partitions predict 42 HierFL and 73 Spyker updates per client at 60 virtual
seconds. All 12 primary traces match. This is an implementation consistency check,
not hardware calibration or an actor-level dataset-row export. The generated
JSON and TeX numerical macros retain that scope.

## Figure conventions

The three learning figures use shared `figure_style.py`: single-column
3.45-by-3.65-inch canvases with two vertically stacked panels, conventional
Matplotlib typography (DejaVu Sans), the original report's green/blue method colors, black
box axes, ordinary grids and framed legends. Both 200-client figures use the
same labeled 0--40% range; the separate network figure uses 0--85%. Every y axis
starts at zero. Different ranges must not be read as a cross-cohort effect
comparison. Markers and line styles distinguish methods/controls and placements.
Shading is one sample standard deviation across three seeds, not a confidence
interval. Vector PDFs embed TrueType fonts; PNG previews use 300 dpi.

HierFL uses `#008000`, Spyker-inspired learning `#0000FF`, and the disabled-feedback
control `#FF0000`. Lines are 0.85 pt with small hollow 1.7 pt markers; SD bands use
alpha 0.10. Grid and frame strokes are lighter than the data lines. The three
generators inherit line/marker sizes from the shared style rather than overriding
them independently. The original PNG files keep their native pixels and legends.

Selected tables fit one column through shorter, caption-defined labels rather
than smaller fonts. The work table omits repeated plus/minus-zero suffixes and
states explicitly that all counts agree across three seeds. Full-precision CSV
and JSON outputs are unchanged. The two original PNG plots remain unmodified;
the manuscript displays each at normal column width, as in the original report.
Only outer white margins of the original PNGs are trimmed in TeX; axes, labels
and plotted data remain intact. References start on their own final page;
the preceding body page closes with balanced columns. Neither data points
nor uncertainty bounds change with these layout choices.

## Reserved artifact DOI

The author supplied `10.5281/zenodo.24245352` for the planned artifact deposit.
It is reserved and unpublished at this review stage. The manuscript includes it
as a draft-deposit reference, without claiming that the files are publicly
accessible. The intended organization is analysis scripts in the existing
software repository and a fixed result archive on Zenodo; no extra experiments
repository is required.

## Operational provenance

`operational-provenance.txt` preserves the detailed execution/segmentation record moved out of the scientific narrative. The original raw manifests and per-case origin mappings remain authoritative. Completed evidence-checked cases were retained regardless of score; only unfinished cases were rerun. This companion record does not introduce new measurements or reinterpret failed partial runs as successful.

## Paired table and explicit output directory

After regenerating the feedback evidence, run:

```sh
python experiments/analysis/generate_feedback_pairs.py --paper ../paper
```

The timing check also needs the paper evidence it verifies:

```sh
python experiments/analysis/generate_timing_consistency.py --archive ../experiment-runs/cifar10-population-cohort-20d5070-2026-11-14 --paper ../paper
```

The root paper PDF is refreshed by the paper repository's build command after
numerical inputs and plots have been reviewed. The recorded source/lock/archive
hashes describe the producing simulation snapshots; the separate paper repository
tracks editorial changes. The reserved artifact DOI is not a published download.
