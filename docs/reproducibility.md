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
resolve random-stream isolation and event-order determinism. A definition
checksum alone is insufficient to reproduce the complete experiment.

Freeze the software environment for each experiment campaign. Record:

- the source commit, lockfile checksums, and container image digests;
- runtime versions, hardware, and allocated CPU/GPU resources;
- topology snapshots, training settings, and random seeds;
- dataset revisions, preprocessing, and client partitions;
- raw metrics, run identifiers, and commands used to generate figures.

Use matched client counts and training budgets when comparing architectures,
repeat runs with multiple seeds, and report variability. Keep results from
different environments distinguishable and preserve the original outputs.
