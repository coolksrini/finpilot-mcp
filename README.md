# FinPilot MCP Server

**AI Financial Co-Pilot for Claude Desktop and VS Code**

MCP server providing financial analysis capabilities through the Model Context Protocol.
Requests flow through the FinPilot Auth Service, which validates credentials and routes
to the private orchestrator.

## Features

- Native integration with Claude Desktop and VS Code
- Zero-config guest mode — stateless calculation tools work without an account
- Authenticated mode — full personal finance tools (credit reports, portfolio, LAMF)
- Cloud-powered analysis (no local computation required)

## Claude Desktop Setup

Edit Claude Desktop config:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

### Zero-config (guest mode — stateless tools only)

No account or API key needed. Stateless calculation tools (loan optimizer, APR
calculator, etc.) work out of the box. Personal finance tools (credit report analysis,
portfolio) require sign-in.

```json
{
  "mcpServers": {
    "finpilot": {
      "command": "uv",
      "args": ["run", "finpilot-mcp"]
    }
  }
}
```

### Authenticated (full access)

Generate an `fp_` API key from [myfinpilot.io](https://myfinpilot.io) → Settings →
API Tokens, then add it here:

```json
{
  "mcpServers": {
    "finpilot": {
      "command": "uv",
      "args": ["run", "finpilot-mcp"],
      "env": {
        "FINPILOT_GATEWAY_URL": "https://<auth-service>.run.app",
        "FINPILOT_API_KEY": "fp_your_token_here"
      }
    }
  }
}
```

Restart Claude Desktop after editing.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `FINPILOT_GATEWAY_URL` | `http://localhost:8080` | Auth Service URL |
| `FINPILOT_API_KEY` | _(none)_ | API key (`fp_...`). Omit for guest mode. |

## Command Line Usage

```bash
# Guest mode (zero-config)
uv run finpilot-mcp

# Authenticated mode
FINPILOT_GATEWAY_URL=https://<auth-service>.run.app \
FINPILOT_API_KEY=fp_your_token_here \
uv run finpilot-mcp

# HTTP mode (for local testing)
uv run finpilot-mcp --mode http --port 8002
```

**CLI Options:**
- `--mode` — Transport mode: `stdio` (default) or `http`
- `--host` — HTTP server host (default: 0.0.0.0)
- `--port` — HTTP server port (default: 8002)
- `--reload` — Enable auto-reload for development

## Available Tools

### Credit Analysis
- `analyze_credit_report` — Analyze CIBIL/Experian/Equifax reports
- `get_credit_health` — Credit health summary

### Portfolio Analysis
- `analyze_portfolio` — Analyze CAS statements or portfolio data

### Loan Optimization
- `optimize_loans` — LAMF and refinancing recommendations

### Financial Planning
- `create_financial_plan` — Goal-based financial planning

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
│  - Optional FINPILOT_API_KEY auth   │
│  - No business logic                │
└────────────┬────────────────────────┘
             │ HTTPS + optional Bearer token
             ▼
┌─────────────────────────────────────┐
│  Auth Service (Public entry point)  │
│  - Token validation / guest assign  │
│  - In-process rate limiting         │
│  - Injects X-User-* headers         │
└────────────┬────────────────────────┘
             │ SA identity token (private)
             ▼
┌─────────────────────────────────────┐
│  Orchestrator (Private Cloud Run)   │
│  - Multi-agent ADK orchestration    │
│  - Business logic & algorithms      │
└─────────────────────────────────────┘
```

## Development

```bash
# Install dependencies
cd backend/finpilot-mcp
uv sync

# Run in HTTP mode for local testing
FINPILOT_GATEWAY_URL=http://localhost:8080 \
uv run finpilot-mcp --mode http --port 8002

# Run tests
uv run pytest
```

## Security

- All API communication over HTTPS
- API keys via environment variables only
- No sensitive data stored locally
- Secrets never in CLI arguments or code

## License

MIT License
