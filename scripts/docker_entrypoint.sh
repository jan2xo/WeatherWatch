#!/bin/sh

set -eu

# Render mounts the persistent disk after the image is built, so the mount can
# hide Dockerfile ownership. Limit privileged work to the one canonical mount;
# never recursively chown an operator-controlled environment path.
runtime_disk=/var/data/weatherwatch
mkdir -p "${runtime_disk}"
chown -R pwuser:pwuser "${runtime_disk}"

# Replace PID 1 with the unprivileged application process so SIGTERM reaches
# WeatherWatch directly and its bounded shutdown contract remains intact.
exec setpriv --reuid=pwuser --regid=pwuser --init-groups -- "$@"
