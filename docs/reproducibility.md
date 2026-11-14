# Reproducibility

## Historical source

Commit `7d9d5bd07d80edc613286f3effec7256cac1fd6b` preserves the imported project
before the repository reorganization. It is a historical source reference;
the exact commit and installed environment used for each manuscript experiment
have not been established.

The original dependency declarations can be inspected without changing the
working tree:

```bash
git show 7d9d5bd:code/requirements.txt
git show 7d9d5bd:code/framework/impl/pyproject.toml
```

Those declarations include lower bounds such as `torch>=2.7.1`, rather than a
complete environment lock. Installing that commit today does not necessarily
reconstruct the original environment. Record recovered environment information
with its source, and label reconstructed environments as reconstructed.

## Current development environment

The current lockfiles describe the maintained software environment. They are not
a record of the historical experiment environment. Installation instructions
are in [Development](development.md).

The automated tests and CPU integration checks exercise application behavior,
dataset partitioning, model training on synthetic images, and runtime
integration. They do not reproduce the manuscript's convergence or performance
measurements. Historical measurements must remain associated with the original
software and hardware conditions; comparisons after a runtime update require
new measurements.

## Recording new experiments

New API submissions freeze the validated topology and normalized requested
settings at submission time. Later graph edits or deletion cannot change a
queued run. Download `GET /runs/{run_id}/export/definition` and retain its
SHA-256 checksum with the results. The same definition is included in final
run metadata and the CSV export's `metadata_json` field. Node and edge list
order is preserved; JSON object key order does not change the checksum.

Both-mode GPU scaling leaves the requested definition unchanged. Each
repetition records the settings passed to its controller under
`runs[].simulation_settings` (inside `results_by_architecture` for Both mode).
These controller inputs do not establish the exact CPU/GPU allocation or
event-order determinism. A definition checksum alone is insufficient to
reproduce the complete experiment.

## Randomness and remaining limits

An explicit run seed initializes the same CNN weights in both engines using a
private CPU generator. Concurrent controllers do not reseed global Python,
NumPy, or PyTorch generators. Model initialization retains the previous layer
initialization rule; it now works independently of other controllers' activity.

Virtual network and training-time noise use actor-owned generators with the
versioned `fedsim-rng-v1` seed derivation. Server streams depend on the run seed,
server ID, and destination ID. Client streams depend on the existing client
seed (run seed plus partition index) and separate training, download, and upload
names. Network streams also include the remote server ID. Drawing from one
stream cannot advance another stream. Run IDs do not affect these seeds.

These changes alter virtual noise sequences relative to earlier code. Record
the source revision with every new experiment. Omitting the seed remains
nondeterministic; a global `torch.manual_seed()` call no longer controls `Net`
initialization. Use `Net(seed=...)` explicitly.
Exact weight equality is checked within the same platform and PyTorch build;
the same seed does not guarantee bitwise equality across operating systems.

Network transfer timing now counts payload bytes against decimal Mbps. Earlier
MiB-to-Mbps mixing underestimated the serialization component. This correction
changes virtual event times; retain the source revision with timing results.

These controls isolate model initialization and the current engines' simulated
noise, not the complete experiment. Callback completion order can still change
event tie-breaking and asynchronous aggregation. Exact replay and future
stochastic model or augmentation operations need separate controls and validation.

## Data assignments

Logical clients retain private loader and RNG state inside a bounded set of
CPU workers, rather than allocating a Ray process per client. Workers reuse
one CNN because each call loads complete incoming parameters and recreates
the optimizer. They also resolve an execution context once per worker,
avoiding a separate copy of the complete client registry for every client.
Tests compare interleaved clients against independent client instances using
actual SGD, exact weight equality, noisy timing and loader-generator states.
This checks client semantics within the same software environment; it does
not establish identical whole-run event order. Physical scheduling and wall
clock measurements change, so record the new revision and rerun performance
comparisons. Client state still grows with population; measure actual memory
and supported client counts rather than extrapolating from worker count.

Pending model versions also consume memory independently of worker replicas.
Record Ray's object-store allocation and the container's shared-memory mount
alongside its RAM limit. Provision shared memory for the chosen object store;
the number of live input and returned-model versions depends on the execution
policy, so one model per client is not a fixed storage bound.

The `fedsim-iid-v1` definition uses the normalized dataset ID, total partition
count, and common run seed (42 when omitted). Flower Datasets now receives this
seed explicitly for source-data shuffling. Each IID partition receives a
deterministic 80/20 train/test split using
`derive_seed(run_seed, "data", "split", str(partition_index))`. Training-loader
shuffle seeds remain separate and do not change train/test membership.

Both engines share a job-owned provider when these definitions match. Splits
are lazy and cached per partition. Matching dataset contents, partition counts,
and run seeds produces the same assignment by partition index, independently
of client request order. Captured graph list order determines how indices map
to individual clients; matching seeds alone do not ensure comparable topology
assignments or equal training work.

These controls change data assignments relative to older code, which used
Flower's default global shuffle seed and client-specific split seeds. Record
the source revision and the actual dataset revision/content with new results.
Dataset revisions and row assignments are not automatically archived. Direct
`load_data` callers must use `partition_seed` to control data membership; `seed`
now controls only training-loader shuffle.

## Evaluation scope

New Spyker evaluations report every server and an equal-weight mean of its
metrics (`server_macro_mean`). Final evaluations include `per_server` values;
periodic points retain them inside `server_stats`, together with model ages
and snapshot times. Each set of server models uses one common test loader.
Per-server actor snapshots do not establish deterministic global event order
or an atomic global snapshot.

Evaluation work grows with the number of servers: each checkpoint is tested
sequentially in one admitted evaluation task. Choose the periodic interval
for the available CPU budget and record it with the campaign settings;
evaluation can otherwise dominate wall-clock time.

Each server checkpoint remains a separate model. `server_checkpoints` and
`primary_server_id` identify its file; the requested output file remains the
first server's checkpoint for compatibility. Use the complete per-repetition
result JSON in the CSV export, rather than interpreting that one file as a
model whose predictions produce the server-mean metric.

The evaluation helper now computes loss per evaluated example, including a
partial last batch. Earlier code averaged batch means equally. This can change
reported loss even for the same checkpoint. Server means likewise differ in
meaning from the previous first-server-only path. Keep historical metrics as
recorded and retain code revision and evaluation scope with new measurements.
Historical records without scope metadata retain their recorded metrics;
no per-server results or aggregation scope are reconstructed from them.

## Experiment campaign records

Freeze the software environment for each experiment campaign. Record:

- the source commit, lockfile checksums, and container image digests;
- runtime versions, hardware, and allocated CPU/GPU resources;
- topology snapshots, training settings, and random seeds;
- dataset revisions, preprocessing, and client partitions;
- raw metrics, run identifiers, and commands used to generate figures.

Use matched client counts and training budgets when comparing architectures,
repeat runs with multiple seeds, and report variability. Keep results from
different environments distinguishable and preserve the original outputs.

The [local comparison campaign](experiments.md) supplies paired configurations,
sequential execution and an archive format for new measurements.

## Failed runs and Ray references

An extended Spyker run at revision `20d5070` with Ray 2.60 encountered a
`ReferenceCountingAssertionError` during peer-model delivery, without an OOM
kill. The precise trigger has not been isolated. Separate direct and nested
reference-transport diagnostics did not reproduce it; they do not establish
failure-free execution of the full engine.

Runtime exceptions propagate to a failed job, and the campaign runner stops.
Preserve its frozen definition, error, partial results and original Ray logs.
Keep previously completed cases only with their full checksum, identity,
checkpoint and protocol checks. Run any unfinished case again from its initial
state in a fresh output directory with the same frozen inputs and runtime;
record the separate execution segments. A partial failed model must not be
reported as a completed result or substituted into a paired comparison.

For a separate reproduction attempt, set `RAY_record_ref_creation_sites=1`
before starting Ray to capture object-reference creation sites. This adds
diagnostic context; restarting or enabling the flag does not establish a fix.
