# syntax=docker/dockerfile:1

# Playwright requires the Python package release and browser image release to
# match.  requirements.txt pins playwright==1.60.0, so this image is pinned to
# the corresponding official Python image and its verified linux/amd64 digest.
# The image supplies Chromium and its Linux system libraries; pip supplies the
# matching Python package only.
FROM mcr.microsoft.com/playwright/python:v1.60.0-noble@sha256:abf13b369f8829eb45e29df38d6c5221f7e7521649cb5d2de7989c82bdb574ad

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/pwuser \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# Keep dependency installation cacheable and fail the image build if the
# pinned application environment is internally inconsistent.
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --disable-pip-version-check \
        -r requirements.txt \
    && python -m pip check \
    && python -c 'import sys; assert sys.version_info[:2] == (3, 12), sys.version' \
    && test "$(python -c 'import importlib.metadata; print(importlib.metadata.version("playwright"))')" = "1.60.0"

COPY --chown=pwuser:pwuser . .

# The official image provides pwuser. Make repository-regenerable output and
# the future Render mount point writable in the image, then install a tiny
# entrypoint that repairs ownership after Render overlays the persistent disk
# and drops privileges before starting WeatherWatch.
RUN mkdir -p /app/output /var/data/weatherwatch \
    && chown -R pwuser:pwuser /app/output /var/data/weatherwatch \
    && command -v setpriv >/dev/null
COPY --chmod=0755 scripts/docker_entrypoint.sh /usr/local/bin/weatherwatch-entrypoint

USER root

EXPOSE 10000

ENTRYPOINT ["/usr/local/bin/weatherwatch-entrypoint"]
CMD ["python", "-m", "core.service"]
