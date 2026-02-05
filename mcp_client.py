"""
MCP Client with Gemini LLM - Natural Language Query Interface
"""
import os
import asyncio
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai.types import Tool, FunctionDeclaration, Part, FunctionResponse

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Load environment variables
load_dotenv()

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

def convert_mcp_to_gemini_schema(mcp_schema):
    """Convert MCP JSON Schema to Gemini Schema format."""
    properties = mcp_schema.get("properties", {})
    required = mcp_schema.get("required", [])
    
    # Convert properties
    gemini_properties = {}
    for prop_name, prop_info in properties.items():
        prop_type = prop_info.get("type", "string")
        prop_desc = prop_info.get("description", "")
        
        # Map JSON Schema types to Gemini types
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

async def llm_mode():
    """LLM mode - Natural language queries powered by Gemini."""
    
    # Initialize Gemini Client
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("❌ Error: GEMINI_API_KEY not found in .env file")
        return
    
    client = genai.Client(api_key=api_key)
    
    # Connect to MCP Server via SSE
    # Connect to MCP Server via SSE
    # Make sure the server is running: python MCP_server.py --transport sse
    # mcp_url = "http://localhost:8000/sse"
    mcp_url = "https://analysis-fire-mcp.fastmcp.app/mcp" # Horizon deployment URL
    
    horizon_api_key = os.getenv("HORIZON_API_KEY")
    headers = {}
    if horizon_api_key:
        headers["Authorization"] = f"Bearer {horizon_api_key}"
        print(f"🔑 Using HORIZON_API_KEY for authentication")
    
    print(f"🔌 Connecting to MCP Server at {mcp_url}...")
    
    from mcp.client.sse import sse_client
    
    async with sse_client(mcp_url, headers=headers) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # Get available tools from MCP server
            tools_list = await session.list_tools()
            print(f"✅ Connected to MCP Server with {len(tools_list.tools)} tools")
            
            # Convert MCP tools to Gemini function declarations
            gemini_functions = []
            for tool in tools_list.tools:
                func_decl = FunctionDeclaration(
                    name=tool.name,
                    description=tool.description,
                    parameters=convert_mcp_to_gemini_schema(tool.inputSchema)
                )
                gemini_functions.append(func_decl)
            
            # Create Gemini tool
            gemini_tool = Tool(function_declarations=gemini_functions)
            
            print("\n" + "=" * 70)
            print("🤖 GEMINI-POWERED SHAPES DATABASE QUERY")
            print("=" * 70)
            print("\n💬 Ask me anything about the shapes database in natural language!")
            print("\n💡 Example questions:")
            print("  • Có bao nhiêu Sprinkler trong hệ thống?")
            print("  • Tìm tất cả Tee có DN=25")
            print("  • Các Elbow nằm ở đâu?")
            print("  • Show me statistics about the database")
            print("  • How many pipes with pipe_id=17?")
            print("\n📝 Type 'exit' or 'quit' to exit")
            print("=" * 70)
            
            # Chat session
            chat = None
            current_model = None

            # Helper to create chat with fallback
            def create_chat_session(excluded_models=None, history=None):
                if excluded_models is None:
                    excluded_models = []
                
                for model_name in MODEL_PRIORITY:
                    if model_name in excluded_models:
                        continue

                    try:
                        print(f"  Trying model: {model_name}...")
                        c = client.chats.create(
                            model=model_name,
                            config={
                                "tools": [gemini_tool],
                                "system_instruction": """You are a helpful assistant for querying a shapes database containing pipes, sprinklers, tees, elbows, and other piping system components.

The database contains objects with these fields:
- id: unique identifier
- shape_name: type of shape (Sprinkler, Tee, Elbow, Line, etc.)
- pipe_id: pipe identifier
- DN: pipe diameter values (array)
- object_type: type of object (pipe, sprinkler, etc.)
- vertices: coordinate points
- connectors: connection points

When users ask questions:
1. Use the available tools to query the database
2. Provide clear, concise answers in Vietnamese or English based on user's language
3. Include relevant numbers and details
4. If showing locations, mention bounding boxes when available

Available tools:
- count_objects: Count objects by criteria
- find_objects: Find objects matching criteria
- get_object_by_id: Get details of specific object
- get_object_locations: Get location information
- list_available_shapes: List all shape types
- get_statistics: Get database statistics
- search_by_criteria: Advanced search with multiple criteria"""
                            },
                            history=history
                        )
                        return c, model_name
                    except Exception as e:
                        print(f"  ⚠️ Failed {model_name}: {e}")
                return None, None

            # Initialize first session
            chat, current_model = create_chat_session()
            if not chat:
                print("❌ Failed to initialize any AI model.")
                return 

            print(f"✅ Initialized with model: {current_model}")

            def safe_send_message(message_content):
                """Send message with automatic fallback to other models on failure."""
                nonlocal chat, current_model
                
                excluded = []
                while True:
                    try:
                        return chat.send_message(message_content)
                    except Exception as e:
                        print(f"⚠️ Model {current_model} failed: {e}")
                        excluded.append(current_model)
                        
                        # Try to capture current history to preserve context
                        try:
                            current_history = chat._curated_history
                        except AttributeError:
                             try:
                                current_history = chat.history
                             except:
                                current_history = None
                        
                        print("🔄 Switching to next available model...")
                        new_chat, new_model = create_chat_session(excluded_models=excluded, history=current_history)
                        
                        if new_chat:
                            chat = new_chat
                            current_model = new_model
                            print(f"✅ Switched to: {current_model}")
                            # Loop continues and retries send_message with new chat
                        else:
                            print("❌ All models failed to respond.")
                            raise e

            while True:
                try:
                    user_input = input("\n💬 You: ").strip()
                    
                    if not user_input:
                        continue
                    
                    if user_input.lower() in ["exit", "quit", "q"]:
                        print("👋 Goodbye!")
                        break
                    
                    try:
                        response = safe_send_message(user_input)
                    except Exception as e:
                        print(f"⚠️ Error sending message after all retries: {e}")
                        continue

                    # Process response - handle function calls
                    final_text = ""
                    
                    # Loop manually to handle tools
                    while True:
                        has_tool_call = False
                        if not response.candidates or not response.candidates[0].content.parts:
                            break

                        for part in response.candidates[0].content.parts:
                            if part.function_call:
                                has_tool_call = True
                                fc = part.function_call
                                print(f"  🔧 Calling tool: {fc.name}...")
                                
                                try:
                                    # Execute tool on MCP server
                                    result = await session.call_tool(fc.name, arguments=dict(fc.args))
                                    
                                    # Extract text content from result
                                    tool_output = ""
                                    if result.content:
                                        for content_item in result.content:
                                            if hasattr(content_item, 'text'):
                                                tool_output += content_item.text
                                    
                                    # Send function response back to Gemini
                                    response_part = Part(
                                        function_response=FunctionResponse(
                                            name=fc.name,
                                            response={"result": tool_output}
                                        )
                                    )
                                    
                                    # Get final response from Gemini
                                    response = safe_send_message(response_part)
                                    break # Check new response (back to inner loop)
                                
                                except Exception as e:
                                    print(f"  ❌ Error executing tool: {e}")
                                    break # Break inner loop
                        
                        if not has_tool_call:
                             break


                    # After tool loop, get text
                    if response.candidates and response.candidates[0].content.parts:
                        for final_part in response.candidates[0].content.parts:
                            if hasattr(final_part, 'text') and final_part.text:
                                final_text += final_part.text
                    
                    # Display Gemini's response
                    if final_text:
                        print(f"\n🤖 Assistant: {final_text}")
                    
                except KeyboardInterrupt:
                    print("\n\n👋 Goodbye!")
                    break
                except Exception as e:
                    print(f"❌ Error: {e}")
                    import traceback
                    traceback.print_exc()

if __name__ == "__main__":
    print("Starting Gemini-powered MCP Shapes Database Client...")
    asyncio.run(llm_mode())
