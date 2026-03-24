
import os
import asyncio
import json
import uvicorn
from contextlib import asynccontextmanager, AsyncExitStack
from typing import AsyncGenerator, Dict, Any, List, Union

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from google import genai
from google.genai.types import Tool, FunctionDeclaration, Part, FunctionResponse, GenerateContentConfig
from mcp import ClientSession
from mcp.client.sse import sse_client

# Load environment variables
load_dotenv()

# --- Configurations ---
DEFAULT_MCP_SERVER_URL = "https://api.nguyenchitrai.id.vn/sse"
# --- Configurations ---
DEFAULT_MCP_SERVER_URL = "https://api.nguyenchitrai.id.vn/sse"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

try:
    from groq import AsyncGroq
except ImportError:
    AsyncGroq = None

if not GEMINI_API_KEY:
    print("WARNING: GEMINI_API_KEY not set!")

# --- Helpers ---
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

# --- Backend Application ---

app = FastAPI(title="MCP Chat Backend")

# Allow CORS for the frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    mcp_urls: List[str] | str | None = None
    provider: str | None = "gemini"
    model: str | None = "gemini-2.5-flash"
    api_key: str | None = None
    base_url: str | None = None

async def chat_process(user_message: str, mcp_urls: List[str], provider: str = "gemini", model: str = "gemini-2.5-flash", api_key: str = None, base_url: str = None):
    """
    Main generator function:
    1. Connects to MCP (one or more)
    2. Initializes LLM Client (Gemini or OpenAI)
    3. Manages the loop: LLM -> [Tool Call -> MCP -> Tool Result] -> LLM -> Text
    """
    
    yield f"data: {json.dumps({'type': 'status', 'content': f'Connecting to MCP Server(s)... Provider: {provider}'})}\n\n"
    
    # Initialize Client
    client = None
    if provider == "gemini":
        key = api_key or GEMINI_API_KEY
        if not key:
             yield f"data: {json.dumps({'type': 'error', 'content': 'GEMINI_API_KEY not set'})}\n\n"
             return
        client = genai.Client(api_key=key)
        
    elif provider == "openai":
         if AsyncOpenAI is None:
             yield f"data: {json.dumps({'type': 'error', 'content': 'openai module not installed. pip install openai'})}\n\n"
             return
             
         key = api_key or OPENAI_API_KEY
         # If base_url is provided (Local LLM), key can be dummy
         if base_url and not key:
             key = "dummy"
             
         if not key:
             yield f"data: {json.dumps({'type': 'error', 'content': 'OPENAI_API_KEY not set'})}\n\n"
             return
             
         client = AsyncOpenAI(api_key=key, base_url=base_url)

    elif provider == "groq":
         if AsyncGroq is None:
             yield f"data: {json.dumps({'type': 'error', 'content': 'groq module not installed. pip install groq'})}\n\n"
             return
        
         key = api_key or GROQ_API_KEY
         if not key:
             yield f"data: {json.dumps({'type': 'error', 'content': 'GROQ_API_KEY not set'})}\n\n"
             return
        
         client = AsyncGroq(api_key=key)
         
    else:
        yield f"data: {json.dumps({'type': 'error', 'content': f'Unknown provider: {provider}'})}\n\n"
        return
    
    try:
        # Create a connection to the MCP server(s)
        async with AsyncExitStack() as stack:
            sessions = []
            all_tools = []
            tool_to_session = {}

            for url in mcp_urls:
                try:
                    url = url.strip()
                    if not url: continue
                    
                    yield f"data: {json.dumps({'type': 'status', 'content': f'Connecting to {url}...'})}\n\n"
                    read, write = await stack.enter_async_context(sse_client(url))
                    session = await stack.enter_async_context(ClientSession(read, write))
                    
                    yield f"data: {json.dumps({'type': 'status', 'content': f'Initializing Session for {url}...'})}\n\n"
                    await session.initialize()
                    
                    # List tools
                    tools_result = await session.list_tools()
                    current_tools = tools_result.tools
                    
                    yield f"data: {json.dumps({'type': 'status', 'content': f'Found {len(current_tools)} tools from {url}'})}\n\n"
                    
                    sessions.append(session)
                    for t in current_tools:
                        tool_to_session[t.name] = session
                        all_tools.append(t)
                        
                except Exception as e:
                    error_msg = f"Failed to connect to {url}: {str(e)}"
                    yield f"data: {json.dumps({'type': 'error', 'content': error_msg})}\n\n"
                    # We continue to try other servers if one fails, or should we stop?
                    # Let's continue to allow partial functionality.

            # --- GEMINI PATH ---
            if provider == "gemini":
                # Convert tools for Gemini
                gemini_tools_declarations = [
                    Tool(function_declarations=[
                        FunctionDeclaration(
                            name=t.name,
                            description=t.description,
                            parameters=convert_mcp_to_gemini_schema(t.inputSchema)
                        ) for t in all_tools
                    ])
                ] if all_tools else []

                # Initialize Chat Session
                chat = client.chats.create(
                    model=model or "gemini-2.5-flash",
                    config=GenerateContentConfig(
                        tools=gemini_tools_declarations, 
                        system_instruction="You are a helpful AI assistant. You have access to tools via MCP. Use them when necessary."
                    )
                )

                # Send initial message
                current_message = user_message
                
                while True:
                    response_stream = chat.send_message_stream(current_message)
                    function_calls = []
                    full_text = ""
                    
                    for chunk in response_stream:
                        candidates = chunk.candidates
                        if not candidates: continue
                        candidate = candidates[0]
                        if not candidate.content or not candidate.content.parts: continue
                        part = candidate.content.parts[0]
                        
                        if part.text:
                            full_text += part.text
                            yield f"data: {json.dumps({'type': 'text_chunk', 'content': part.text})}\n\n"
                            
                        if part.function_call:
                            fc = part.function_call
                            function_calls.append(fc)
                            yield f"data: {json.dumps({'type': 'tool_call', 'name': fc.name, 'args': fc.args})}\n\n"

                    if not function_calls:
                        break
                    
                    for fc in function_calls:
                        yield f"data: {json.dumps({'type': 'status', 'content': f'Executing {fc.name}...'})}\n\n"
                        try:
                            session = tool_to_session.get(fc.name)
                            if not session: raise ValueError(f"No session found for tool {fc.name}")
                            result = await session.call_tool(fc.name, arguments=dict(fc.args))
                            
                            tool_output = ""
                            if hasattr(result, 'content') and result.content:
                                tool_output = "".join([c.text for c in result.content if hasattr(c, "text")])
                            else:
                                tool_output = str(result)

                            response_part = Part(
                                function_response=FunctionResponse(
                                    name=fc.name,
                                    response={"result": tool_output}
                                )
                            )
                            current_message = response_part 
                            yield f"data: {json.dumps({'type': 'tool_result', 'name': fc.name, 'result': tool_output})}\n\n"

                        except Exception as e:
                            err_msg = f"Error executing tool: {str(e)}"
                            yield f"data: {json.dumps({'type': 'error', 'content': err_msg})}\n\n"
                            response_part = Part(
                                function_response=FunctionResponse(
                                    name=fc.name,
                                    response={"error": err_msg}
                                )
                            )
                            current_message = response_part

                            current_message = response_part

            # --- GROQ PATH ---
            elif provider == "groq":
                messages = [
                    {"role": "viewer", "content": "You are a helpful assistant."}, # Groq often prefers system or user/assistant. 'viewer' is a weird role? No, system.
                    {"role": "system", "content": "Use the tools to answer the questions."},
                    {"role": "user", "content": user_message}
                ]
                # Remove the 'viewer' role if it's not standard. OpenAI uses 'system'.
                messages = [
                    {"role": "system", "content": "Use the tools to answer the questions."},
                    {"role": "user", "content": user_message}
                ]
                
                groq_tools = []
                if all_tools:
                    groq_tools = [
                        {
                            "type": "function",
                            "function": {
                                "name": t.name,
                                "description": t.description,
                                "parameters": t.inputSchema,
                            },
                        }
                        for t in all_tools
                    ]
                
                max_turns = 5
                
                for _ in range(max_turns):
                    create_args = {
                        "model": model or "qwen/qwen3-32b",
                        "messages": messages,
                    }
                    if groq_tools:
                        create_args["tools"] = groq_tools
                        create_args["tool_choice"] = "auto"
                    
                    yield f"data: {json.dumps({'type': 'status', 'content': 'Thinking (Groq)...'})}\n\n"
                    
                    response = await client.chat.completions.create(**create_args)
                    response_message = response.choices[0].message
                    
                    if response.choices[0].finish_reason == "tool_calls":
                        messages.append(response_message)
                        
                        for tool_call in response_message.tool_calls:
                            tool_name = tool_call.function.name
                            tool_args_str = tool_call.function.arguments
                            tool_call_id = tool_call.id
                            
                            try:
                                tool_args = json.loads(tool_args_str)
                            except json.JSONDecodeError:
                                tool_args = {}

                            yield f"data: {json.dumps({'type': 'tool_call', 'name': tool_name, 'args': tool_args})}\n\n"
                            yield f"data: {json.dumps({'type': 'status', 'content': f'Executing {tool_name}...'})}\n\n"
                            
                            try:
                                session = tool_to_session.get(tool_name)
                                if not session: raise ValueError(f"No session found for {tool_name}")
                                
                                result = await session.call_tool(tool_name, arguments=tool_args)
                                
                                tool_output = ""
                                if hasattr(result, 'content') and result.content:
                                    tool_output = "".join([c.text for c in result.content if hasattr(c, "text")])
                                else:
                                    tool_output = str(result)
                                
                                yield f"data: {json.dumps({'type': 'tool_result', 'name': tool_name, 'result': tool_output})}\n\n"
                                
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call_id,
                                    "content": tool_output
                                })

                            except Exception as e:
                                err_msg = f"Error executing {tool_name}: {e}"
                                yield f"data: {json.dumps({'type': 'error', 'content': err_msg})}\n\n"
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call_id,
                                    "content": str(e)
                                })
                                
                    else:
                        content = response_message.content
                        if content:
                            yield f"data: {json.dumps({'type': 'text_chunk', 'content': content})}\n\n"
                        break
            
            # --- OPENAI PATH ---
            elif provider == "openai":
                messages = [
                    {"role": "system", "content": "Use the tools to answer the questions."},
                    {"role": "user", "content": user_message}
                ]
                
                openai_tools = []
                if all_tools:
                    openai_tools = [
                        {
                            "type": "function",
                            "function": {
                                "name": t.name,
                                "description": t.description,
                                "strict": True,
                                "parameters": t.inputSchema,
                            },
                        }
                        for t in all_tools
                    ]
                
                max_turns = 5
                
                for _ in range(max_turns):
                    # Call OpenAI API (Non-streaming for robust tool handling as per llm_call_api.py)
                    create_args = {
                        "model": model or "gpt-3.5-turbo",
                        "messages": messages,
                    }
                    if openai_tools:
                        create_args["tools"] = openai_tools
                    
                    yield f"data: {json.dumps({'type': 'status', 'content': 'Thinking...'})}\n\n"
                    
                    response = await client.chat.completions.create(**create_args)
                    response_message = response.choices[0].message
                    
                    # Case 1: Tool Calls
                    if response.choices[0].finish_reason == "tool_calls":
                        messages.append(response_message)
                        
                        for tool_call in response_message.tool_calls:
                            tool_name = tool_call.function.name
                            tool_args_str = tool_call.function.arguments
                            tool_call_id = tool_call.id
                            
                            try:
                                tool_args = json.loads(tool_args_str)
                            except json.JSONDecodeError:
                                tool_args = {} # Handle parsing error logic if needed

                            yield f"data: {json.dumps({'type': 'tool_call', 'name': tool_name, 'args': tool_args})}\n\n"
                            yield f"data: {json.dumps({'type': 'status', 'content': f'Executing {tool_name}...'})}\n\n"
                            
                            try:
                                session = tool_to_session.get(tool_name)
                                if not session: raise ValueError(f"No session found for {tool_name}")
                                
                                result = await session.call_tool(tool_name, arguments=tool_args)
                                
                                # Extract result content
                                tool_output = ""
                                if hasattr(result, 'content') and result.content:
                                    tool_output = "".join([c.text for c in result.content if hasattr(c, "text")])
                                else:
                                    tool_output = str(result)
                                
                                yield f"data: {json.dumps({'type': 'tool_result', 'name': tool_name, 'result': tool_output})}\n\n"
                                
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call_id,
                                    "content": tool_output
                                })

                            except Exception as e:
                                err_msg = f"Error executing {tool_name}: {e}"
                                yield f"data: {json.dumps({'type': 'error', 'content': err_msg})}\n\n"
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call_id,
                                    "content": str(e)
                                })
                                
                    # Case 2: Final Response
                    else:
                        content = response_message.content
                        if content:
                            yield f"data: {json.dumps({'type': 'text_chunk', 'content': content})}\n\n"
                        break
            
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    except Exception as e:
        # Helper to recursively unwrap ExceptionGroups
        def get_actual_errors(exc):
            errors = []
            if hasattr(exc, 'exceptions'):
                for sub_exc in exc.exceptions:
                    errors.extend(get_actual_errors(sub_exc))
            else:
                errors.append(f"{type(exc).__name__}: {str(exc)}")
            return errors

        real_errors = get_actual_errors(e)
        error_msg = " | ".join(real_errors)
        
        print(f"DEBUG: Root cause errors: {error_msg}")
        yield f"data: {json.dumps({'type': 'error', 'content': f'Backend Error: {error_msg}'})}\n\n"


@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    # Normalize mcp_urls
    urls = []
    if req.mcp_urls:
        if isinstance(req.mcp_urls, str):
            urls = [req.mcp_urls]
        else:
            urls = req.mcp_urls
    else:
        urls = [DEFAULT_MCP_SERVER_URL]
        
    return StreamingResponse(chat_process(req.message, urls, req.provider, req.model, req.api_key, req.base_url), media_type="text/event-stream")

class CheckMcpRequest(BaseModel):
    url: str

@app.post("/check-mcp")
async def check_mcp(req: CheckMcpRequest):
    """
    Checks if an MCP server is reachable and valid via SSE.
    """
    url = req.url.strip()
    if not url:
        return {"status": "error", "message": "Empty URL"}
        
    try:
        # Use a short timeout for the check
        async def try_connect():
            async with sse_client(url) as _:
                pass # If we enter context, connection is successful
                
        await asyncio.wait_for(try_connect(), timeout=5.0)
        return {"status": "connected", "message": "Successfully connected"}
        
    except asyncio.TimeoutError:
         return {"status": "error", "message": "Connection timed out"}
    except Exception as e:
         return {"status": "error", "message": f"Connection failed: {str(e)}"}
     
@app.get("/")
def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=9000)
