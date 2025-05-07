"""
Base provider interface for chat completions.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Generator, Optional


class CompletionProvider(ABC):
    """Base class for all completion providers."""
    
    @abstractmethod
    def get_name(self) -> str:
        """Return the name of the provider."""
        pass
    
    @abstractmethod
    def get_default_model(self) -> str:
        """Return the default model for this provider."""
        pass
    
    @abstractmethod
    def get_response(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get a non-streaming response from the provider."""
        pass
    
    @abstractmethod
    def get_streaming_response(self, messages: List[Dict[str, Any]], 
                              completion_id: str, created: int, 
                              model: str) -> Generator[str, None, None]:
        """Get a streaming response from the provider."""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is available (has required credentials, etc.)"""
        pass
    
    def log_request(self, messages: List[Dict[str, Any]]) -> None:
        """Log the incoming request messages."""
        import json
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Incoming messages to {self.get_name()}: {json.dumps(messages)}")
    
    def log_response(self, response: Any) -> None:
        """Log the response from the provider."""
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Response from {self.get_name()}: {response}")
