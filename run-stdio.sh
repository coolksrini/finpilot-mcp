#!/bin/bash
#
# Start finpilot-mcp in STDIO mode for Claude Desktop
#
# PREREQUISITES:
# - Backend services running (via docker compose -f docker-compose.local.yml up -d)
# - Orchestrator available at http://localhost:3000
#
# USAGE:
#   ./run-stdio.sh
#

set -e

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Set environment for local development
export ENVIRONMENT=development
export FINPILOT_ORCHESTRATOR_URL=http://localhost:3000

# Run finpilot-mcp in stdio mode
if command -v uv &> /dev/null; then
    exec uv run python -m finpilot_mcp.server --mode stdio
else
    exec python3 -m finpilot_mcp.server --mode stdio
fi
