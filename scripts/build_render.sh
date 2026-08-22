#!/usr/bin/env bash

set -eu

# Compatibility helper for local/CI Python dependency verification only.
# Canonical Render deployment builds Dockerfile; this script is not a Render
# build command and intentionally does not install browsers or OS packages.
python -m pip install --disable-pip-version-check -r requirements.txt
python -m pip check

python -m compileall -q \
  main.py \
  config \
  core \
  helpers \
  pipelines \
  plugins \
  services \
  storage \
  tests \
  tools
