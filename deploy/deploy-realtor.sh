#!/usr/bin/env bash
# Redeploy the realtor stack: pull latest, rebuild, restart, prune old images.
# Convention: this script is copied to ~/deploy-realtor.sh on the VPS.
set -euo pipefail

cd /opt/RealtorAgentPlatform
git pull --ff-only
# --wait makes the exit code mean "running and healthy", not just "started";
# on failure, set -e aborts before the prune so the previous image survives.
docker compose up -d --build --wait
docker image prune -f
docker compose ps
