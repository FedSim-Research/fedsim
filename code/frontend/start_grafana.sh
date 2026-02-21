#!/bin/bash


FRONTEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"


grafana server \
  --homepath=/usr/share/grafana \
  --config=grafana.ini \
  --configOverrides "cfg:paths.data=$FRONTEND_DIR/grafana-data cfg:paths.logs=$FRONTEND_DIR/grafana-logs cfg:paths.plugins=$FRONTEND_DIR/grafana-plugins"
