from app.core.models import AgentConfig, NodeConfig, NodeRoute, GlobalSettings
from pydantic import ValidationError

def parse_agent_config(raw_json: dict) -> AgentConfig:
    """
    Converts UI JSON (with 'nodes', 'edges', etc.) to AgentConfig model.
    Assumes node data is inside node["data"].
    """
    try:
        global_settings = raw_json.get("global_settings")
        entry_node = raw_json.get("entry_node")
        flow_type=raw_json.get("flow_type")

        ui_nodes = raw_json.get("nodes", [])
        parsed_nodes = []

        for node in ui_nodes:
            node_data = node.get("data", {})
            if not node_data:
                continue
            parsed_nodes.append(NodeConfig(**node_data))

        agent_config = AgentConfig(
            global_settings=GlobalSettings(**global_settings) if global_settings else None,
            entry_node=entry_node,
            nodes=parsed_nodes,
            flow_type=flow_type
        )

        return agent_config

    except ValidationError as e:
        print("Validation error while parsing agent config:", e)
        raise
