"""
OpenAI provider for chat completions.
"""
import json
import logging
import os
import time
from typing import Dict, Any, List, Generator, Optional

from openai import OpenAI
from .base import CompletionProvider

logger = logging.getLogger(__name__)

class OpenAIProvider(CompletionProvider):
    """Provider for OpenAI."""
    
    def __init__(self):
        """Initialize the OpenAI provider."""
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.default_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.client = self._get_openai_client()
    
    def _get_openai_client(self):
        """Create and return an OpenAI client."""
        return OpenAI(api_key=self.api_key)
    
    def get_name(self) -> str:
        """Return the name of the provider."""
        return "OpenAI"
    
    def get_default_model(self) -> str:
        """Return the default model for this provider."""
        return self.default_model
    
    def is_available(self) -> bool:
        """Check if this provider is available."""
        return bool(self.api_key)
    
    def _process_openai_stream(self, stream) -> str:
        """Process the OpenAI stream and return the full response text."""
        full_response = []
        
        try:
            logger.info("Starting to process OpenAI stream")
            
            if not stream:
                logger.warning("Stream is empty")
                return "I apologize, but I received no response. How else can I assist you?"
            
            for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        full_response.append(delta.content)
        
        except Exception as e:
            logger.error(f"Error processing OpenAI stream: {e}", exc_info=True)
            return "I apologize, but I encountered an error processing the response. How else can I assist you?"
        
        if not full_response:
            logger.warning("No response was collected from the stream")
            return "I apologize, but I'm having trouble processing the response. How else can I assist you?"
        
        result = ''.join(full_response)
        logger.info(f"Final processed response: {result}")
        return result
    
    def get_response(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get a response from OpenAI based on the messages."""
        try:
            # Log the incoming request
            self.log_request(messages)
            
            # Call OpenAI API
            response = self.client.chat.completions.create(
                model=self.default_model,
                messages=messages,
                stream=False
            )
            
            response_text = response.choices[0].message.content
            
            # Log the response
            self.log_response(response_text)
            
            return {"content": response_text}
            
        except Exception as e:
            logger.error(f"Error in get_openai_response: {str(e)}", exc_info=True)
            return {"content": f"Error: {str(e)}"}
    
    def format_sse_event(self, data: str) -> str:
        """Format a string as a Server-Sent Event."""
        return f"data: {data}\n\n"
    
    def get_streaming_response(self, messages: List[Dict[str, Any]], 
                              completion_id: str, created: int, 
                              model: str) -> Generator[str, None, None]:
        """Get a streaming response from OpenAI."""
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
            
            # Call OpenAI API with streaming
            stream = self.client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True
            )
            
            # Track if we've sent any content
            has_sent_content = False
            
            # Collect the full response for logging
            full_response = []
            
            # Process the stream
            for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta.content:
                        # Log the streaming response
                        logger.debug(f"Streaming chunk from OpenAI: {delta.content}")
                        
                        # Collect the content for full response logging
                        full_response.append(delta.content)
                        
                        yield self.format_sse_event(
                            json.dumps({
                                "id": completion_id,
                                "object": "chat.completion.chunk",
                                "created": created,
                                "model": model,
                                "system_fingerprint": None,
                                "choices": [{
                                    "index": 0,
                                    "delta": {
                                        "content": delta.content
                                    },
                                    "logprobs": None,
                                    "finish_reason": None
                                }]
                            })
                        )
                        has_sent_content = True
                    
                    # Check for finish_reason
                    if chunk.choices[0].finish_reason is not None:
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
                                "finish_reason": chunk.choices[0].finish_reason
                            }]
                        }
                        yield self.format_sse_event(json.dumps(final_response))
            
            # If we haven't sent any content, send a placeholder
            if not has_sent_content:
                placeholder_text = "I apologize, but I received no response. How else can I assist you?"
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
                                "content": placeholder_text
                            },
                            "logprobs": None,
                            "finish_reason": None,
                        }
                    ],
                }
                yield self.format_sse_event(json.dumps(chunk_response))
                
                # Set the full response to the placeholder
                full_response = [placeholder_text]
                
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
        
            # Log the complete response
            complete_response = ''.join(full_response)
            self.log_response(complete_response)
            
            yield self.format_sse_event("[DONE]")
            
        except Exception as e:
            logger.error(f"Error in get_streaming_response: {str(e)}", exc_info=True)
            error_message = str(e)
            error_response = {
                "error": {"message": error_message, "type": "server_error", "code": 500}
            }
            # Log the error as the response
            self.log_response(f"Error: {error_message}")
            yield self.format_sse_event(json.dumps(error_response))
