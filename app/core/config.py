import os
import json
import logging
from typing import Dict, Any, Optional

# Configure logging
logger = logging.getLogger("config")

# Default configuration directory
CONFIG_DIR = os.path.join(os.getcwd(), "configs")

# Ensure the config directory exists
os.makedirs(CONFIG_DIR, exist_ok=True)

# Global variables
AGENT_CONFIG = {}


def load_config():
    """Load the most recent global agent configuration into AGENT_CONFIG"""
    global AGENT_CONFIG

    logger.info("Loading configuration...")

    try:
        config_files = [
            f for f in os.listdir(CONFIG_DIR)
            if os.path.isfile(os.path.join(CONFIG_DIR, f)) and f.endswith(".json")
        ]

        if not config_files:
            logger.warning("No configuration files found.")
            AGENT_CONFIG = {}
            return

        # Sort by modified time descending
        config_files.sort(
            key=lambda f: os.path.getmtime(os.path.join(CONFIG_DIR, f)),
            reverse=True
        )
        latest_file = config_files[0]
        latest_file_path = os.path.join(CONFIG_DIR, latest_file)

        with open(latest_file_path, "r") as f:
            AGENT_CONFIG = json.load(f)

        logger.info(f"Configuration loaded from {latest_file_path}")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        AGENT_CONFIG = {}

def save_config(
        agent_id: str, 
        config: Dict[str, Any],
        room_name: Optional[str] = None,
        agent_name:Optional[str] = None
        ) -> bool:
    """Save agent configuration to disk"""
    try:
        file_path = os.path.join(CONFIG_DIR, f"{agent_id}.json")
        if room_name and agent_name:
            config["room_name"] = room_name
            config["agent_name"]=agent_name
        
        with open(file_path, "w") as f:
            json.dump(config, f, indent=2)
            
        logger.info(f"Configuration saved to {file_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save configuration: {e}")
        return False

def get_agent_config(agent_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve agent configuration from disk"""
    try:
        file_path = os.path.join(CONFIG_DIR, f"{agent_id}.json")
        
        if not os.path.exists(file_path):
            logger.error(f"Configuration file not found: {file_path}")
            return None
            
        with open(file_path, "r") as f:
            config = json.load(f)
            
        logger.info(f"Configuration loaded from {file_path}")
        return config
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        return None

def delete_agent_config(agent_id: str) -> bool:
    """Delete agent configuration from disk"""
    try:
        file_path = os.path.join(CONFIG_DIR, f"{agent_id}.json")
        
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Configuration deleted: {file_path}")
            return True
        else:
            logger.warning(f"Configuration file not found: {file_path}")
            return False
    except Exception as e:
        logger.error(f"Failed to delete configuration: {e}")
        return False