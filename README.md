# FinPilot MCP Server

**AI Financial Co-Pilot for Claude Desktop and VS Code**

MCP server providing financial analysis capabilities through the Model Context Protocol.

## Features

- 🔌 Native integration with Claude Desktop and VS Code
- ⚡ Cloud-powered analysis (no local computation required)
- 🔒 Secure API key authentication
- 🚀 Easy setup with `uvx` or `pip`

## Installation

**Using uvx (recommended - no installation needed):**

```bash
uvx finpilot-mcp --mode stdio
```

**Using pip:**

```bash
pip install finpilot-mcp
```

## Configuration for Claude Desktop

1. Get your API key from your FinPilot deployment

2. Edit Claude Desktop config:
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`

**Using uvx:**

```json
{
  "mcpServers": {
    "finpilot": {
      "command": "uvx",
      "args": ["finpilot-mcp", "--mode", "stdio"],
      "env": {
        "FINPILOT_API_KEY": "your-api-key-here",
        "FINPILOT_API_GATEWAY_URL": "https://your-deployment.example.com"
      }
    }
  }
}
```

**Using pip:**

```json
{
  "mcpServers": {
    "finpilot": {
      "command": "python",
      "args": ["-m", "finpilot_mcp.server", "--mode", "stdio"],
      "env": {
        "FINPILOT_API_KEY": "your-api-key-here",
        "FINPILOT_API_GATEWAY_URL": "https://your-deployment.example.com"
      }
    }
  }
}
```

3. Restart Claude Desktop

## Environment Variables

**Required:**
- `FINPILOT_API_KEY` - Your API key
- `FINPILOT_API_GATEWAY_URL` - Your FinPilot API Gateway URL

**Optional:**
- `ENVIRONMENT` - `production`, `staging`, or `development` (default: production)

## Command Line Usage

```bash
# STDIO mode (for Claude Desktop)
FINPILOT_API_KEY=your-key \
FINPILOT_API_GATEWAY_URL=https://api.example.com \
python -m finpilot_mcp.server --mode stdio

# HTTP mode (for testing)
FINPILOT_API_KEY=your-key \
FINPILOT_API_GATEWAY_URL=https://api.example.com \
python -m finpilot_mcp.server --mode http --port 8002

# Local development
FINPILOT_API_KEY=your-key \
python -m finpilot_mcp.server \
  --mode stdio \
  --api-gateway-url http://localhost:8000 \
  --environment development
```

**CLI Options:**
- `--mode` - Transport mode: `stdio` or `http`
- `--host` - HTTP server host (default: 0.0.0.0)
- `--port` - HTTP server port (default: 8002)
- `--api-gateway-url` - Override API Gateway URL
- `--environment` - Override environment
- `--reload` - Enable auto-reload for development

**Security:** Secrets (API keys) must be set via environment variables, never via CLI arguments.

## Available Tools

### Credit Analysis
- `analyze_credit_report` - Analyze CIBIL/Experian/Equifax reports
- `get_credit_health` - Credit health summary

### Portfolio Analysis
- `analyze_portfolio` - Analyze CAS statements or portfolio data

### Loan Optimization
- `optimize_loans` - LAMF and refinancing recommendations

### Financial Planning
- `create_financial_plan` - Goal-based financial planning

## Architecture

```
┌─────────────────────────────────────┐
│  Claude Desktop / VS Code           │
└────────────┬────────────────────────┘
             │ MCP Protocol (STDIO)
             ▼
┌─────────────────────────────────────┐
│  finpilot-mcp (This Package)        │
│  - Lightweight MCP wrapper          │
│  - HTTP client to API Gateway       │
│  - No business logic                │
└────────────┬────────────────────────┘
             │ HTTPS REST API
             ▼
┌─────────────────────────────────────┐
│  FinPilot API Gateway (Backend)     │
│  - Authentication                   │
│  - Multi-Agent Orchestration        │
│  - Business Logic & Algorithms      │
└─────────────────────────────────────┘
```

## Development

```bash
# Clone repository
git clone https://github.com/YOUR_ORG/finpilot-mcp.git
cd finpilot-mcp

# Install dependencies
uv pip install -e ".[dev]"

# Run tests
pytest

# Run in HTTP mode for testing
FINPILOT_API_KEY=test \
FINPILOT_API_GATEWAY_URL=http://localhost:8000 \
python -m finpilot_mcp.server --mode http
```

## Security

- ✅ All API communication over HTTPS
- ✅ API keys via environment variables only
- ✅ No sensitive data stored locally
- ✅ Secrets never in CLI arguments or code

## License

MIT License
