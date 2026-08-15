#!/bin/bash
set -e

# Run the MCP server in the background on the internal port (8765).
python -m app.mcp.mcp_server &

# Run the public FastAPI backend in the foreground.
# Railway assigns the public port dynamically via $PORT - don't hardcode it.
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
