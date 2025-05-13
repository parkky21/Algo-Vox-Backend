## 🚀 Getting Started

### 1. Clone & Install

```bash
git clone https://github.com/your-org/algo-vox.git
cd algo-vox/backend
python -m venv venv
pip install -r requirements.txt
```

### 2. Create `.env` File

```env
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret
LIVEKIT_URL=wss://yourdomain.livekit.cloud

# Optional: Add OpenAI, Google, or Deepgram keys if used
```

### 3. Run the API Server

```bash
uvicorn app.main:app --reload
# or
python main.py
```

---

## 📡 API Routes

| Method | Endpoint               | Description                  |
| ------ | ---------------------- | ---------------------------- |
| POST   | `/agents/start-agent`  | Start a voice agent session  |
| POST   | `/agents/disconnect`   | Gracefully stop a session    |
| WS     | `/ws/agent/{agent_id}` | Real-time node update stream |

---

## 🧠 Flow Control (Node-Based)

Agent logic is defined using JSON-based nodes:

```json
{
  "node_id": "node_1",
  "type": "conversation",
  "prompt": "Ask user their concern",
  "routes": [
    {
      "tool_name": "handle_inquiry",
      "next_node": "node_2",
      "condition": "user wants info"
    }
  ]
}
```

---

### 🔒 WebSocket Authentication Implementation

We've enhanced the WebSocket system with token-based authentication to improve security. Please note these changes when connecting to agent WebSockets:

#### How to Connect to Agent WebSockets

1. When starting an agent via the `/agents/start-agent` endpoint, you'll now receive a `ws_token` in the response:

```json
{
  "status": "success",
  "token": "livekit_token_for_audio",
  "ws_token": "websocket_auth_token",  // Use this for WebSocket connections
  "agent_name": "agent-abc123",
  "room_name": "room-def456",
  "message": "Agent started successfully"
}
```

2. Include this token as a query parameter when connecting to the WebSocket:

```javascript
// Frontend code example
const ws = new WebSocket(`ws://api-url/ws/agent/${agentId}?token=${wsToken}`);
```

#### For Developers

The WebSocket system now implements:
- Token-based authentication
- IP-based rate limiting (max 5 connections per IP)
- Better error handling and connection management
- Connection tracking and stale connection cleanup

If you need to modify the WebSocket authentication logic, check the `WebSocketManager` class in `app/core/ws_manager.py` and the WebSocket route handler in `app/api/routes/ws_routes.py`.

---

## ✨ Quick Fix: LLM Markdown Symbol Removal

To remove all markdown formatting from LLM output (for clean TTS or frontend display), use the following code:
Use it line number 654

```python
import re

def strip_markdown(text: str) -> str:
    """
    Remove common markdown symbols from text.
    Removes headers (#, ##), *, **, _, ~, `, - and markdown links/images.
    """
    text = re.sub(r'#+\s*', '', text)                      # Headers like #, ##
    text = re.sub(r'\s*-\s*', ' ', text)                   # Dashes / bullet points
    text = re.sub(r'[*_~`]+', '', text)                    # Bold, italic, strike, code
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)            # Images
    text = re.sub(r'\[.*?\]\(.*?\)', '', text)             # Links
    return text.strip()

# Usage inside your LLM response processor:
clean_content = strip_markdown(delta.content or "") if delta.content else None
```

---

## 📜 Transcript Logging

Every conversation is stored as a `.json` file under `/transcripts`, using this format:

```
transcript_<room_name>_<timestamp>.json
```

---

## 🛠 TODO

* [ ] Admin dashboard to upload and test flows
* [ ] UI to manage agents and track sessions
* [ ] Multi-language support with Whisper.cpp
* [ ] Integrate fallback logic and error handling

---

## 👨‍💻 Maintainer

**Algo Root Pvt. Ltd**
📧 Email: [hello@algoroot.ai](mailto:hello@algoroot.ai)
🌐 Website: [www.algoroot.ai](https://www.algoroot.ai)

---

## 🛡️ License

This project is private and owned by Algo Root. All rights reserved.

---

Let me know if you want a PDF version of this README or if you'd like to auto-generate docs for your API endpoints.
