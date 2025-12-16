import re
import sys
import os
from pathlib import Path
from rapidfuzz import fuzz
from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio
import asyncio


SEARCH_PATH = None

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
                    "offset": {
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
        )
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name != "search":
        raise ValueError(f"Unknown tool: {name}")
    
    query = arguments["query"]
    offset = arguments.get("offset", 0)
    threshold = arguments.get("threshold", 80)
    
    search_path = Path(SEARCH_PATH)
    results = []
    total_found = 0
    
    if not search_path.exists():
        return [TextContent(
            type="text",
            text=f"Path not found: {SEARCH_PATH}"
        )]
    
    query_len = len(query)
    matches_found = 0
    
    for file_path in search_path.rglob('*'):
        if not file_path.is_file():
            continue
        
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
        except:
            continue
        
        words = re.findall(r'\S+', content)
        
        for i, word in enumerate(words):
            if abs(len(word) - query_len) > query_len * 0.3:
                continue
                
            similarity = fuzz.ratio(query.lower(), word.lower())
            
            if similarity >= threshold:
                total_found += 1
                
                if matches_found >= offset and len(results) < 5:
                    pos = content.find(word, sum(len(w) + 1 for w in words[:i]))
                    chunk_start = max(0, pos - 250)
                    chunk_end = min(len(content), pos + len(word) + 250)
                    chunk = content[chunk_start:chunk_end]
                    
                    relative_path = '/' + str(file_path.relative_to(search_path)).replace('\\', '/')
                    
                    results.append({
                        'file': relative_path,
                        'position': pos,
                        'match': word,
                        'similarity': similarity,
                        'chunk': chunk
                    })
                
                matches_found += 1
    
    output = f"Total found: {total_found}\n\n"
    for r in results:
        output += f"File: {r['file']}\n"
        output += f"Position: {r['position']}\n"
        output += f"Context:\n{r['chunk']}\n\n\n"
        output += "-"*20+"\n\n\n"
    
    return [TextContent(type="text", text=output)]

def main():
    global SEARCH_PATH
    
    # Get search path from environment variable or command line argument
    if len(sys.argv) > 1:
        SEARCH_PATH = sys.argv[1]
    else:
        SEARCH_PATH = os.getenv('SEARCH_PATH')
    
    if not SEARCH_PATH:
        print("Error: No search path provided. Set SEARCH_PATH environment variable or pass as argument.", file=sys.stderr)
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