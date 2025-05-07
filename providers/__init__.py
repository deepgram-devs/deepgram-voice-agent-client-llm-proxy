"""
Provider initialization module.
"""
from .base import CompletionProvider
from .bedrock import BedrockProvider
from .openai import OpenAIProvider

__all__ = ["CompletionProvider", "BedrockProvider", "OpenAIProvider"]

# Factory function to get the appropriate provider
def get_provider(provider_name: str = None) -> CompletionProvider:
    """
    Get the appropriate provider based on name and availability.
    
    Args:
        provider_name: The name of the provider to use. If None, will use the first available provider.
        
    Returns:
        An instance of a CompletionProvider
        
    Raises:
        ValueError: If no provider is available or the requested provider is not available
    """
    providers = {
        "bedrock": BedrockProvider,
        "openai": OpenAIProvider,
    }
    
    # If a specific provider is requested, try to use it
    if provider_name:
        provider_name = provider_name.lower()
        if provider_name not in providers:
            raise ValueError(f"Unknown provider: {provider_name}")
        
        provider = providers[provider_name]()
        if not provider.is_available():
            raise ValueError(f"Provider {provider_name} is not available (missing credentials?)")
        
        return provider
    
    # Otherwise, try each provider in order
    for name, provider_class in providers.items():
        try:
            provider = provider_class()
            if provider.is_available():
                return provider
        except Exception:
            continue
    
    # If we get here, no provider is available
    raise ValueError("No provider is available. Please check your environment variables.")
