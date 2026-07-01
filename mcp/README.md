# ThinkGraph MCP Server

Exposes ThinkGraph as a [Model Context Protocol](https://modelcontextprotocol.io) server with 7 tools.

## Quick start

```bash
python thinkgraph_mcp.py
```

This starts a JSON-RPC 2.0 server over stdio. Configure it in your MCP client:

### Claude Desktop (claude_desktop_config.json)

```json
{
  "mcpServers": {
    "thinkgraph": {
      "command": "python",
      "args": ["/absolute/path/to/mcp/thinkgraph_mcp.py"]
    }
  }
}
```

### Cursor

Add to your MCP settings:
```json
{
  "mcpServers": {
    "thinkgraph": {
      "command": "python",
      "args": ["/absolute/path/to/mcp/thinkgraph_mcp.py"]
    }
  }
}
```

## Available tools

| Tool | Description |
|---|---|
| `thinkgraph_triage` | Classify prompt complexity (trivial/single-hop/multi-hop/planning/creative) |
| `thinkgraph_validate_dag` | Validate a DAG, check cycles, get execution batches |
| `thinkgraph_vote` | Self-consistency voting — pick most consistent LLM response |
| `thinkgraph_web_search` | DuckDuckGo HTML search (no API key) |
| `thinkgraph_cache_get` | Look up cached resolved facts |
| `thinkgraph_cache_set` | Store resolved facts with confidence |
| `thinkgraph_tokens` | Estimate token count |

## Protocol

The server implements JSON-RPC 2.0 over stdio:
- `initialize` → announces server capabilities
- `tools/list` → returns all available tools
- `tools/call` → executes a named tool with arguments

All responses are JSON. Errors use standard JSON-RPC error codes.

## Requirements

- Python 3.8+
- stdlib only (no external dependencies)
- No API keys required