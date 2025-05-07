"""
Amazon Bedrock provider for chat completions.
"""
import boto3
import json
import logging
import os
import time
import uuid
from typing import Dict, Any, List, Generator, Optional

from .base import CompletionProvider

logger = logging.getLogger(__name__)

class BedrockProvider(CompletionProvider):
    """Provider for Amazon Bedrock."""
    
    def __init__(self):
        """Initialize the Bedrock provider."""
        self.agent_id = os.getenv("AGENT_ID")
        self.agent_alias_id = os.getenv("AGENT_ALIAS_ID")
        self.region = os.getenv("AWS_REGION", "us-east-1")
        self.client = self._get_bedrock_client()
    
    def _get_bedrock_client(self):
        """Create and return a boto3 bedrock-agent-runtime client."""
        return boto3.client(
            "bedrock-agent-runtime",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=self.region,
        )
    
    def get_name(self) -> str:
        """Return the name of the provider."""
        return "Bedrock"
    
    def get_default_model(self) -> str:
        """Return the default model for this provider."""
        return "bedrock-agent"
    
    def is_available(self) -> bool:
        """Check if this provider is available."""
        return bool(self.agent_id and self.agent_alias_id and 
                   os.getenv("AWS_ACCESS_KEY_ID") and 
                   os.getenv("AWS_SECRET_ACCESS_KEY"))
    
    def _get_last_user_message(self, messages: List[Dict[str, Any]]) -> str:
        """Extract the last user message from the messages list."""
        last_message = next(
            (msg["content"] for msg in reversed(messages) if msg["role"] == "user"),
            None,
        )
        if not last_message:
            raise ValueError("No user message found")
        return last_message
    
    def _process_completion_stream(self, completion_stream) -> str:
        """Process the completion stream and return the full response text."""
        full_response = []

        try:
            logger.info("Starting to process Bedrock completion stream")
            logger.debug(f"Completion stream type: {type(completion_stream)}")

            if not completion_stream:
                logger.warning("Completion stream is empty")
                return "I apologize, but I received no response from the agent. How else can I assist you?"

            for event in completion_stream:
                logger.debug(f"Event type: {type(event)}")
                logger.debug(f"Event content: {event}")

                # Handle trace events
                if "trace" in event:
                    trace_data = (
                        event["trace"].get("trace", {}).get("orchestrationTrace", {})
                    )
                    if "observation" in trace_data:
                        observation = trace_data["observation"]
                        if isinstance(observation, dict) and "finalResponse" in observation:
                            final_text = observation["finalResponse"].get("text", "")
                            if final_text:
                                full_response.append(final_text)

                # Handle direct message chunks
                elif "chunk" in event:
                    try:
                        chunk_content = event["chunk"]["bytes"].decode("utf-8")
                        if chunk_content.strip():
                            try:
                                chunk_data = json.loads(chunk_content)
                                if isinstance(chunk_data, dict) and "content" in chunk_data:
                                    content = chunk_data["content"]
                                    if content.strip():
                                        full_response.append(content)
                            except json.JSONDecodeError:
                                if chunk_content.strip():
                                    full_response.append(chunk_content)
                    except UnicodeDecodeError:
                        try:
                            chunk_content = event["chunk"]["bytes"].decode("latin-1")
                            if chunk_content.strip():
                                full_response.append(chunk_content)
                        except:
                            logger.error("Failed to decode chunk with alternative encoding")

                # Handle direct text or content
                elif "text" in event:
                    text = event["text"]
                    if text and text.strip():
                        full_response.append(text)
                elif "content" in event:
                    content = event["content"]
                    if content and content.strip():
                        full_response.append(content)

        except Exception as e:
            logger.error(f"Error processing completion stream: {e}", exc_info=True)
            return "I apologize, but I encountered an error processing the response. How else can I assist you?"

        if not full_response:
            logger.warning("No response was collected from the stream")
            return "I apologize, but I'm having trouble processing the response. How else can I assist you?"

        result = " ".join(full_response)
        logger.info(f"Final processed response: {result}")
        return result
    
    def get_response(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get a response from Bedrock based on the messages."""
        try:
            # Log the incoming request
            self.log_request(messages)
            
            # Get the last user message
            last_message = self._get_last_user_message(messages)
            
            # Generate a session ID
            session_id = f"session_{str(uuid.uuid4())[:8]}"
            
            # Call Bedrock Agent
            response = self.client.invoke_agent(
                agentId=self.agent_id,
                agentAliasId=self.agent_alias_id,
                sessionId=session_id,
                inputText=last_message,
                enableTrace=True,
            )
            
            # Process the completion stream
            completion_stream = response.get("completion", [])
            response_text = self._process_completion_stream(completion_stream)
            
            # Log the response
            self.log_response(response_text)
            
            return {"content": response_text}
            
        except Exception as e:
            logger.error(f"Error in get_bedrock_response: {str(e)}", exc_info=True)
            return {"content": f"Error: {str(e)}"}
    
    def format_sse_event(self, data: str) -> str:
        """Format a string as a Server-Sent Event."""
        return f"data: {data}\n\n"
    
    def get_streaming_response(self, messages: List[Dict[str, Any]], 
                              completion_id: str, created: int, 
                              model: str) -> Generator[str, None, None]:
        """Get a streaming response from Bedrock."""
        try:
            # Log the incoming request
            self.log_request(messages)
            
            # Initial response with role
            initial_response = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "system_fingerprint": None,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant"},
                        "logprobs": None,
                        "finish_reason": None,
                    }
                ],
            }
            yield self.format_sse_event(json.dumps(initial_response))

            # Get the last user message
            last_message = self._get_last_user_message(messages)
            
            # Generate a session ID
            session_id = f"session_{str(uuid.uuid4())[:8]}"

            # Call Bedrock Agent
            response = self.client.invoke_agent(
                agentId=self.agent_id,
                agentAliasId=self.agent_alias_id,
                sessionId=session_id,
                inputText=last_message,
                enableTrace=True,
            )

            # Process the completion stream
            completion_stream = response.get("completion", [])

            # Track if we've sent any content
            has_sent_content = False

            # Process only chunk events
            for event in completion_stream:
                if "chunk" in event:
                    try:
                        chunk_content = event["chunk"]["bytes"].decode("utf-8")
                        if chunk_content.strip():
                            try:
                                chunk_data = json.loads(chunk_content)
                                if isinstance(chunk_data, dict) and "content" in chunk_data:
                                    content = chunk_data["content"]
                                    if content.strip():
                                        # Log the streaming response
                                        logger.debug(f"Streaming chunk from Bedrock: {content.strip()}")
                                        
                                        yield self.format_sse_event(
                                            json.dumps(
                                                {
                                                    "id": completion_id,
                                                    "object": "chat.completion.chunk",
                                                    "created": created,
                                                    "model": model,
                                                    "system_fingerprint": None,
                                                    "choices": [
                                                        {
                                                            "index": 0,
                                                            "delta": {
                                                                "content": content.strip()
                                                            },
                                                            "logprobs": None,
                                                            "finish_reason": None,
                                                        }
                                                    ],
                                                }
                                            )
                                        )
                                        has_sent_content = True
                            except json.JSONDecodeError:
                                if chunk_content.strip():
                                    yield self.format_sse_event(
                                        json.dumps(
                                            {
                                                "id": completion_id,
                                                "object": "chat.completion.chunk",
                                                "created": created,
                                                "model": model,
                                                "system_fingerprint": None,
                                                "choices": [
                                                    {
                                                        "index": 0,
                                                        "delta": {
                                                            "content": chunk_content.strip()
                                                        },
                                                        "logprobs": None,
                                                        "finish_reason": None,
                                                    }
                                                ],
                                            }
                                        )
                                    )
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
                    "choices": [
                        {
                            "index": 0,
                            "delta": {
                                "content": "I apologize, but I received no response from the agent. How else can I assist you?"
                            },
                            "logprobs": None,
                            "finish_reason": None,
                        }
                    ],
                }
                yield self.format_sse_event(json.dumps(chunk_response))

            # Final chunk with finish_reason
            final_response = {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "system_fingerprint": None,
                "choices": [
                    {"index": 0, "delta": {}, "logprobs": None, "finish_reason": "stop"}
                ],
            }
            yield self.format_sse_event(json.dumps(final_response))
            yield self.format_sse_event("[DONE]")

        except Exception as e:
            logger.error(f"Error in get_streaming_response: {str(e)}", exc_info=True)
            error_response = {
                "error": {"message": str(e), "type": "server_error", "code": 500}
            }
            yield self.format_sse_event(json.dumps(error_response))
