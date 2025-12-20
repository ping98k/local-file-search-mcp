# local-file-search-mcp

MCP server for indexed full-text search in local files using Tantivy. Supports fuzzy matching, wildcards, phrases, and boolean operators.

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

### search_file_contents
Search for text in files using indexed full-text search. Fuzzy matching is automatically enabled for single-word queries.

**Parameters:**
- `query` (required): Search query. You can manually write queries with operators:
  - Fuzzy matching: `term~2` (allows 2 character differences)
  - Wildcards: `test*` (prefix matching)
  - Phrases: `"exact phrase"`
  - Boolean: `term1 AND term2`, `term1 OR term2`
- `filePattern` (optional): File glob pattern relative to search path (e.g., '*.py', 'data/**', 'src/**/*.js'). Default searches all files.
- `skip` (optional): Skip first N matches (default: 0)

### read_file_chunk
Read a text chunk from a file around a specific character offset. Returns approximately 1000 characters (100 before and 900 after the offset).

**Parameters:**
- `filePath` (required): File path (relative to search path or absolute)
- `charOffset` (required): Character offset in the file

### list_directory_contents
List files and directories at the specified path. Returns folders and files with sizes.

**Parameters:**
- `path` (optional): Directory path relative to search path (empty or '/' for root)