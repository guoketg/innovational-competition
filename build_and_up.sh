#!/bin/sh
# Sequential build then up, with full logging
cd /opt/edu-ta || exit 1
export COMPOSE_PARALLEL_LIMIT=1
echo "=== BUILD START $(date) ==="
docker compose build
echo "build_exit=$?"
echo "=== UP START $(date) ==="
docker compose up -d
echo "up_exit=$?"
echo "=== ALL DONE $(date) ==="
