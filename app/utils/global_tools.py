from livekit.agents import function_tool, RunContext
from typing import List, Callable
from app.core.models import AgentConfig

def build_global_tools(
    agent_config: AgentConfig,
    agent_id: str,
    create_agent_fn: Callable  # Pass in the create_agent function
) -> List:
    tools = []

    for idx, node in enumerate(agent_config.nodes):
        if getattr(node, "global_node", False):
            tool_name = f"global_{idx + 1}"
            condition = getattr(node, "global_node_condition", f"Trigger global node {node.node_id}")
            next_node = node.node_id

            def make_tool(next_node_val):
                @function_tool(name=tool_name, description=condition)
                async def global_tool(context: RunContext):
                    chat_ctx = context.session._chat_ctx
                    return await create_agent_fn(
                        node_id=next_node_val,
                        chat_ctx=chat_ctx,
                        agent_config=context.session._agent_config,
                        agent_id=agent_id
                    )
                return global_tool

            tools.append(make_tool(next_node))

    return tools
