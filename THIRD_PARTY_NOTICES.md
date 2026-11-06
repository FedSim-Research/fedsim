# Third-party notices

## Flower Datasets

FedSim uses [Flower Datasets](https://pypi.org/project/flwr-datasets/0.6.1/)
(`flwr-datasets`, version 0.6.1) for dataset loading and IID partitioning.
Its source is maintained in the
[Flower repository](https://github.com/flwrlabs/flower/tree/main/datasets).

Flower Datasets is licensed under Apache-2.0. The IID partitioner carries
`Copyright 2023 Flower Labs GmbH. All Rights Reserved.` The license text is
included in [LICENSE](LICENSE). Upstream source files retain their copyright and license
headers; the 0.6.1 wheel does not bundle a separate full license text, so this
repository includes it explicitly.

FedSim depends on the published package and does not vendor its source. Its
simulation engines use their own scheduler and aggregation strategies; the
Flower framework and Flower Simulation Runtime are not required.

Redistributions of covered code or binaries must retain the license and applicable
copyright and attribution notices, identify modifications to covered files, and
preserve applicable upstream `NOTICE` contents when supplied. See
[section 4 of Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0).

These notices concern third-party material. Other Python, npm, container-image,
and dataset dependencies retain their respective terms.

## Flower PyTorch examples

The local training and evaluation helpers in `src/fedsim/learning.py` follow the
[Flower PyTorch quickstart](https://github.com/flwrlabs/flower/tree/v1.26.0/examples/quickstart-pytorch),
published under Apache-2.0 by the Flower contributors. FedSim modifies the model,
data loading, label handling, and training-strategy integration. This attribution
also covers adapted example code independently of the `flwr-datasets` dependency.
The applicable license text is included in [LICENSE](LICENSE).

## Frontend distributions

The production Angular build generates `3rdpartylicenses.txt`, which the frontend
container serves alongside the application at `/3rdpartylicenses.txt`. Preserve
this file when redistributing the compiled frontend. It includes dependency
licenses and copyright notices, including those for Angular, PrimeNG Community,
PrimeIcons, ngx-vflow, and Selecto. The installed PrimeNG version is a Community
release (21.1.10), with MIT-licensed themes and PrimeIcons. The separate upstream
LTS terms apply to versions with an `-lts` suffix. PrimeNG 22 and the newer PrimeUI
packages use different terms and are not included in this dependency set.

## Python and container distributions

Python dependencies are installed as published distributions, including their
bundled license and notice files. Preserve those files when redistributing the
Python environment or container image. Base images and bundled components retain
their own terms; this document is not a complete bill of materials.

The API images also include [uv 0.13.7](https://github.com/astral-sh/uv/tree/0.13.7),
copyright (c) 2025 Astral Software Inc. uv is dual-licensed under MIT or Apache-2.0;
FedSim redistributes it under
[Apache-2.0](https://github.com/astral-sh/uv/blob/0.13.7/LICENSE-APACHE), whose full
text is included in [LICENSE](LICENSE).

Compose references the following separate upstream services:

| Service | Upstream license |
| --- | --- |
| Grafana | [AGPL-3.0](https://github.com/grafana/grafana/blob/main/LICENSE) |
| Loki | [AGPL-3.0](https://github.com/grafana/loki/blob/main/LICENSE) |
| Alloy | [Apache-2.0](https://github.com/grafana/alloy/blob/main/LICENSE) |
| Prometheus | [Apache-2.0](https://github.com/prometheus/prometheus/blob/main/LICENSE) |
| Nginx | [BSD-style license](https://github.com/nginx/nginx/blob/master/LICENSE) |

FedSim's Apache-2.0 license does not relicense these services. Preserve their
license notices and follow their source-distribution obligations when
redistributing or modifying the upstream components.

## Datasets

Datasets are downloaded at runtime and are not included in this repository.
Their usage and redistribution terms are separate from FedSim's software license.
