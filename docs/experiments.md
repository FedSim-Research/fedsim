# Local comparison campaign

The supplied configurations prepare measurements of the corrected implementation on
one machine. They ask how changing client placement and network conditions affect the two engines under
the same virtual time limit, data seed and local training settings. It does not
reproduce the historical large experiments or establish protocol fidelity.

## Design

`experiments/local-pilot.json` defines twelve sequential measurement jobs. Its
60-second horizon is a candidate for calibration, not a convergence-study setting:

| Setting | Value |
| --- | --- |
| Architectures | HierFL and Spyker-inspired |
| Clients / servers | Six clients and three edge/peer servers |
| Client placement | Balanced 2/2/2 and imbalanced 4/1/1 |
| Seeds | 42, 43, 44, paired across architectures |
| Training | One local epoch, learning rate 0.01, batch size 32 |
| Dataset | CIFAR-10, current IID partition scheme |
| Virtual duration / evaluation interval | 60 s / 20 s |
| Client / server compute factor | 500 / 1000 |
| Link bandwidth | 100 Mbps upload and download at every node |
| Client links / server links | 10 ms / 100 ms latency |
| Timing noise / jitter / loss | Zero |
| GPU budget | Zero; CPU training and evaluation |

HierFL adds its coordinator; Spyker connects all peers. Both supplied profiles
explicitly record all Spyker algorithm parameters. They retain the engine defaults
except `h_intra=4`, which requests synchronization at a model-age difference of
four since the last exchange; `h_inter` remains 5. This is a small-topology
calibration choice, not an optimal setting or a new protocol. The first real
60-second pilot with the original `h_intra=350` completed eight client updates per
server without any peer-model exchange. Its results remain a separate baseline.
Global engine defaults are unchanged. Generated node
order fixes server registration and client partition-index mapping. Changing the
placement changes which server owns each index, while retaining the six partitions.
Architecture order alternates between seeds to reduce first-run/cache effects.
This is a fixed order, not a randomized experimental design.

The supplied profiles set `require_peer_exchange=true`. Collection then requires
at least one locally completed exchange at every Spyker server and one initiated
round somewhere in the mesh, evidenced by the last periodic snapshot. Each server
must have accepted at least one contribution per peer. Token circulation or
positive accuracy alone cannot satisfy this check. A proof failure retains the
raw results but marks the campaign interrupted. This evidence establishes that
exchange occurred, not model consensus, convergence, or superiority.

`sync_rounds_initiated` counts initiations by that actor,
`sync_rounds_completed` counts rounds in which that actor accepted all distinct
peer contributions, and `peer_models_aggregated` counts accepted contributions.
These are local cumulative counters, not a global barrier or a count of independent
observations. Duplicate messages in the retained cache do not increase them.
Saved v1 plans without these optional controls remain readable, retain their
original defaults and do not acquire fabricated exchange evidence. Such plans
cannot approve a new measurement profile with different algorithm controls.

The shared virtual horizon does **not** imply equal numbers of updates or equal
wall-clock training work. Report that distinction, both time scales and Spyker's
individual server metrics. Its server macro mean describes separate models;
HierFL's coordinator metric describes one model. Three seeds provide an initial
variability estimate, not a guarantee of statistical power.

Calibration is required before a measurement campaign. The CLI's `--calibrate`
option selects the first scenario and seed, producing two jobs, one per architecture.
Choose the final horizon and interval from that pilot, document the decision,
then freeze the configuration before collecting the reported campaign. Every
Spyker evaluation tests three models sequentially. Even a short virtual duration
can involve substantial CPU training and full test-set evaluation.

With 50,000 CIFAR-10 training examples, six IID partitions and the local 80/20
split, each client trains on approximately 6,667 examples. At compute factor 500,
one local epoch represents about 13.3 virtual seconds, before communication. A
60-second run therefore allows only a few updates per client; whether it answers
the research question must be decided from actual progress and metric traces.

## Network sensitivity

`experiments/network-sensitivity.json` retains the client placements, seeds and
training settings but changes the network profile:

| Region | Client upload/download (Mbps) | Server upload/download (Mbps) | Client latency (ms) |
| --- | --- | --- | --- |
| 1 | 100 / 100 | 100 / 100 | 10 |
| 2 | 10 / 20 | 25 / 25 | 40 |
| 3 | 2 / 5 | 10 / 10 | 100 |

Server-link latency remains 100 ms; jitter and loss remain zero. The coordinator
retains 100 Mbps in both configurations. Regional profiles are applied identically
to matching server/client groups in both engines. This compares complete network
profiles; it does not isolate the effects of bandwidth and latency individually.

The current float32 model payload is 2,481,448 bytes. Its serialization alone
takes about 0.199 s at 100 Mbps and 9.926 s at 2 Mbps, excluding latency and protocol
messages. The homogeneous network is active but comparatively fast; it cannot
establish behavior under heterogeneous links. The second configuration makes
that a separate experiment rather than silently changing the placement baseline.
It needs its own calibration pair with matching network/training conditions.
For direct comparisons between network profiles, select a common final horizon
and evaluation interval and update both measurement configurations together.
Neither profile models contention, metadata overhead or every network effect.

## Preview without starting jobs

From the repository root, with Git installed and the locked CPU development environment:

```bash
uv run --no-sync python -m fedsim.experiments.campaign plan --config experiments/local-pilot.json --calibrate --output var/campaigns/calibration-plan
```

This writes `plan.json` and makes no HTTP requests. Existing output directories
are refused. Execute this exact plan with `run --plan`; its campaign ID, node IDs,
checkpoint paths and archived plan bytes are preserved. The plan is checked against
its embedded configuration and the current generator before any submission.
An edited/incompatible plan is rejected. Direct `run --config` remains available
and generates a fresh ID. A saved plan is not a resume mechanism: do not execute
it twice, because it references the same backend checkpoint paths and node IDs.

## Record the backend environment

Commit the reviewed code and configuration, then rebuild and start the backend
from that revision. Use a dedicated instance with no unrelated jobs or editor
changes during measurement. Set CPU and memory limits in the deployment and
record them; the campaign client does not impose Ray cluster limits.
Use the CPU backend and worker images for this design so final checkpoint
evaluation also runs on CPU.

Create a local JSON file with these fields, replacing all placeholders:

```json
{
  "source_commit": "<full backend Git commit>",
  "uv_lock_sha256": "<SHA-256 of the backend uv.lock>",
  "runtime_versions": {
    "python": "<backend version>",
    "torch": "<backend version>",
    "ray": "<backend version>",
    "container_image": "<backend and worker image digests, if used>"
  },
  "hardware": {
    "cpu": "<model>",
    "ram": "<installed memory>",
    "os": "<backend OS and version>"
  },
  "resource_budget": {
    "cpus": "<Ray CPUs and container CPU quota>",
    "memory": "<container memory limit>",
    "gpu": "disabled"
  },
  "dataset_provenance": {
    "training": "<Hugging Face dataset revision and content/fingerprint evidence>",
    "evaluation": "<torchvision dataset archive checksums>",
    "partitioning": "fedsim-iid-v1; six partitions; per-case seed; ordered graph nodes"
  }
}
```

The runner checks that the declared backend commit and lock checksum match the
clean local repository and archives that commit's tracked source. It cannot
inspect the running server's actual image, hardware or dataset. These fields are
operator declarations; collect them from the backend and workers, not from a
different client environment. Record additional dataset/partition evidence there
when available. This tool does not export dataset rows or prove exact replay.

## Execute and preserve results

With the default Compose stack available at `localhost:8088`:

```bash
uv run --no-sync python -m fedsim.experiments.campaign run --plan var/campaigns/calibration-plan/plan.json --output var/campaigns/calibration-run --environment var/backend-environment.json
```

After inspecting the calibration traces, create `var/calibration-review.json`:

```json
{
  "pilot_archive": "campaigns/calibration-run",
  "run_time_limit": 60,
  "eval_interval": 20,
  "rationale": "Replace with the observed progress, evaluation cost and reason for the selected horizon and interval."
}
```

The values above illustrate the format, not a recommendation to keep the short
horizon. Update the measurement configuration to the selected values and commit
it before execution. If too little progress is visible, extend calibration first.
`pilot_archive` is relative to the review file's directory (or absolute). The
runner verifies its checksums, completed calibration pair, raw evaluation evidence,
frozen definitions and checkpoint mapping. Training, network and Spyker algorithm
controls must match;
the selected horizon/interval must match the measurement configuration. The
written rationale remains a human judgment, not an automated convergence test.
If simulation code, dataset or resource conditions change, recalibrate.

Preview and execute the reviewed measurement plan:

```bash
uv run --no-sync python -m fedsim.experiments.campaign plan --config experiments/local-pilot.json --output var/campaigns/measurement-plan
uv run --no-sync python -m fedsim.experiments.campaign run --plan var/campaigns/measurement-plan/plan.json --output var/campaigns/measurement-run --environment var/backend-environment.json --calibration-review var/calibration-review.json
```

Measurement runs without a completed calibration review are rejected before
creating graphs or jobs. Repeat the sequence using `network-sensitivity.json`
and separate output/review paths for the heterogeneous network campaign. Each
full configuration has twelve jobs; each calibration pair has two. Do not launch
both full campaigns before measuring the local runtime and fixing their scope.

The runner checks the backend's OpenAPI schema for the new evaluation-export
endpoint before creating any graphs or jobs. The default shared
mount maps `/var/lib/fedsim/models` to local `var/models`. Override `--api-url`,
`--checkpoint-root` and `--backend-model-root` for other POSIX backend paths and
shared mounts. The client requires access to the resulting checkpoint files;
it does not download weights through HTTP.

The archive contains the plan, declared environment, source ZIP, execution journal
and checksums. Measurement archives also retain the calibration decision, resolved
pilot path and checksum-manifest hash. Preserve that referenced pilot archive
alongside the measurement archive. Each case retains the graph, submitted request, acceptance response,
checksummed frozen definition, final response, summary CSV, unrounded periodic
points with server details, and copies of the checkpoints with a server/file map.
The export follows exact repetition IDs recorded in the job result, including
single-architecture child runs; it does not use a prefix search. Captured topology
contents and settings are checked against the plan before polling continues.

Jobs run sequentially. The runner stops on failure, missing evaluation evidence,
checkpoint-copy failure, or a 24-hour per-job polling timeout. Interruptions retain
the execution journal and checksums of available artifacts. There is no automatic
submission retry, resume, cancellation or graph deletion. Transport failures on
GET requests are retried at most twice; HTTP error responses are not retried.
Atomic JSON replacement retries transient permission failures for up to eight
seconds, accommodating Windows readers and bind mounts. Persistent failures still
stop collection; this does not retry an HTTP submission.
A timed-out submission may already
have been accepted: inspect the backend before starting another campaign. Stopping
the client does not stop its backend job. Created graphs and backend files remain
available for inspection.

Only a campaign with `execution.json` status `completed` has passed all collection
checks. Preserve the original archive before deriving tables or figures. Evaluation
snapshots remain per-actor, not globally simultaneous; asynchronous event order
can still vary. Historical paper measurements remain a separate evidence set.
