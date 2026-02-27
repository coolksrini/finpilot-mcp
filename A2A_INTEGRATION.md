# A2A Integration Guide

## Overview

The finpilot-mcp server communicates with the ADK orchestrator using the A2A (Agent-to-Agent) protocol via JSON-RPC 2.0.

## Architecture

```
MCP Client (finpilot-mcp)
    ↓ JSON-RPC 2.0
Orchestrator (ADK Agent)
    ↓ MCP Protocol
mcp-core (Internal Tools)
```

## A2A JSON-RPC 2.0 Format

### Request Format

```json
{
  "jsonrpc": "2.0",
  "method": "message/send",
  "params": {
    "message": {
      "role": "user",
      "parts": [
        {
          "type": "text",
          "text": "{\"ui_action\": \"GET_CREDIT_HEALTH\", \"data\": {\"user_id\": \"123\"}}"
        }
      ],
      "messageId": "unique-message-id"
    }
  },
  "id": 1
}
```

### Response Format

```json
{
  "id": 1,
  "jsonrpc": "2.0",
  "result": {
    "artifacts": [
      {
        "artifactId": "uuid",
        "parts": [
          {
            "kind": "text",
            "text": "{\"status\": \"success\", \"data\": {...}}"
          }
        ]
      }
    ],
    "contextId": "uuid",
    "history": [...],
    "id": "task-uuid",
    "kind": "task",
    "status": {
      "state": "completed",
      "timestamp": "2026-02-18T10:03:44.583628+00:00"
    }
  }
}
```

## Key Insights

1. **No A2A SDK needed**: Simple HTTP POST with JSON-RPC format
2. **Endpoint**: Root path `/` (not `/jsonrpc`)
3. **Method**: Always `"message/send"`
4. **Message format**: JSON string in `parts[0].text`
5. **Response extraction**: Parse `result.artifacts[0].parts[0].text` as JSON

## Supported UI Actions

- `EXTRACT_CREDIT_REPORT` - Extract credit bureau data
- `EXTRACT_SECURITIES` - Parse CAS file (alias: `ANALYZE_PORTFOLIO`)
- `GET_CREDIT_HEALTH` - Get user's credit health summary
- `OPTIMIZE_LOANS` - Get loan optimization recommendations
- `CREATE_FINANCIAL_PLAN` - Generate financial plan

## Testing

### Local Development

```bash
# Start services
./run-local-dev.sh

# Test directly
curl -X POST http://localhost:3000/ \
  -H "Content-Type: application/json" \
  -d @test_message.json
```

### Python Client

```python
from finpilot_mcp.orchestrator_client import orchestrator_client

result = await orchestrator_client.get_credit_health(user_id="test")
```

## Configuration

Environment variables:
- `FINPILOT_ORCHESTRATOR_URL`: Orchestrator endpoint (default: http://localhost:3000)
- `ENVIRONMENT`: Set to `development` for local dev mode

## References

- [Google ADK Documentation](https://cloud.google.com/vertex-ai/docs/agent-builder)
- [A2A Protocol Spec](https://github.com/google/adk)
- EquiSave reference: `references/EquiSave/frontend/lib/services/agent_service.dart`
