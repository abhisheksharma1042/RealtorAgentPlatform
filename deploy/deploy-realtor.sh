#!/usr/bin/env bash
# Redeploy the realtor stack: pull latest, rebuild, restart, prune old images.
# Convention: this script is copied to ~/deploy-realtor.sh on the VPS.
set -euo pipefail

cd /opt/RealtorAgentPlatform
git pull --ff-only
docker compose up -d --build
docker image prune -f
docker compose ps
