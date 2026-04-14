# 🤖 Real-Time AI Chatbot Backend

A **production-ready**, streaming chatbot API built with **FastAPI** and **Groq** (LLaMA 3).  
Supports multi-turn conversations, Server-Sent Events (SSE) streaming, and clean modular architecture.

---

## 📁 Project Structure

```
chatbot-backend/
├── app/
│   ├── __init__.py
│   ├── main.py               ← FastAPI app + CORS + lifespan
│   ├── routes.py             ← All API endpoints
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py        ← Pydantic request/response models
│   ├── services/
│   │   ├── __init__.py
│   │   └── groq_service.py   ← Groq API integration (streaming + non-streaming)
│   └── utils/
│       ├── __init__.py
│       └── memory.py         ← In-memory conversation history manager
├── .env.example              ← Environment variable template
├── requirements.txt          ← Python dependencies
└── README.md
```

---

## ⚙️ Setup

### 1. Clone / download the project

```bash
git clone <your-repo-url>
cd chatbot-backend
```

### 2. Create and activate a virtual environment

```bash
# Create venv
python -m venv venv

# Activate (Mac/Linux)
source venv/bin/activate

# Activate (Windows)
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and paste your Groq API key:

```env
GROQ_API_KEY=gsk_your_actual_key_here
```

> Get a **free** API key at [https://console.groq.com](https://console.groq.com)

---

## 🚀 Running the Server

### Development (with auto-reload)

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Production

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

The server starts at **http://localhost:8000**  
Interactive API docs at **http://localhost:8000/docs**

---

## 📡 API Reference

### Base URL

```
http://localhost:8000/api/v1
```

---

### `POST /chat` — Send a message

**Request body:**

```json
{
  "message": "Explain quantum entanglement simply.",
  "session_id": "my-session-123",
  "model": "llama3-70b-8192",
  "system_prompt": "You are a physics tutor.",
  "temperature": 0.7,
  "max_tokens": 1024,
  "stream": true
}
```

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `message` | string | ✅ | — | User's message |
| `session_id` | string | ❌ | auto-generated UUID | Session for conversation memory |
| `model` | string | ❌ | `llama3-70b-8192` | Groq model to use |
| `system_prompt` | string | ❌ | helpful assistant | Overrides default system persona |
| `temperature` | float | ❌ | `0.7` | Creativity (0.0 – 2.0) |
| `max_tokens` | int | ❌ | `1024` | Max reply length |
| `stream` | bool | ❌ | `true` | SSE stream vs full JSON |

---

### `GET /history/{session_id}` — Get conversation history

Returns all messages for a session.

---

### `DELETE /history/{session_id}` — Clear a session

Removes the session from memory.

---

### `GET /sessions` — List active sessions (debug)

Returns all session IDs currently in memory.

---

### `GET /models` — List supported models

Returns available Groq model IDs.

---

## 🧪 Example Requests

### Streaming chat (curl)

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is the capital of France?",
    "stream": true
  }' \
  --no-buffer
```

**Example SSE stream output:**

```
data: {"session_id": "f3a2b1c4-..."}

data: {"chunk": "The"}

data: {"chunk": " capital"}

data: {"chunk": " of"}

data: {"chunk": " France"}

data: {"chunk": " is"}

data: {"chunk": " Paris."}

data: [DONE]
```

---

### Non-streaming chat (curl)

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Tell me a fun fact about space.",
    "stream": false
  }'
```

**Example JSON response:**

```json
{
  "session_id": "f3a2b1c4-d5e6-7890-abcd-ef1234567890",
  "message": "Here is a fun fact: a day on Venus is longer than a year on Venus! ...",
  "model": "llama3-70b-8192",
  "usage": {
    "prompt_tokens": 42,
    "completion_tokens": 87,
    "total_tokens": 129
  }
}
```

---

### Multi-turn conversation (curl)

```bash
# Turn 1 – start a session
SESSION=$(curl -s -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "My name is Alice.", "stream": false}' | jq -r '.session_id')

echo "Session: $SESSION"

# Turn 2 – follow-up in the same session
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"What is my name?\", \"session_id\": \"$SESSION\", \"stream\": false}"
```

---

### Get history

```bash
curl http://localhost:8000/api/v1/history/f3a2b1c4-d5e6-7890-abcd-ef1234567890
```

### Delete session

```bash
curl -X DELETE http://localhost:8000/api/v1/history/f3a2b1c4-d5e6-7890-abcd-ef1234567890
```

---

## 🌐 JavaScript / Frontend Integration

```javascript
const response = await fetch("http://localhost:8000/api/v1/chat", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    message: "Hello!",
    session_id: "user-session-001",
    stream: true,
  }),
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;

  const text = decoder.decode(value);
  for (const line of text.split("\n")) {
    if (line.startsWith("data: ")) {
      const raw = line.slice(6).trim();
      if (raw === "[DONE]") break;
      const payload = JSON.parse(raw);
      if (payload.chunk) process.stdout.write(payload.chunk); // or update DOM
    }
  }
}
```

---

## 🔧 Available Groq Models

| Model ID | Description |
|---|---|
| `llama3-70b-8192` | LLaMA 3 70B – best quality, 8k context |
| `llama3-8b-8192` | LLaMA 3 8B – fastest, 8k context |
| `mixtral-8x7b-32768` | Mixtral 8×7B MoE – 32k context |
| `gemma2-9b-it` | Google Gemma 2 9B instruction-tuned |

---

## 🔒 Production Checklist

- [ ] Set `GROQ_API_KEY` in a secrets manager (not in a committed `.env`)
- [ ] Replace `allow_origins=["*"]` with your actual frontend domain in `main.py`
- [ ] Add authentication middleware (JWT / API key header)
- [ ] Swap in-memory `ConversationMemory` with Redis or a database
- [ ] Enable HTTPS via a reverse proxy (Nginx / Caddy / AWS ALB)
- [ ] Add rate limiting (`slowapi` library works great with FastAPI)
- [ ] Run with `--workers N` matching your CPU core count

---

## 📄 License

MIT — free to use and modify.
