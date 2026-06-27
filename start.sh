#!/bin/bash
OLLAMA_IP=$(avahi-resolve --name ageix.local 2>/dev/null | awk '{print $2}')

if [ -z "$OLLAMA_IP" ]; then
    echo "ERROR: Could not resolve ageix.local" >&2
    exit 1
fi

echo "Resolved Ollama host to $OLLAMA_IP"
export OLLAMA_BASE_URL="http://${OLLAMA_IP}:11434"

exec uvicorn app:app --reload --port 8000
