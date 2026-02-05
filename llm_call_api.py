import asyncio
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from openai import OpenAI
from dotenv import load_dotenv
from google import genai
import json

# Load environment variables
load_dotenv()

# client = OpenAI(api_key="FAKEAPI", base_url="http://10.0.8.23:1235/v1")
client = OpenAI(
    api_key="AIzaSyB0IJ0S4syOZpJI8MIc_OwdjxgVV8vgsjQ",
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

model= "gemini-2.5-flash"


class ConnectionManager:
    def __init__(self, sse_server_map):
        self.sse_server_map = sse_server_map
        self.sessions = {}
        self.exit_stack = AsyncExitStack()

    async def initialize(self):
        # Initialize SSE connections
        for server_name, url in self.sse_server_map.items():
            sse_transport = await self.exit_stack.enter_async_context(
                sse_client(url=url)
            )
            read, write = sse_transport
            session = await self.exit_stack.enter_async_context(
                ClientSession(read, write)
            )
            await session.initialize()
            self.sessions[server_name] = session

    async def list_tools(self):
        tool_map = {}
        consolidated_tools = []
        for server_name, session in self.sessions.items():
            tools = await session.list_tools()
            tool_map.update({tool.name: server_name for tool in tools.tools})
            consolidated_tools.extend(tools.tools)
        return tool_map, consolidated_tools

    async def call_tool(self, tool_name, arguments, tool_map):
        server_name = tool_map.get(tool_name)
        if not server_name:
            print(f"Tool '{tool_name}' not found.")
            return

        session = self.sessions.get(server_name)
        if session:
            result = await session.call_tool(tool_name, arguments=arguments)
            return result.content[0].text

    async def close(self):
        await self.exit_stack.aclose()


# Chat function to handle interactions and tool calls
async def chat(
    input_messages,
    tool_map,
    tools,
    max_turns=3,
    connection_manager=None,
):
    chat_messages = input_messages[:]
    for _ in range(max_turns):
        result = client.chat.completions.create(
            model=model,
            messages=chat_messages,
            tools=tools,
        )

        if result.choices[0].finish_reason == "tool_calls":
            chat_messages.append(result.choices[0].message)
            # Loop and call and append to message array
            for tool_call in result.choices[0].message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments)

                # Get server name for the tool just for logging
                server_name = tool_map.get(tool_name, "")

                # Log tool call
                log_message = f"**Tool Call**  \n**Tool Name:** `{tool_name}` from **MCP Server**: `{server_name}`  \n**Input:**  \n```json\n{json.dumps(tool_args, indent=2)}\n```"
                yield {"role": "assistant", "content": log_message}

                # Call the tool and log its observation
                observation = await connection_manager.call_tool(
                    tool_name, tool_args, tool_map
                )
                log_message = f"**Tool Observation**  \n**Tool Name:** `{tool_name}` from **MCP Server**: `{server_name}`  \n**Output:**  \n```json\n{json.dumps(observation, indent=2)}\n```  \n---"
                yield {"role": "assistant", "content": log_message}

                chat_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": str(observation),
                    }
                )
        else:
            yield {"role": "assistant", "content": result.choices[0].message.content}
            return

    # Generate a final response if max turns are reached
    print("✅Before ", chat_messages)
    result = client.chat.completions.create(
        model=model,
        messages=chat_messages,
    )
    yield {"role": "assistant", "content": result.choices[0].message.content}



if __name__ == "__main__":
    sse_server_map = {
        "python_executor_mcp": "http://10.0.8.23:8001/sse",
    }

    async def main():
        connection_manager = ConnectionManager(sse_server_map)
        await connection_manager.initialize()

        tool_map, tool_objects = await connection_manager.list_tools()

        tools_json = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "strict": True,
                    "parameters": tool.inputSchema,
                },
            }
            for tool in tool_objects
        ]
        # print(tools_json)

        input_messages = [
            {
                "role": "system",
                "content": "Use the tools to answer the questions.",
            },
            {"role": "user", "content": "tính tổng 112 và 123"},
        ]

        async for response in chat(
            input_messages,
            tool_map,
            tools=tools_json,
            connection_manager=connection_manager,
        ):
            print(response)

        await connection_manager.close()

    asyncio.run(main())