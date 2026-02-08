import os
import asyncio
import json
import traceback
from pathlib import Path
from typing import List, Dict, Any, Optional
from contextlib import asynccontextmanager
import re

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from google import genai
from google.genai.types import Tool, FunctionDeclaration, Part, FunctionResponse
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Load environment variables
load_dotenv()

# --- Configuration ---
API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    print("WARNING: GEMINI_API_KEY not found in .env file")

# --- Constants ---
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

# --- Global State ---
gemini_client = None

# --- Helpers ---
def convert_mcp_to_gemini_schema(mcp_schema):
    """Convert MCP JSON Schema to Gemini Schema format."""
    properties = mcp_schema.get("properties", {})
    required = mcp_schema.get("required", [])
    
    gemini_properties = {}
    for prop_name, prop_info in properties.items():
        prop_type = prop_info.get("type", "string")
        prop_desc = prop_info.get("description", "")
        
        type_mapping = {
            "string": "STRING",
            "integer": "INTEGER",
            "number": "NUMBER",
            "boolean": "BOOLEAN",
            "array": "ARRAY",
            "object": "OBJECT"
        }
        
        gemini_properties[prop_name] = {
            "type": type_mapping.get(prop_type, "STRING"),
            "description": prop_desc
        }
    
    return {
        "type": "OBJECT",
        "properties": gemini_properties,
        "required": required
    }

# --- Life Cycle ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Global initialization
    global gemini_client
    if API_KEY:
        gemini_client = genai.Client(api_key=API_KEY)
        print("✅ Gemini Client Initialized")
    else:
        print("❌ Gemini Client Init Failed: No API Key")
        
    yield
    # Cleanup if needed
    print("🛑 Server Shutting Down")

# --- App Setup ---
app = FastAPI(title="MCP Agent API", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all for dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Models ---
class ChatRequest(BaseModel):
    query: str
    history: Optional[List[Dict[str, Any]]] = None

class ChatResponse(BaseModel):
    text: str
    commands: Optional[List[Dict[str, Any]]] = None

# --- System Instruction ---
SYSTEM_INSTRUCTION = """
You are an AI assistant for a piping system visualization tool.
You have access to a dataset (shapes database) via tools.
You also have access to UI CONTROL TOOLS to manipulate the interface (highlight, view, toggle_layer, etc.).

**GUIDELINES:**
1. **Use Tools**: When the user asks to see, find, or analyze something, use the appropriate tools (`highlight`, `view`) to visualize it.
   - Example: "Show me all Tees" -> Call `highlight(criteria={'shape_name': ['Tee']})`.
   - Example: "Where are the DN25 pipes?" -> Call `highlight(criteria={'shape_name': ['Pipe'], 'DN': 25})`.
   
2. **Layer Control**: Use `toggle_layer` only when explicitly asked about layers or visibility of categories.

3. **Combined Actions**: You can use multiple tools in sequence. For example, use a data tool to count items, then a UI tool to highlight them.

4. **Response**: Be concise and helpful in your text response. The UI actions will happen automatically based on your tool calls.

IMPORTANT: Do NOT output JSON/Code blocks for UI actions. Use the provided tools directly.
"""

# --- Client Tool Definitions ---
def get_client_tool_definitions():
    return [
        FunctionDeclaration(
            name="highlight",
            description="Highlight specific shapes or objects in the CAD drawing based on criteria.",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "criteria": {
                        "type": "OBJECT",
                        "properties": {
                            "shape_name": {
                                "type": "ARRAY", 
                                "items": {"type": "STRING"}, 
                                "description": "List of shape names (e.g. ['Tee', 'Elbow', 'Pipe'])"
                            },
                            "DN": {"type": "INTEGER", "description": "Nominal Diameter filter"},
                            "layer": {"type": "STRING", "description": "Layer name filter"}
                        }
                    }
                },
                "required": ["criteria"]
            }
        ),
        FunctionDeclaration(
            name="view",
            description="Focus/Zoom the camera to specific shapes.",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "criteria": {
                        "type": "OBJECT",
                        "properties": {
                             "shape_name": {"type": "ARRAY", "items": {"type": "STRING"}},
                             "DN": {"type": "INTEGER"},
                             "layer": {"type": "STRING"}
                        }
                    }
                },
                "required": ["criteria"]
            }
        ),
        FunctionDeclaration(
            name="toggle_layer",
            description="Control visibility of layers.",
            parameters={
                 "type": "OBJECT",
                 "properties": {
                     "criteria": {
                         "type": "OBJECT",
                         "properties": {
                             "layer_name": {"type": "ARRAY", "items": {"type": "STRING"}},
                             "type": {"type": "STRING", "enum": ["text", "graphic", "all", "any"]}
                         }
                     },
                     "action": {
                         "type": "STRING", 
                         "enum": ["show", "hide", "toggle", "only"],
                         "description": "show: visible, hide: invisible, toggle: invert, only: show these and hide others"
                     }
                 },
                 "required": ["criteria", "action"]
            }
        ),
        FunctionDeclaration(
            name="clear_highlight",
            description="Clear all active highlights.",
            parameters={"type": "OBJECT", "properties": {}}
        ),
        FunctionDeclaration(
            name="click",
            description="Programmatically click a button in the UI.",
            parameters={
                "type": "OBJECT",
                "properties": {
                    "target_id": {"type": "STRING", "description": "ID of the element to click"}
                },
                "required": ["target_id"]
            }
        )
    ]

CLIENT_TOOL_NAMES = ["highlight", "view", "toggle_layer", "clear_highlight", "click"]

# --- Routes ---
@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    if not gemini_client:
        raise HTTPException(status_code=500, detail="Gemini Client not initialized")

    # Connect to MCP Server per request
    script_dir = Path(__file__).parent
    server_script = script_dir / "MCP_server.py"

    import sys
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(server_script)],
        env=os.environ.copy() # Pass env vars
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                
                # Get Tools
                tools_list = await session.list_tools()
                
                # Convert Tools
                gemini_functions = []
                for tool in tools_list.tools:
                    func_decl = FunctionDeclaration(
                        name=tool.name,
                        description=tool.description,
                        parameters=convert_mcp_to_gemini_schema(tool.inputSchema)
                    )
                    gemini_functions.append(func_decl)
                
                # Identify Client Tools
                gemini_functions.extend(get_client_tool_definitions())
                
                gemini_tool = Tool(function_declarations=gemini_functions)

                # Attempt with fallback models
                response = None
                last_error = None
                
                for model_name in MODEL_PRIORITY:
                    try:
                        print(f"🤖 Agent: Attempting with model {model_name}...")
                        
                        # Create Chat Config
                        chat = gemini_client.chats.create(
                            model=model_name, 
                            config={
                                "tools": [gemini_tool],
                                "system_instruction": SYSTEM_INSTRUCTION
                            }
                        )

                        # Send User Message
                        response = chat.send_message(request.query)
                        
                        # If success, break loop
                        if response:
                            print(f"✅ Success with model {model_name}")
                            break
                            
                    except Exception as e:
                        print(f"⚠️ Error with model {model_name}: {e}")
                        last_error = e
                        # Continue to next model
                
                if not response:
                    raise HTTPException(status_code=503, detail=f"All AI models failed. Last error: {last_error}")

                final_text = ""
                commands = [] # Queue for client commands

                # Loop to handle tool calls
                while True:
                    has_tool_call = False
                    if not response.candidates or not response.candidates[0].content.parts:
                        break
                        
                    for part in response.candidates[0].content.parts:
                        if part.function_call:
                            has_tool_call = True
                            fc = part.function_call
                            print(f"🔧 Tool Call: {fc.name}")
                            
                            # INTERCEPT CLIENT TOOLS
                            if fc.name in CLIENT_TOOL_NAMES:
                                print(f"  -> Client Command Intercepted: {fc.name}")
                                # Convert tool call to command dict
                                cmd = {"command": fc.name}
                                cmd.update(fc.args) # Add arguments like criteria, action
                                commands.append(cmd)
                                
                                # Mock success response to model
                                response_part = Part(
                                    function_response=FunctionResponse(
                                        name=fc.name,
                                        response={"result": "Command sent to client UI."}
                                    )
                                )
                                response = chat.send_message(response_part)
                                break # Process next response from model
                                
                            else:
                                # EXECUTE MCP TOOLS
                                try:
                                    result = await session.call_tool(fc.name, arguments=dict(fc.args))
                                    tool_output = ""
                                    if result.content:
                                        for item in result.content:
                                            if hasattr(item, 'text'):
                                                tool_output += item.text
                                    
                                    # Send outcome back
                                    response_part = Part(
                                        function_response=FunctionResponse(
                                            name=fc.name,
                                            response={"result": tool_output}
                                        )
                                    )
                                    response = chat.send_message(response_part)
                                    break # Check new response
                                except Exception as e:
                                    print(f"❌ Tool Error: {e}")
                                    error_part = Part(
                                        function_response=FunctionResponse(
                                            name=fc.name,
                                            response={"error": str(e)}
                                        )
                                    )
                                    response = chat.send_message(error_part)
                                    break

                    if not has_tool_call:
                        break
                
                # Extract Final Text
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'text') and part.text:
                        final_text += part.text

                # Legacy JSON parsing (for backward compat or if model hallucinates JSON)
                # We prioritize the `commands` list populated by Tool Calls above.

                try:
                    # Look for code blocks or raw JSON objects
                    # Regex to find all JSON-like structures might be complex, 
                    # but usually models return one block or one list.
                    
                    # Strategy 1: Find ```json ... ``` blocks
                    code_blocks = re.findall(r'```json\s*([\s\S]*?)\s*```', final_text)
                    for block in code_blocks:
                        try:
                            parsed = json.loads(block)
                            if isinstance(parsed, list):
                                commands.extend(parsed)
                            elif isinstance(parsed, dict):
                                commands.append(parsed)
                        except:
                            pass
                            
                    # Strategy 2: If no code blocks, look for raw {...}
                    if not commands:
                        raw_matches = re.findall(r'\{[\s\S]*\}', final_text)
                        for match in raw_matches:
                            try:
                                # Validate if it looks like a command
                                parsed = json.loads(match)
                                if isinstance(parsed, dict) and "command" in parsed:
                                    commands.append(parsed)
                            except:
                                pass
                                
                except Exception as e:
                    print(f"JSON Parse Error: {e}")

                return ChatResponse(text=final_text, commands=commands)

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
