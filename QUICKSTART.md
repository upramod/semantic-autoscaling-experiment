# Quick Start

Run these commands from a shell with Docker, kind, kubectl, Helm, and Python available.

```bash
./scripts/preflight.sh
./scripts/build_images.sh
./scripts/kind_create.sh
./scripts/kind_load_images.sh
./scripts/install_keda.sh
./scripts/deploy.sh
```

First measured pair:

```bash
DURATION=180 ./scripts/run_experiment.sh baseline composition 1
DURATION=180 ./scripts/run_experiment.sh semantic composition 1
```

Inspect:

```bash
cat results/baseline_composition_seed1/summary.json
cat results/semantic_composition_seed1/summary.json
```

Then run repeated trials:

```bash
SEEDS="1 2 3 4 5 6 7 8 9 10" DURATION=180 ./scripts/run_matrix.sh
```

The file needed for the paper is then:

```text
results/aggregate.csv
```

If running on Windows, use WSL2 with Docker Desktop integration or another shell that can execute the Bash scripts. `kubectl`, Helm, and kind should all point at the same Docker/Kubernetes environment.
