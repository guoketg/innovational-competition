#!/bin/sh
cd /opt/edu-ta || exit 1
export COMPOSE_PARALLEL_LIMIT=1
echo "=== REBUILD START $(date) ==="
docker compose build student-backend student-frontend
echo "build_exit=$?"
docker compose up -d student-backend student-frontend
echo "up_exit=$?"
echo "=== REBUILD DONE $(date) ==="
