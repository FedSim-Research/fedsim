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

This isolates model initialization and the current engines' simulated noise,
not the complete experiment. Client data-loader shuffle generators remain
explicitly seeded, but dataset partitioning and train/test splits retain their
existing behavior. Shared seeds do not establish matched data assignments.
Callback completion order can still change event tie-breaking and asynchronous
aggregation. Exact replay, dataset revisions, and future stochastic model or
augmentation operations need separate controls and validation.

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
