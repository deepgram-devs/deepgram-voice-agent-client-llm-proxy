from flask import Flask, request, jsonify, Response, stream_with_context
from dotenv import load_dotenv
import os
import uuid
import time
import json
import logging
from typing import Dict, Any, List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
# Reduce logging from watchdog and other verbose libraries
logging.getLogger("watchdog").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Import our provider system
from providers import get_provider

# Create Flask app
app = Flask(__name__)

# Custom JSON encoder
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        return super().default(obj)

app.json_encoder = CustomJSONEncoder

# Get the configured provider name from environment, default to openai
PROVIDER_NAME = os.getenv("PROVIDER_NAME", "openai")

def create_chat_completion_response(response_text: str, model: str) -> Dict[str, Any]:
    """Create a chat completion response in OpenAI format"""
    return {
        "id": f"chatcmpl-{str(uuid.uuid4())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": response_text},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": -1, "completion_tokens": -1, "total_tokens": -1},
    }

def stream_chat_completion(data):
    """Handle streaming chat completion requests"""
    messages = data.get("messages", [])
    model = data.get("model", "gpt-4o-mini")
    provider_override = data.get("provider")
    
    # Get the appropriate provider
    try:
        provider = get_provider(provider_override or PROVIDER_NAME)
        logger.info(f"Using provider: {provider.get_name()}")
        
        # If model is not specified explicitly, use the provider's default
        if model == "gpt-4o-mini" and not data.get("model"):
            model = provider.get_default_model()
    except ValueError as e:
        logger.error(f"Provider error: {str(e)}")
        yield f"data: {json.dumps({'error': {'message': str(e), 'type': 'provider_error', 'code': 500}})}\n\n"
        return
    
    # Generate a unique ID for this completion
    completion_id = f"chatcmpl-{str(uuid.uuid4())}"
    created = int(time.time())
    
    # Get streaming response from provider
    try:
        for event in provider.get_streaming_response(messages, completion_id, created, model):
            yield event
    except Exception as e:
        logger.error(f"Error in stream_chat_completion: {str(e)}", exc_info=True)
        error_response = {
            "error": {"message": str(e), "type": "server_error", "code": 500}
        }
        yield f"data: {json.dumps(error_response)}\n\n"

@app.route("/v1/chat/completions", methods=["POST"])
def chat_completions():
    """Handle chat completion requests"""
    try:
        data = request.json
        logger.info(f"Received chat completion request: {data}")
        
        # Extract parameters from the request
        messages = data.get("messages", [])
        model = data.get("model", "gpt-4o-mini")
        stream = data.get("stream", False)
        provider_override = data.get("provider")
        
        # Validate messages
        if not messages or not any(msg.get("role") == "user" for msg in messages):
            return jsonify({"error": "No user message found"}), 400
        
        # Get the appropriate provider
        try:
            provider = get_provider(provider_override or PROVIDER_NAME)
            logger.info(f"Using provider: {provider.get_name()}")
            
            # If model is not specified explicitly, use the provider's default
            if model == "gpt-4o-mini" and not data.get("model"):
                model = provider.get_default_model()
        except ValueError as e:
            logger.error(f"Provider error: {str(e)}")
            return jsonify({"error": str(e)}), 500
        
        try:
            if stream:
                logger.info("Processing as streaming response")
                # Return streaming response
                return Response(
                    stream_with_context(stream_chat_completion(data)),
                    mimetype="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "Content-Type": "text/event-stream",
                        "X-Accel-Buffering": "no",
                    },
                )
            else:
                logger.info("Processing as non-streaming response")
                # Get response from provider
                response_obj = provider.get_response(messages)
                response_text = response_obj.get("content", "")
                
                return jsonify(create_chat_completion_response(response_text, model))
            
        except Exception as e:
            logger.error(f"Error processing response: {str(e)}", exc_info=True)
            return jsonify({"error": f"Error processing response: {str(e)}"}), 500
    
    except Exception as e:
        logger.error(f"Error in chat completions: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@app.route("/v1/providers", methods=["GET"])
def list_providers():
    """List available providers"""
    from providers import BedrockProvider, OpenAIProvider
    
    providers = []
    
    # Check Bedrock
    try:
        bedrock = BedrockProvider()
        providers.append({
            "name": "bedrock",
            "available": bedrock.is_available(),
            "default_model": bedrock.get_default_model() if bedrock.is_available() else None
        })
    except Exception as e:
        providers.append({
            "name": "bedrock",
            "available": False,
            "error": str(e)
        })
    
    # Check OpenAI
    try:
        openai = OpenAIProvider()
        providers.append({
            "name": "openai",
            "available": openai.is_available(),
            "default_model": openai.get_default_model() if openai.is_available() else None
        })
    except Exception as e:
        providers.append({
            "name": "openai",
            "available": False,
            "error": str(e)
        })
    
    return jsonify({
        "providers": providers,
        "default": PROVIDER_NAME or "openai"
    })

if __name__ == "__main__":
    # Try to initialize the default provider to catch any issues early
    try:
        provider = get_provider(PROVIDER_NAME)
        logger.info(f"Using provider: {provider.get_name()} with default model: {provider.get_default_model()}")
    except ValueError as e:
        logger.warning(f"Provider warning: {str(e)}")
        logger.warning("The application will still start, but requests may fail if no provider is available.")
    
    app.run(host="0.0.0.0", port=5005)
