#!/bin/bash
source ../.venv/bin/activate
ray start --head --metrics-export-port=8080 --include-dashboard=true --dashboard-port=8265 --disable-usage-stats
