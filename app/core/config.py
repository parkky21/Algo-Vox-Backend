# config.py

import json
import os

CONFIG_FILE = "D:\Algo-vox-backend\backend\app\core\agent_runner.py"

AGENT_CONFIG = {
    "nodes": [],
    "global_prompt": "",
    "entry_node": "node_1",
    "room": "default-room",
    "agent_name": "outbound-caller"
}

def save_config():
    with open(CONFIG_FILE, "w") as f:
        json.dump(AGENT_CONFIG, f, indent=2)

def load_config():
    global AGENT_CONFIG
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            AGENT_CONFIG = json.load(f)

load_config()