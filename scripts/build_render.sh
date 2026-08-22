#!/usr/bin/env bash

set -eu

python -m pip install --disable-pip-version-check -r requirements.txt
python -m pip check

# The Python package does not include a browser binary or its Linux shared
# libraries. Keep this explicit so a managed build fails instead of producing
# a release that can start but cannot capture WINDY.
python -m playwright install --with-deps chromium

python -m compileall -q \
  main.py \
  config \
  core \
  helpers \
  pipelines \
  plugins \
  services \
  storage
