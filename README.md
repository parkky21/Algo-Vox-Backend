## 🚀 Getting Started

### 1. Clone & Install

```bash
git clone https://github.com/your-org/algo-vox.git
cd algo-vox/backend
pip install -r requirements.txt
````

### 2. Create `.env` file

```env
LIVEKIT_API_KEY=your_livekit_api_key
LIVEKIT_API_SECRET=your_livekit_api_secret
LIVEKIT_URL=wss://yourdomain.livekit.cloud

# Add OpenAI, Google, or Deepgram keys if used
```

### 3. Run the API Server

```bash
uvicorn app.main:app --reload
```

---

## 📡 API Routes

| Method | Endpoint               | Description                    |
| ------ | ---------------------- | ------------------------------ |
| POST   | `/agents/start-agent`  | Start a voice agent session    |
| POST   | `/agents/disconnect`   | Gracefully stop a session      |
| WS     | `/ws/agent/{agent_id}` | Receive real-time node updates |

---

## 💬 Real-time WebSocket Updates

When a user flows through nodes, the backend emits:

```json
{
  "type": "node_switched",
  "agent_id": "uuid",
  "node_id": "node_1"
}
```

Use this to visually update the frontend as the conversation progresses.

---

## 🧠 Flow Control (Node-Based)

Agent logic is driven via a JSON structure:

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

## 📜 Transcript Logging

Every conversation is saved to `/transcripts` with filename:

```
transcript_<room_name>_<timestamp>.json
```

---

## 🛠 TODO

* [ ] Admin dashboard to upload and test flows
* [ ] UI to manage agents and track sessions
* [ ] Multi-language support with Whisper.cpp
* [ ] Integrate fallback logic and advanced error handling

---

## 👨‍💻 Maintainer

**Algo Root Pvt. Ltd**
Email: [hello@algoroot.ai](mailto:hello@algoroot.ai)
Website: [www.algoroot.ai](https://www.algoroot.ai)

---

## 🛡️ License

This project is private and owned by Algo Root. All rights reserved.

```
