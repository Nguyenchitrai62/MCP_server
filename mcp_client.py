"""
Generic MCP Client with Gemini LLM
"""
import os
import asyncio
import contextlib

import sys
from dotenv import load_dotenv
from google import genai
from google.genai.types import Tool, FunctionDeclaration, Part, FunctionResponse
from mcp import ClientSession

# Load environment variables
load_dotenv()

# Configuration Parameter
MCP_SERVER_URLS = [
    # "https://localhost:8000/sse",
    # "https://localhost:8001/sse",
    "https://api.nguyenchitrai.id.vn/sse",
]
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") # Replace with your key string if not using .env

# Priority list for fallback mechanism
MODEL_PRIORITY = [
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
    "gemini-exp-1206",
    "gemini-2.0-flash",
    "gemini-2.0-flash-001",

    "gemini-2.5-flash-lite",
    "gemini-2.0-flash-lite",
    "gemini-2.0-flash-lite-001",

    "gemini-2.0-flash-lite-preview-02-05",
]

def convert_mcp_to_gemini_schema(schema):
    """Recursively convert MCP JSON Schema to Gemini Schema format."""
    if not schema:
        return {"type": "STRING"}

    typ = schema.get("type")
    
    if typ == "object" or "properties" in schema:
        return {
            "type": "OBJECT",
            "properties": {k: convert_mcp_to_gemini_schema(v) for k, v in schema.get("properties", {}).items()},
            "required": schema.get("required", [])
        }
    elif typ == "array":
        return {
            "type": "ARRAY",
            "items": convert_mcp_to_gemini_schema(schema.get("items", {})),
            "description": schema.get("description", "")
        }
    else:
        return {
            "type": "STRING" if typ == "string" else 
                    "INTEGER" if typ == "integer" else
                    "NUMBER" if typ == "number" else
                    "BOOLEAN" if typ == "boolean" else "STRING",
            "description": schema.get("description", "")
        }

async def main():
    if not GEMINI_API_KEY:
        print("❌ Error: GEMINI_API_KEY not found in .env or configuration")
        return

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    from mcp.client.sse import sse_client

    async with contextlib.AsyncExitStack() as stack:
        sessions = []
        all_tools = []
        tool_to_session = {}

        print("🔌 Connecting to MCP Servers...")
        
        for url in MCP_SERVER_URLS:
            try:
                print(f"  - Connecting to {url}...")
                read, write = await stack.enter_async_context(sse_client(url))
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                
                tools = await session.list_tools()
                print(f"    ✅ Connected. Found {len(tools.tools)} tools.")
                
                sessions.append(session)
                for t in tools.tools:
                    tool_to_session[t.name] = session
                    all_tools.append(t)
            except Exception as e:
                print(f"    ❌ Failed to connect to {url}: {e}")

        if not sessions:
            print("❌ No MCP servers connected. Exiting.")
            return

        gemini_tools = [
            Tool(function_declarations=[
                FunctionDeclaration(
                    name=t.name,
                    description=t.description,
                    parameters=convert_mcp_to_gemini_schema(t.inputSchema)
                ) for t in all_tools
            ])
        ] if all_tools else []

        # Chat Management
        chat = None
        current_model = None

        def create_session(excluded=None, history=None):
            excluded = excluded or []
            for model in MODEL_PRIORITY:
                if model in excluded: continue
                try:
                    c = client.chats.create(
                        model=model,
                        config={"tools": gemini_tools, "system_instruction": "You are a helpful AI assistant connected to MCP server(s). Use available tools to answer requests."},
                        history=history
                    )
                    return c, model
                except Exception:
                    continue
            return None, None

        chat, current_model = create_session()
        if not chat:
            print("❌ Failed to init any model.")
            return

        print(f"🤖 Ready ({current_model})\nType 'exit' to quit.")

        while True:
            try:
                user_msg = input("\n💬 > ").strip()
                if user_msg.lower() in ("exit", "quit", "q"): break
                if not user_msg: continue

                # Send & Retry Logic
                response = None
                excluded = []
                while True:
                    try:
                        response = chat.send_message(user_msg)
                        break
                    except Exception as e:
                        print(f"⚠️ {current_model} error: {e}")
                        excluded.append(current_model)
                        
                        # Preserve history
                        try: history = chat._curated_history
                        except: history = None
                        
                        chat, current_model = create_session(excluded, history)
                        if not chat:
                            print("❌ All models failed.")
                            raise e
                        print(f"🔄 Switched to {current_model}")

                # Tool Execution Loop
                while response.candidates and response.candidates[0].content.parts:
                    part = response.candidates[0].content.parts[0]
                    if not part.function_call:
                        break
                        
                    fc = part.function_call
                    print(f"  🔧 Tool: {fc.name}")
                    
                    session = tool_to_session.get(fc.name)
                    if not session:
                        print(f"  ❌ Error: No session found for tool {fc.name}")
                        break

                    try:
                        result = await session.call_tool(fc.name, arguments=dict(fc.args))
                        tool_out = "".join([c.text for c in result.content if hasattr(c, "text")])
                        
                        response = chat.send_message(Part(
                            function_response=FunctionResponse(name=fc.name, response={"result": tool_out})
                        ))
                    except Exception as e:
                        print(f"  ❌ Tool error: {e}")
                        break

                # Final Output
                if response.candidates and response.candidates[0].content.parts:
                    final_text = "".join([p.text for p in response.candidates[0].content.parts if p.text])
                    if final_text: print(f"🤖 {final_text}")

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"❌ Error: {e}")



if __name__ == "__main__":
    asyncio.run(main())
