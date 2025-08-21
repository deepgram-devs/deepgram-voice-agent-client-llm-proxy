# Multi-Provider Chat Completions Proxy

This component provides an OpenAI-compatible chat completions API that can use multiple LLM providers, including Amazon Bedrock Agents and OpenAI. It's designed to be modular and extensible, allowing you to easily switch between providers or add new ones.

*Note: In order for non-local models to work, you will need to have this proxy server accessible over the internet. You can use tools like ngrok to expose your local server to the internet.*

## Features

- OpenAI-compatible `/v1/chat/completions` endpoint
- Support for multiple LLM providers (Bedrock, OpenAI, and extensible for more)
- Easy provider switching through environment variables or request parameters
- Support for both streaming and non-streaming responses
- Message logging for requests and responses
- Exact matching of OpenAI's response format
- Comprehensive error handling and logging

The proxy will forward the text to your proxy's configured LLM. Specifically, you will point your Voice Agent config's `think` endpoint to your proxy's URL:
```
"think": {
  "endpoint": {
    "url": "https://your-proxy-endpoint.com/v1/chat/completions",
    }
  }
```

## Server Components

### Main Application (`app.py`)
- Flask server implementation
- Request/response handling
- Provider selection and management
- Format conversion
- Error handling

### Provider System (`providers/`)
- Base provider interface (`base.py`)
- Bedrock provider implementation (`bedrock.py`)
- OpenAI provider implementation (`openai.py`)
- Provider factory for easy selection (`__init__.py`)

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

Required variables in `.env` (depending on which providers you want to use):
```
# Provider Selection
# Options: "bedrock", "openai", or leave empty for openai
PROVIDER_NAME=openai

# OpenAI Configuration (required if using OpenAI provider)
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=gpt-4o-mini

# Bedrock Configuration (required if using Bedrock provider)
AGENT_ID=your_bedrock_agent_id
AGENT_ALIAS_ID=your_bedrock_agent_alias_id
AWS_ACCESS_KEY_ID=your_aws_access_key_id
AWS_SECRET_ACCESS_KEY=your_aws_secret_access_key
AWS_REGION=us-east-1

# Logging Configuration (optional)
LOG_LEVEL=INFO
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

# Or download from https://ngrok.com/downloads
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

In this example, you will update your Voice Agent `think` settings like:
```
"think": {
  "endpoint": {
    "url": "https://xxxx-xx-xx-xxx-xx.ngrok-free.app/v1/chat/completions",
    }
  }
```

# Example using OpenAI Python client:
```python
from openai import OpenAI

client = OpenAI(
    base_url="https://xxxx-xx-xx-xxx-xx.ngrok-free.app/v1",
    api_key="not-needed"  # The proxy doesn't check API keys
)

# Using the default provider configured in .env
response = client.chat.completions.create(
    model="gpt-4o-mini",  # Will use the provider's default model
    messages=[
        {"role": "user", "content": "Hello, how can you help me?"}
    ],
    stream=True  # Supports both streaming and non-streaming
)

# Or specify a provider explicitly in the request
response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "user", "content": "Hello, how can you help me?"}
    ],
    stream=True,
    provider="openai"  # Force using the OpenAI provider
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
    "model": "gpt-4o-mini",
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello, how can you help me?"}
    ],
    "stream": false,
    "provider": "openai"  // Optional: explicitly select a provider
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

## Provider API

### List Available Providers

`GET /v1/providers`

Returns information about available providers and their status:

```json
{
    "providers": [
        {
            "name": "bedrock",
            "available": true,
            "default_model": "bedrock-agent"
        },
        {
            "name": "openai",
            "available": true,
            "default_model": "gpt-4o-mini"
        }
    ],
    "default": "openai"
}
```

## Adding New Providers

To add a new provider:

1. Create a new file in the `providers/` directory (e.g., `anthropic.py`)
2. Implement the `CompletionProvider` interface
3. Add the provider to the factory in `providers/__init__.py`
4. Update the environment variables as needed

## Implementation Notes

- Token usage information is not available from Bedrock and will return -1
- Session IDs are generated using UUID4 if not provided
- Error responses follow OpenAI's format for compatibility
- The server sanitizes error messages to prevent information leakage
- AWS credentials are loaded securely from environment variables 
