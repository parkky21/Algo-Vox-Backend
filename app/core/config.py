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
AGENT_CONFIG = {}  # Latest config
ALL_AGENT_CONFIGS: Dict[str, Dict[str, Any]] = {}  # All configs loaded by agent_id


def load_all_configs():
    """Load all agent configurations from disk"""
    global AGENT_CONFIG, ALL_AGENT_CONFIGS

    logger.info("Loading all agent configurations...")

    try:
        ALL_AGENT_CONFIGS.clear()

        config_files = [
            f for f in os.listdir(CONFIG_DIR)
            if os.path.isfile(os.path.join(CONFIG_DIR, f)) and f.endswith(".json")
        ]

        if not config_files:
            logger.warning("No configuration files found.")
            AGENT_CONFIG = {}
            return

        for file in config_files:
            agent_id = os.path.splitext(file)[0]
            file_path = os.path.join(CONFIG_DIR, file)

            with open(file_path, "r") as f:
                config = json.load(f)
                ALL_AGENT_CONFIGS[agent_id] = config

        # Set AGENT_CONFIG to the latest modified file (for backward compatibility)
        config_files.sort(key=lambda f: os.path.getmtime(os.path.join(CONFIG_DIR, f)), reverse=True)
        latest_file = config_files[0]
        with open(os.path.join(CONFIG_DIR, latest_file), "r") as f:
            AGENT_CONFIG = json.load(f)

        logger.info(f"Loaded {len(ALL_AGENT_CONFIGS)} agent configurations.")
        logger.info(f"Latest configuration loaded from {latest_file}")

    except Exception as e:
        logger.error(f"Failed to load configurations: {e}")
        AGENT_CONFIG = {}
        ALL_AGENT_CONFIGS.clear()


def save_config(
    agent_id: str,
    config: Dict[str, Any],
    room_name: Optional[str] = None,
    agent_name: Optional[str] = None
) -> bool:
    """Save agent configuration to disk and update in-memory store"""
    try:
        if room_name:
            config["room_name"] = room_name
        if agent_name:
            config["agent_name"] = agent_name

        file_path = os.path.join(CONFIG_DIR, f"{agent_id}.json")

        with open(file_path, "w") as f:
            json.dump(config, f, indent=2)

        # Update in-memory configs
        ALL_AGENT_CONFIGS[agent_id] = config
        logger.info(f"Configuration saved to {file_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save configuration: {e}")
        return False


def get_agent_config(agent_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve agent configuration from memory or disk"""
    try:
        if agent_id in ALL_AGENT_CONFIGS:
            return ALL_AGENT_CONFIGS[agent_id]

        file_path = os.path.join(CONFIG_DIR, f"{agent_id}.json")
        if not os.path.exists(file_path):
            logger.error(f"Configuration file not found: {file_path}")
            return None

        with open(file_path, "r") as f:
            config = json.load(f)
            ALL_AGENT_CONFIGS[agent_id] = config  # Update memory cache
            return config

    except Exception as e:
        logger.error(f"Failed to load configuration for agent {agent_id}: {e}")
        return None


def delete_agent_config(agent_id: str) -> bool:
    """Delete agent configuration from disk and memory"""
    try:
        file_path = os.path.join(CONFIG_DIR, f"{agent_id}.json")

        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Configuration deleted: {file_path}")
        else:
            logger.warning(f"Configuration file not found: {file_path}")

        ALL_AGENT_CONFIGS.pop(agent_id, None)
        return True

    except Exception as e:
        logger.error(f"Failed to delete configuration: {e}")
        return False
