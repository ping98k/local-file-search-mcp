import re
import sys
import os
from pathlib import Path
import tantivy
from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio
import asyncio


SEARCH_PATH = None
USE_FULL_PATH = False
SEARCH_INDEX = None

server = Server("search-server")

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search",
            description="Search for text in files with fuzzy matching",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "filePattern": {
                        "type": "string",
                        "description": "File name pattern to search in (e.g., '*.py', 'config.txt'). Default searches all files.",
                        "default": "*"
                    },
                    "skip": {
                        "type": "integer",
                        "description": "Skip first N matches",
                        "default": 0
                    },
                    # "threshold": {
                    #     "type": "integer",
                    #     "description": "Similarity threshold (0-100)",
                    #     "default": 80
                    # }

                },
                "required": ["query"]
            }
        ),
        Tool(
            name="read",
            description="Read text from a file at a specific offset",
            inputSchema={
                "type": "object",
                "properties": {
                    "filePath": {
                        "type": "string",
                        "description": "File path (relative to search path or absolute)"
                    },
                    "charOffset": {
                        "type": "integer",
                        "description": "Character offset in the file"
                    }
                },
                "required": ["filePath", "charOffset"]
            }
        ),
        Tool(
            name="list",
            description="list file that you can access",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path relative to search path (empty or '/' for root)",
                        "default": ""
                    }
                },
                "required": []
            }
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "list":
        dir_path = arguments.get("path", "")
        full_path_output = USE_FULL_PATH
        
        search_path = Path(SEARCH_PATH)
        # Remove leading slash if present
        if dir_path.startswith('/'):
            dir_path = dir_path[1:]
        
        if dir_path:
            full_path = search_path / dir_path
        else:
            full_path = search_path
        
        if not full_path.exists():
            return [TextContent(
                type="text",
                text=f"Directory not found: {dir_path or '/'}"
            )]
        
        if not full_path.is_dir():
            return [TextContent(
                type="text",
                text=f"Not a directory: {dir_path or '/'}"
            )]
        
        try:
            items = sorted(full_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            
            folders = []
            files = []
            
            for item in items:
                if full_path_output:
                    display_path = str(item).replace('\\', '/')
                else:
                    relative = item.relative_to(search_path)
                    display_path = '/' + str(relative).replace('\\', '/')
                
                if item.is_dir():
                    folders.append(display_path + '/')
                else:
                    size = item.stat().st_size
                    files.append(f"{display_path} ({size} bytes)")
            
            output = f"Directory: {dir_path or '/'}\n\n"
            
            if folders:
                output += "Folders:\n"
                for folder in folders:
                    output += f"  {folder}\n"
                output += "\n"
            
            if files:
                output += "Files:\n"
                for file in files:
                    output += f"  {file}\n"
            
            if not folders and not files:
                output += "(empty directory)\n"
            
            output += f"\nTotal: {len(folders)} folders, {len(files)} files"
            
            return [TextContent(type="text", text=output)]
            
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"Error listing directory: {e}"
            )]
    
    if name == "read":
        file_path = arguments["filePath"]
        char_offset = arguments["charOffset"]
        full_path_output = USE_FULL_PATH
        
        search_path = Path(SEARCH_PATH)
        
        # Check if path is absolute
        path_obj = Path(file_path)
        if path_obj.is_absolute():
            full_path = path_obj
        else:
            # Remove leading slash if present for relative paths
            if file_path.startswith('/'):
                file_path = file_path[1:]
            full_path = search_path / file_path
        
        if not full_path.exists():
            return [TextContent(
                type="text",
                text=f"File not found: {file_path}"
            )]
        
        try:
            content = full_path.read_text(encoding='utf-8', errors='ignore')
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"Error reading file: {e}"
            )]
        
        start = max(0, char_offset - 100)
        end = min(len(content), char_offset + 500)
        chunk = content[start:end]
        max_range = len(content)
        
        display_path = str(full_path).replace('\\', '/') if full_path_output else file_path
        output = f"File: {display_path}\n"
        output += f"Range: {start}-{end} (offset {char_offset}) [Max: 0-{max_range}]\n"
        output += f"Context:\n{chunk}\n\n\n"
        
        return [TextContent(type="text", text=output)]
    
    if name != "search":
        raise ValueError(f"Unknown tool: {name}")
    
    query = arguments["query"]
    file_pattern = arguments.get("filePattern", "*")
    skip = arguments.get("skip", 0)
    full_path_output = USE_FULL_PATH
    
    search_path = Path(SEARCH_PATH)
    
    if not search_path.exists():
        return [TextContent(
            type="text",
            text=f"Path not found: {SEARCH_PATH}"
        )]
    
    # Build index if not already built
    global SEARCH_INDEX
    if SEARCH_INDEX is None:
        # Schema Definition: path and content fields
        schema_builder = tantivy.SchemaBuilder()
        schema_builder.add_text_field("path", stored=True)
        schema_builder.add_text_field("content", stored=True)
        schema = schema_builder.build()
        
        # In-Memory Index
        SEARCH_INDEX = tantivy.Index(schema, path=None)  # None = in-memory
        writer = SEARCH_INDEX.writer()
        
        # Index all files
        for file_path in search_path.rglob('*'):
            if not file_path.is_file():
                continue
            
            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                if full_path_output:
                    display_path = str(file_path).replace('\\', '/')
                else:
                    display_path = '/' + str(file_path.relative_to(search_path)).replace('\\', '/')
                
                writer.add_document(tantivy.Document(
                    path=[display_path],
                    content=[content]
                ))
            except:
                continue
        
        writer.commit()
    
    # Search the index
    searcher = SEARCH_INDEX.searcher()
    tantivy_query = SEARCH_INDEX.parse_query(query, ["content"])
    
    search_results = searcher.search(tantivy_query, limit=skip + 5).hits
    
    results = []
    for score, doc_address in search_results[skip:]:
        if len(results) >= 5:
            break
        
        doc = searcher.doc(doc_address)
        file_path = doc.get_first("path")
        content = doc.get_first("content")
        
        # Filter by file pattern if needed
        if file_pattern != "*":
            path_obj = Path(file_path.lstrip('/'))
            if not path_obj.match(file_pattern):
                continue
        
        # Find query position in content
        query_lower = query.lower()
        content_lower = content.lower()
        pos = content_lower.find(query_lower)
        
        if pos == -1:
            # If exact match not found, show beginning of file
            pos = 0
        
        chunk_start = max(0, pos - 250)
        chunk_end = min(len(content), pos + len(query) + 250)
        chunk = content[chunk_start:chunk_end]
        
        results.append({
            'file': file_path,
            'position': pos,
            'chunk': chunk
        })
    
    output = f"Total found: {len(search_results)}\n\n"
    for r in results:
        output += f"File: {r['file']}\n"
        output += f"Position: {r['position']}\n"
        output += f"Context:\n{r['chunk']}\n\n\n"
        output += "-"*20+"\n\n\n"
    
    return [TextContent(type="text", text=output)]

def main():
    global SEARCH_PATH, USE_FULL_PATH
    
    # Parse command-line arguments
    args = sys.argv[1:]
    search_path_arg = None
    
    for arg in args:
        if arg == '--full-path':
            USE_FULL_PATH = True
        elif not arg.startswith('--'):
            search_path_arg = arg
    
    # Get search path from command line argument or environment variable
    if search_path_arg:
        SEARCH_PATH = search_path_arg
    else:
        SEARCH_PATH = os.getenv('SEARCH_PATH')
    
    if not SEARCH_PATH:
        print("Error: No search path provided. Set SEARCH_PATH environment variable or pass as argument.", file=sys.stderr)
        print("Usage: python server.py <search_path> [--full-path]", file=sys.stderr)
        sys.exit(1)
    
    async def run():
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options()
            )
    
    asyncio.run(run())

if __name__ == "__main__":
    main()