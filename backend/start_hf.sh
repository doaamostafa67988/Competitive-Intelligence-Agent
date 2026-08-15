#!/bin/bash
set -e

# Run the MCP server in the background on the internal port (8765).
python -m app.mcp.mcp_server &

# Run the public FastAPI backend in the foreground on HF Spaces' port (7860).
exec uvicorn app.main:app --host 0.0.0.0 --port 7860
