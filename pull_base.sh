#!/bin/sh
# Sequential base image pulls with logging
echo "=== pull python:3.11-slim ==="
docker pull python:3.11-slim
echo "py_exit=$?"
echo "=== pull node:20-alpine ==="
docker pull node:20-alpine
echo "node_exit=$?"
echo "=== ALL PULLS DONE ==="
