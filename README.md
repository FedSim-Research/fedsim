# FedSim

**Explore geo-distributed federated learning through interactive network topologies.**

FedSim combines a graph editor with Ray-based simulation engines for hierarchical
and Spyker-inspired asynchronous federated learning. PyTorch clients train real
models while an event scheduler tracks virtual computation and communication time.
Grafana dashboards display evaluation results and runtime metrics.

## Run locally

With Docker and Docker Compose installed, run from the repository root:

```bash
git clone https://github.com/FedSim-Research/fedsim.git
cd fedsim
docker compose up -d --build
```

Open **[localhost:8088](http://localhost:8088)** to edit a topology and submit a run.
The initial build and dataset download require internet access.

The bundled stack is configured for local use. Its database, downloaded datasets,
checkpoints, and evaluation logs are stored in the ignored `var/` directory.

## Research scope

The current implementation uses IID partitions and a fixed CNN, with CIFAR-10 as
the baseline dataset. Training clients run on CPU. The optional GPU deployment
supports evaluation. The accompanying research studies use scoped CIFAR-10
configurations; their results concern those update policies and execution budgets,
rather than a general ranking of federated-learning architectures. Additional
dataset paths, non-IID workloads and physical timing calibration remain unvalidated.

## Documentation

- [Development](docs/development.md): installation, tests, and frontend development.
- [Architecture](docs/architecture.md): simulation engines and component boundaries.
- [Reproducibility](docs/reproducibility.md): historical source and experiment environments.
- [Experiments](docs/experiments.md): plan and archive a small comparison campaign.
- [Operations](docs/operations.md): monitoring, configuration, and GPU deployment.
- [Third-party notices](THIRD_PARTY_NOTICES.md): dependency and source attributions.

## Citation

Use [CITATION.cff](CITATION.cff) to cite the software. Record the source commit
and dependency lockfile with your experiment results.

The accompanying paper, its experiment archives and the analysis scripts that
regenerate its tables and figures are published separately under the reserved
Zenodo DOI **10.5281/zenodo.24245352** (not yet published). They are not part of
this repository.

## License

FedSim is licensed under [Apache-2.0](LICENSE). Third-party components retain
their own licenses; see [Third-party notices](THIRD_PARTY_NOTICES.md).
