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
            name="search_file_contents",
            description="Search for text in files using indexed full-text search. Returns: list of matches with file paths, relevance scores, character offsets, and content snippets.\n\nEXAMPLE QUERIES:\n- 'error' - Simple search\n- 'function definition' - Multiple terms\n- 'import requests' - Exact phrase\n\nBEST PRACTICES:\n1. Use list_directory_contents first to understand what you're working with\n2. Start with globPattern='*' to search all files before filtering by specific file types",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query."
                    },
                    "globPattern": {
                        "type": "string",
                        "description": "Glob pattern relative to search path (e.g., '*', '*.txt', 'data/**', 'src/**/*.txt'). Leading slashes are ignored. Default searches all files.",
                        "default": "*"
                    },
                    "skip": {
                        "type": "integer",
                        "description": "Skip first N matches",
                        "default": 0
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="search_file_contents_with_lucene_syntax",
            description="Search for text in files using Tantivy query syntax with manual control. Write queries manually with operators like fuzzy (~2), wildcards (*), phrases (\"\"), boolean (AND/OR/NOT), and more. Use this when you want exact control over the query. Returns: list of matches with file paths, relevance scores, character offsets, and content snippets.\n\nEXAMPLE QUERIES:\n- 'error~2' - Fuzzy search (max 2 edits)\n- 'def*' - Wildcard search\n- '\"exact phrase\"' - Exact phrase\n- 'term1 AND term2' - Boolean AND\n- '(error OR warning) AND log' - Complex boolean",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Tantivy query syntax. Examples: 'term1 AND term2', 'term~2', 'prefix*', '\"exact phrase\"', '(term1 OR term2) AND term3'"
                    },
                    "globPattern": {
                        "type": "string",
                        "description": "Glob pattern relative to search path (e.g., '*', '*.txt', 'data/**', 'src/**/*.txt'). Leading slashes are ignored. Default searches all files.",
                        "default": "*"
                    },
                    "skip": {
                        "type": "integer",
                        "description": "Skip first N matches",
                        "default": 0
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="read_file_chunk",
            description="Read a text chunk from a file around a specific character offset. Returns approximately 1000 characters (100 before and 900 after the offset). Returns: file path, character range, and text content.",
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
            name="list_directory_contents",
            description="List files and directories at the specified path. Returns folders and files with sizes. Returns: organized list of folders and files with byte sizes and total counts.\n\nBEST PRACTICE: Use this tool first to understand what you're working with before searching.",
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
    if name == "list_directory_contents":
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
    
    if name == "read_file_chunk":
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
        end = min(len(content), char_offset + 900)
        chunk = content[start:end]
        max_range = len(content)
        
        display_path = str(full_path).replace('\\', '/') if full_path_output else file_path
        output = f"File: {display_path}\n"
        output += f"Range: {start}-{end} (offset {char_offset}) [Max: 0-{max_range}]\n"
        output += f"Context:\n{chunk}\n\n\n"
        
        return [TextContent(type="text", text=output)]
    
    if name not in ("search_file_contents", "search_file_contents_with_lucene_syntax"):
        raise ValueError(f"Unknown tool: {name}")
    
    query = arguments["query"]
    file_pattern = arguments.get("globPattern", "*")
    skip = arguments.get("skip", 0)
    limit = arguments.get("limit", 10)
    full_path_output = USE_FULL_PATH
    bypass_fuzzy = (name == "search_file_contents_with_lucene_syntax")
    
    search_path = Path(SEARCH_PATH)
    
    if not search_path.exists():
        return [TextContent(type="text", text=f"Path not found: {SEARCH_PATH}")]
    
    global SEARCH_INDEX
    if SEARCH_INDEX is None:
        schema_builder = tantivy.SchemaBuilder()
        schema_builder.add_text_field("path", stored=True)
        schema_builder.add_text_field("content", stored=True, tokenizer_name="default")
        schema_builder.add_integer_field("char_offset", stored=True, indexed=False)
        schema = schema_builder.build()
        
        SEARCH_INDEX = tantivy.Index(schema, path=None)
        writer = SEARCH_INDEX.writer()
        
        CHUNK_SIZE = 500
        CHUNK_OVERLAP = 100
        
        # Normalize file pattern: remove leading slash, ensure proper glob syntax
        if file_pattern != "*":
            file_pattern = file_pattern.lstrip('/')
            if file_pattern.endswith('**'):
                file_pattern += '/*'
        
        for file_path in search_path.rglob('*'):
            if not file_path.is_file():
                continue
            
            # Filter by file pattern during indexing
            if file_pattern != "*":
                relative_path = file_path.relative_to(search_path)
                relative_str = str(relative_path).replace('\\', '/')
                
                # Check if it's an exact path or a glob pattern
                if '*' in file_pattern or '?' in file_pattern:
                    # Use glob matching
                    if not relative_path.match(file_pattern):
                        continue
                else:
                    # Exact path match
                    if relative_str != file_pattern:
                        continue
            
            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                if full_path_output:
                    display_path = str(file_path).replace('\\', '/')
                else:
                    display_path = '/' + str(file_path.relative_to(search_path)).replace('\\', '/')
                
                # Chunk the file content
                for i in range(0, len(content), CHUNK_SIZE - CHUNK_OVERLAP):
                    chunk = content[i:i + CHUNK_SIZE]
                    if chunk.strip():  # Skip empty chunks
                        writer.add_document(tantivy.Document(
                            path=[display_path],
                            content=[chunk],
                            char_offset=[i]
                        ))
            except:
                continue
        
        writer.commit()
        SEARCH_INDEX.reload()
    
    try:
        # Add automatic fuzzy matching for all queries (unless bypassed)
        if not bypass_fuzzy:
            # Split query into terms and add fuzzy matching to each
            terms = query.split()
            if len(terms) == 1 and '"' not in query and '~' not in query and '*' not in query:
                # Single term: combine fuzzy and prefix matching
                fuzzy_query = f"({query}~2 OR {query}*)"
            else:
                # Multiple terms or special operators: just apply fuzzy to plain terms
                fuzzy_terms = []
                for term in terms:
                    if '"' not in term and '~' not in term and '*' not in term and term.upper() not in ('AND', 'OR', 'NOT'):
                        fuzzy_terms.append(f"({term}~2 OR {term}*)")
                    else:
                        fuzzy_terms.append(term)
                fuzzy_query = ' '.join(fuzzy_terms)
            tantivy_query = SEARCH_INDEX.parse_query(fuzzy_query, ["content"])
        else:
            tantivy_query = SEARCH_INDEX.parse_query(query, ["content"])
    except:
        return [TextContent(type="text", text=f"Invalid query syntax: {query}")]
    
    searcher = SEARCH_INDEX.searcher()
    search_result = searcher.search(tantivy_query, limit=limit, offset=skip)
    search_results = search_result.hits
    total_count = search_result.count
    
    results = []
    
    for score, doc_address in search_results:
        doc = searcher.doc(doc_address)
        file_path = doc.get_first("path")
        content = doc.get_first("content")
        char_offset = doc.get_first("char_offset")
        
        results.append({
            'file': file_path,
            'score': score,
            'chunk': content,
            'char_offset': char_offset
        })
    
    output = f"Total found: {total_count} matches\n\n"
    for r in results:
        output += f"File: {r['file']}\n"
        output += f"Score: {r['score']:.2f}\n"
        output += f"Offset: {r['char_offset']}\n"
        output += f"Context:\n{r['chunk']}\n\n"
        output += "-"*20+"\n\n"
    
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