from flask import Flask, request, jsonify, Response, stream_with_context
import boto3
from dotenv import load_dotenv
import os
import uuid
import time
from typing import List, Dict, Any
import json
from botocore.eventstream import EventStream
import logging
import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
# Reduce logging from watchdog and other verbose libraries
logging.getLogger('watchdog').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('werkzeug').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

app = Flask(__name__)

# Load environment variables
load_dotenv()

# Constants
AGENT_ID = os.getenv('AGENT_ID')
AGENT_ALIAS_ID = os.getenv('AGENT_ALIAS_ID')

if not AGENT_ID or not AGENT_ALIAS_ID:
    raise ValueError("AGENT_ID and AGENT_ALIAS_ID must be set in environment variables")

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, EventStream):
            return "EventStream"
        return super().default(obj)

app.json_encoder = CustomJSONEncoder

def get_bedrock_client():
    """Create and return a boto3 bedrock-agent-runtime client"""
    region = os.getenv('AWS_REGION', 'us-east-1')  # Default to us-east-1 if not specified
    return boto3.client(
        'bedrock-agent-runtime',
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        region_name=region
    )

def format_sse_event(data: str) -> str:
    """Format a string as a Server-Sent Event"""
    return f"data: {data}\n\n"

def process_completion_stream(completion_stream) -> str:
    """Process the completion stream and return the full response text"""
    full_response = []
    
    try:
        logger.info("Starting to process completion stream")
        logger.debug(f"Completion stream type: {type(completion_stream)}")
        
        if not completion_stream:
            logger.warning("Completion stream is empty")
            return "I apologize, but I received no response from the agent. How else can I assist you?"
        
        for event in completion_stream:
            logger.debug(f"Event type: {type(event)}")
            logger.debug(f"Event content: {event}")
            
            # Handle trace events
            if 'trace' in event:
                trace_data = event['trace'].get('trace', {}).get('orchestrationTrace', {})
                if 'observation' in trace_data:
                    observation = trace_data['observation']
                    if isinstance(observation, dict) and 'finalResponse' in observation:
                        final_text = observation['finalResponse'].get('text', '')
                        if final_text:
                            full_response.append(final_text)
            
            # Handle direct message chunks
            elif 'chunk' in event:
                try:
                    chunk_content = event['chunk']['bytes'].decode('utf-8')
                    if chunk_content.strip():
                        try:
                            chunk_data = json.loads(chunk_content)
                            if isinstance(chunk_data, dict) and 'content' in chunk_data:
                                content = chunk_data['content']
                                if content.strip():
                                    full_response.append(content)
                        except json.JSONDecodeError:
                            if chunk_content.strip():
                                full_response.append(chunk_content)
                except UnicodeDecodeError:
                    try:
                        chunk_content = event['chunk']['bytes'].decode('latin-1')
                        if chunk_content.strip():
                            full_response.append(chunk_content)
                    except:
                        logger.error("Failed to decode chunk with alternative encoding")
            
            # Handle direct text or content
            elif 'text' in event:
                text = event['text']
                if text and text.strip():
                    full_response.append(text)
            elif 'content' in event:
                content = event['content']
                if content and content.strip():
                    full_response.append(content)
    
    except Exception as e:
        logger.error(f"Error processing completion stream: {e}", exc_info=True)
        return "I apologize, but I encountered an error processing the response. How else can I assist you?"
    
    if not full_response:
        logger.warning("No response was collected from the stream")
        return "I apologize, but I'm having trouble processing the response. How else can I assist you?"
    
    result = ' '.join(full_response)
    logger.info(f"Final processed response: {result}")
    return result

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
                "message": {
                    "role": "assistant",
                    "content": response_text
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

def get_bedrock_response(messages):
    """Get a response from Bedrock based on the messages"""
    try:
        # Get the last user message
        last_message = next((msg['content'] for msg in reversed(messages) 
                           if msg['role'] == 'user'), None)
        
        if not last_message:
            raise ValueError("No user message found")
        
        # Create Bedrock client
        client = get_bedrock_client()
        
        # Generate a session ID
        session_id = f"session_{str(uuid.uuid4())[:8]}"
        
        # Call Bedrock Agent
        response = client.invoke_agent(
            agentId=AGENT_ID,
            agentAliasId=AGENT_ALIAS_ID,
            sessionId=session_id,
            inputText=last_message,
            enableTrace=True
        )
        
        # Process the completion stream
        completion_stream = response.get('completion', [])
        response_text = process_completion_stream(completion_stream)
        
        return {"content": response_text}
        
    except Exception as e:
        logger.error(f"Error in get_bedrock_response: {str(e)}", exc_info=True)
        return {"content": f"Error: {str(e)}"}

def stream_chat_completion(data):
    messages = data.get('messages', [])
    model = "bedrock-agent"
    
    # Generate a unique ID for this completion
    completion_id = f"chatcmpl-{str(uuid.uuid4())}"
    created = int(time.time())
    
    try:
        # Initial response with role
        initial_response = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "system_fingerprint": None,
            "choices": [{
                "index": 0,
                "delta": {
                    "role": "assistant"
                },
                "logprobs": None,
                "finish_reason": None
            }]
        }
        yield format_sse_event(json.dumps(initial_response))

        # Get response from Bedrock
        client = get_bedrock_client()
        session_id = data.get('session_id', f"session_{str(uuid.uuid4())[:8]}")
        
        # Get the last user message
        last_message = next((msg['content'] for msg in reversed(messages) 
                           if msg['role'] == 'user'), None)
        
        if not last_message:
            error_response = {
                "error": {
                    "message": "No user message found",
                    "type": "invalid_request_error",
                    "code": 400
                }
            }
            yield format_sse_event(json.dumps(error_response))
            return

        # Call Bedrock Agent
        response = client.invoke_agent(
            agentId=AGENT_ID,
            agentAliasId=AGENT_ALIAS_ID,
            sessionId=session_id,
            inputText=last_message,
            enableTrace=True
        )
        
        # Process the completion stream
        completion_stream = response.get('completion', [])
        
        # Track if we've sent any content
        has_sent_content = False
        
        # Process only chunk events
        for event in completion_stream:
            if 'chunk' in event:
                try:
                    chunk_content = event['chunk']['bytes'].decode('utf-8')
                    if chunk_content.strip():
                        try:
                            chunk_data = json.loads(chunk_content)
                            if isinstance(chunk_data, dict) and 'content' in chunk_data:
                                content = chunk_data['content']
                                if content.strip():
                                    yield format_sse_event(json.dumps({
                                        "id": completion_id,
                                        "object": "chat.completion.chunk",
                                        "created": created,
                                        "model": model,
                                        "system_fingerprint": None,
                                        "choices": [{
                                            "index": 0,
                                            "delta": {
                                                "content": content.strip()
                                            },
                                            "logprobs": None,
                                            "finish_reason": None
                                        }]
                                    }))
                                    has_sent_content = True
                        except json.JSONDecodeError:
                            if chunk_content.strip():
                                yield format_sse_event(json.dumps({
                                    "id": completion_id,
                                    "object": "chat.completion.chunk",
                                    "created": created,
                                    "model": model,
                                    "system_fingerprint": None,
                                    "choices": [{
                                        "index": 0,
                                        "delta": {
                                            "content": chunk_content.strip()
                                        },
                                        "logprobs": None,
                                        "finish_reason": None
                                    }]
                                }))
                                has_sent_content = True
                except Exception as e:
                    logger.error(f"Error processing chunk: {e}")
        
        # If we haven't sent any content, send a placeholder
        if not has_sent_content:
            chunk_response = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "system_fingerprint": None,
                "choices": [{
                    "index": 0,
                    "delta": {
                        "content": "I apologize, but I received no response from the agent. How else can I assist you?"
                    },
                    "logprobs": None,
                    "finish_reason": None
                }]
            }
            yield format_sse_event(json.dumps(chunk_response))
        
        # Final chunk with finish_reason
        final_response = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "system_fingerprint": None,
            "choices": [{
                "index": 0,
                "delta": {},
                "logprobs": None,
                "finish_reason": "stop"
            }]
        }
        yield format_sse_event(json.dumps(final_response))
        yield format_sse_event("[DONE]")
        
    except Exception as e:
        error_response = {
            "error": {
                "message": str(e),
                "type": "server_error",
                "code": 500
            }
        }
        yield format_sse_event(json.dumps(error_response))

@app.route('/v1/chat/completions', methods=['POST'])
def chat_completions():
    try:
        data = request.json
        logger.info(f"Received chat completion request: {data}")
        
        # Extract parameters from the request
        messages = data.get('messages', [])
        # Always use bedrock-agent as the model name
        model = "bedrock-agent"
        stream = data.get('stream', False)
        
        # Get the last user message
        last_message = next((msg['content'] for msg in reversed(messages) 
                           if msg['role'] == 'user'), None)
        
        if not last_message:
            return jsonify({"error": "No user message found"}), 400
        
        # Create Bedrock client
        client = get_bedrock_client()
        
        # Generate a session ID if not provided
        session_id = data.get('session_id', f"session_{str(uuid.uuid4())[:8]}")
        logger.info(f"Using session ID: {session_id}")
        
        try:
            # Call Bedrock Agent
            logger.info(f"Calling Bedrock Agent with message: {last_message}")
            response = client.invoke_agent(
                agentId=AGENT_ID,
                agentAliasId=AGENT_ALIAS_ID,
                sessionId=session_id,
                inputText=last_message,
                enableTrace=True
            )
            
            logger.info("Got response from Bedrock Agent")
            logger.debug(f"Response keys: {response.keys()}")
            logger.debug(f"Raw response: {response}")
            
            if stream:
                logger.info("Processing as streaming response")
                # Return streaming response
                return Response(
                    stream_with_context(stream_chat_completion(data)),
                    mimetype='text/event-stream',
                    headers={
                        'Cache-Control': 'no-cache',
                        'Connection': 'keep-alive',
                        'Content-Type': 'text/event-stream',
                        'X-Accel-Buffering': 'no'
                    }
                )
            else:
                logger.info("Processing as non-streaming response")
                # Return non-streaming response
                completion_stream = response.get('completion', [])
                logger.debug(f"Completion stream: {completion_stream}")
                response_text = process_completion_stream(completion_stream)
                
                return jsonify(create_chat_completion_response(response_text, "bedrock-agent"))
            
        except Exception as e:
            logger.error(f"Error processing Bedrock response: {str(e)}", exc_info=True)
            return jsonify({"error": f"Error processing response: {str(e)}"}), 500
    
    except Exception as e:
        logger.error(f"Error in chat completions: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000) 