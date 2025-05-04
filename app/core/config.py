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
    """Load global configuration"""
    global AGENT_CONFIG
    
    # This function can be expanded to load from environment variables or config files
    logger.info("Loading configuration...")

def save_config(agent_id: str, config: Dict[str, Any]) -> bool:
    """Save agent configuration to disk"""
    try:
        file_path = os.path.join(CONFIG_DIR, f"{agent_id}.json")
        
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