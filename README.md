# local-file-search-mcp

MCP server for full-text search with fuzzy matching in local files.

## Installation

Install the package in editable mode:

```bash
pip install -e .
```

## Usage

Run the server with a search path argument:

```bash
local-file-search-mcp <search_path>
```

Example:
```bash
local-file-search-mcp "C:/Users/pingk/OneDrive/Desktop/knowledge"
```

## Configuration

Add to your MCP settings:

```json
"mcpServers": {
    "local-search": {
      "command": "local-file-search-mcp",
      "args": [
        "C:/Users/pingk/OneDrive/Desktop/knowledge"
      ]
    }
}
```

## Tools

- **full_text_search**: Search for text in files with fuzzy matching
  - `query` (required): Search query
  - `offset` (optional): Skip first N matches (default: 0)
  - `threshold` (optional): Similarity threshold 0-100 (default: 80)