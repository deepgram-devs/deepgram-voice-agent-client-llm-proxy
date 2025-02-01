import requests
import json
import sys
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_streaming_chat_completions(url: str, message: str, is_openai=False):
    """Test streaming chat completions and print each chunk received"""
    
    headers = {
        "Content-Type": "application/json"
    }
    
    if is_openai:
        headers["Authorization"] = f"Bearer {os.getenv('OPENAI_API_KEY')}"
    
    data = {
        "model": "gpt-3.5-turbo" if is_openai else "bedrock-agent",
        "stream": True,
        "messages": [
            {"role": "user", "content": message}
        ]
    }
    
    print(f"\n=== Sending Request to {'OpenAI' if is_openai else 'Bedrock Proxy'} ===")
    print(f"URL: {url}")
    print(f"Request Data: {json.dumps(data, indent=2)}")
    
    try:
        with requests.post(url, json=data, headers=headers, stream=True) as response:
            print(f"\nResponse Status: {response.status_code}")
            print("Response Headers:")
            for key, value in response.headers.items():
                print(f"{key}: {value}")
            
            print("\n=== Received Chunks ===")
            chunk_count = 0
            for line in response.iter_lines():
                if line:
                    # Decode the line
                    text = line.decode('utf-8')
                    chunk_count += 1
                    print(f"\nChunk {chunk_count}:")
                    print(f"Raw: {text}")
                    
                    # If it's a data line, try to parse the JSON
                    if text.startswith('data: '):
                        data_str = text[6:]  # Remove 'data: ' prefix
                        try:
                            if data_str == '[DONE]':
                                print("Received [DONE] marker")
                            else:
                                data = json.loads(data_str)
                                print("Parsed JSON:")
                                print(json.dumps(data, indent=2))
                        except json.JSONDecodeError as e:
                            print(f"Error parsing JSON: {e}")
            
            print(f"\nTotal chunks received: {chunk_count}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)

if __name__ == "__main__":
    # URLs for both APIs
    bedrock_url = "https://d978-2600-1700-aaf0-fa0-73f7-3241-bd48-fa65.ngrok-free.app/v1/chat/completions"
    openai_url = "https://api.openai.com/v1/chat/completions"
    
    # Test messages
    test_messages = [
        "Hello, how are you?",
        "I need technical support",
        "Can you help me make a booking?"
    ]
    
    for message in test_messages:
        print("\n" + "="*80)
        print(f"Testing with message: {message}")
        print("="*80)
        
        # Test OpenAI API first
        print("\nTesting OpenAI API...")
        test_streaming_chat_completions(openai_url, message, is_openai=True)
        
        # Then test our Bedrock proxy
        print("\nTesting Bedrock Proxy...")
        test_streaming_chat_completions(bedrock_url, message, is_openai=False)
        
        print("\n" + "="*80) 