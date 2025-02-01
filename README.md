# OpenAI-Compatible Proxy Server for Amazon Bedrock Agents

This component provides an OpenAI-compatible chat completions API that internally uses Amazon Bedrock Agents.

## Features

- OpenAI-compatible `/v1/chat/completions` endpoint
- Support for both streaming and non-streaming responses
- Session management for maintaining conversation context
- Exact matching of OpenAI's response format
- Comprehensive error handling and logging

## Server Components

### Main Application (`app.py`)
- Flask server implementation
- Request/response handling
- Bedrock Agent integration
- Format conversion
- Error handling

### Streaming Support
The server implements Server-Sent Events (SSE) streaming that:
- Matches OpenAI's chunk format exactly
- Provides word-by-word streaming
- Handles role and content deltas
- Processes trace events and completion chunks
- Maintains consistent message IDs

### Streaming Test Tool (`test_streaming.py`)
A validation tool that:
- Compares responses with OpenAI's API
- Verifies streaming format compatibility
- Checks chunk formatting and timing
- Validates role and content handling
- Measures streaming performance

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Configure environment:
```bash
cp .env.example .env
```

Required variables in `.env`:
```
# AWS Credentials
AWS_ACCESS_KEY_ID=your_aws_access_key_id
AWS_SECRET_ACCESS_KEY=your_aws_secret_access_key
AWS_REGION=us-east-1

# Agent Configuration
AGENT_ID=your_bedrock_agent_id
AGENT_ALIAS_ID=your_bedrock_agent_alias_id

# Optional: For streaming comparison tests
OPENAI_API_KEY=your_openai_api_key
```

3. Start the server:
```bash
python app.py
```

## Running Locally with ngrok

To make your local server accessible over the internet (useful for testing with external tools):

1. Install ngrok:
```bash
# On Ubuntu/Debian
curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null && echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list && sudo apt update && sudo apt install ngrok

# On macOS with Homebrew
brew install ngrok

# Or download from https://ngrok.com/download
```

2. Sign up at https://ngrok.com and get your authtoken

3. Configure ngrok:
```bash
ngrok config add-authtoken your_auth_token
```

4. Start the Flask server:
```bash
python app.py
```

5. In a new terminal, start ngrok:
```bash
ngrok http 5000
```

6. Use the provided URL:
- ngrok will display a URL like `https://xxxx-xx-xx-xxx-xx.ngrok-free.app`
- Your OpenAI-compatible endpoint will be available at `https://xxxx-xx-xx-xxx-xx.ngrok-free.app/v1/chat/completions`
- You can use this URL in any OpenAI-compatible client by setting the base URL

Example using OpenAI Python client:
```python
from openai import OpenAI

client = OpenAI(
    base_url="https://xxxx-xx-xx-xxx-xx.ngrok-free.app/v1",
    api_key="not-needed"  # The proxy doesn't check API keys
)

response = client.chat.completions.create(
    model="bedrock-agent",  # Model name doesn't matter, will use Bedrock
    messages=[
        {"role": "user", "content": "Hello, how can you help me?"}
    ],
    stream=True  # Supports both streaming and non-streaming
)

for chunk in response:
    print(chunk.choices[0].delta.content or "", end="")
```

Note: The ngrok free tier provides:
- Random URLs that change each time you start ngrok
- Rate limits that should be fine for testing
- For production use, consider ngrok's paid tiers or proper deployment

## API Reference

### Chat Completions

`POST /v1/chat/completions`

#### Request Format
```json
{
    "model": "bedrock-agent",
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, how can you help me?"}
    ],
    "stream": false,
    "session_id": "optional-session-id"
}
```

#### Response Format (Non-Streaming)
```json
{
    "id": "chatcmpl-123abc...",
    "object": "chat.completion",
    "created": 1677858242,
    "model": "bedrock-agent",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "The response from the agent..."
            },
            "finish_reason": "stop"
        }
    ],
    "usage": {
        "prompt_tokens": -1,
        "completion_tokens": -1,
        "total_tokens": -1
    }
}
```

#### Streaming Response Format
When `stream: true`, responses are sent as Server-Sent Events:
```json
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1234567890,"model":"bedrock-agent","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1234567890,"model":"bedrock-agent","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1234567890,"model":"bedrock-agent","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

## Testing

### Run Streaming Format Test
```bash
python test_streaming.py
```

This will:
1. Start a local server instance
2. Send identical requests to both OpenAI and the proxy
3. Compare the streaming responses
4. Validate format compatibility
5. Generate a detailed comparison report

## Implementation Notes

- Token usage information is not available from Bedrock and will return -1
- Session IDs are generated using UUID4 if not provided
- Error responses follow OpenAI's format for compatibility
- The server sanitizes error messages to prevent information leakage
- AWS credentials are loaded securely from environment variables 
