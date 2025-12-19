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
local-file-search-mcp <search_path> [--full-path]
```

Options:
- `--full-path`: Use full system paths in output instead of relative paths (default: false)

Example:
```bash
local-file-search-mcp "C:/Users/pingk/OneDrive/Desktop/knowledge"
```

With full paths:
```bash
local-file-search-mcp "C:/Users/pingk/OneDrive/Desktop/knowledge" --full-path
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

With full paths enabled:
```json
"mcpServers": {
    "local-search": {
      "command": "local-file-search-mcp",
      "args": [
        "C:/Users/pingk/OneDrive/Desktop/knowledge",
        "--full-path"
      ]
    }
}
```

## Tools

### search
Search for text in files with fuzzy matching
- `query` (required): Search query
- `filePattern` (optional): File name pattern to search in (e.g., '*.py', 'config.txt'). Default searches all files.
- `skip` (optional): Skip first N matches (default: 0)
- `fullPath` (optional): Use full system path in output instead of relative path (overrides server default)

### read
Read text from a file at a specific offset
- `filePath` (required): File path relative to search path
- `charOffset` (required): Character offset in the file
- `fullPath` (optional): Use full system path in output instead of relative path (overrides server default)

### list
List files and folders in a directory
- `path` (optional): Directory path relative to search path (empty or '/' for root)
- `fullPath` (optional): Use full system path in output instead of relative path (overrides server default)