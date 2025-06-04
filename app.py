from flask import Flask, request, jsonify, render_template
from qwen_agent.agents import Assistant
import httpx
import logging
import json
import ssl
import os
import urllib3
import requests
from bs4 import BeautifulSoup
import time
import certifi

app = Flask(__name__)

# --- Configuration from Environment Variables ---
LLM_MODEL_NAME = os.getenv("VLLM_MODEL", "Qwen/Qwen3-30B-A3B-FP8")
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "https://vllm.rangeresources.com/v1/")
VLLM_CHAT_COMPLETIONS_URL = os.getenv("VLLM_CHAT_COMPLETIONS_URL", "https://vllm.rangeresources.com/v1/chat/completions")
VLLM_MODELS_URL = os.getenv("VLLM_MODELS_URL", "https://vllm.rangeresources.com/v1/models")
API_KEY = os.getenv("VLLM_API_KEY", "123456789")
VERIFY_SSL = os.getenv("VLLM_VERIFY_SSL", "False").lower() in ['true', '1', 'yes', 'on']
PLAYWRIGHT_SERVICE_URL = os.getenv("PLAYWRIGHT_SERVICE_URL", "http://playwright-service:3000")

logging.basicConfig(level=logging.INFO)
app.logger.setLevel(logging.INFO)

# --- Enhanced SSL Configuration ---
if not VERIFY_SSL:
    app.logger.info("SSL verification is DISABLED based on VLLM_VERIFY_SSL environment variable")
    
    # Disable SSL warnings
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    # Set environment variables - use certifi bundle as fallback
    os.environ['PYTHONHTTPSVERIFY'] = '0'
    os.environ['CURL_CA_BUNDLE'] = certifi.where()  # Use certifi bundle
    os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()  # Use certifi bundle
    os.environ['SSL_CERT_FILE'] = certifi.where()
    
    # Global SSL context modification
    ssl._create_default_https_context = ssl._create_unverified_context
    
    # Create custom session with proper SSL handling
    import requests
    from requests.adapters import HTTPAdapter
    from requests.packages.urllib3.util.ssl_ import create_urllib3_context
    
    class SSLAdapter(HTTPAdapter):
        def init_poolmanager(self, *args, **kwargs):
            context = create_urllib3_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            kwargs['ssl_context'] = context
            return super().init_poolmanager(*args, **kwargs)
    
    # Create a session with custom SSL adapter
    session = requests.Session()
    session.mount('https://', SSLAdapter())
    session.mount('http://', HTTPAdapter())
    
    # Monkey patch requests to use our session
    old_request = requests.request
    def new_request(method, url, **kwargs):
        kwargs['verify'] = False
        return session.request(method=method, url=url, **kwargs)
    requests.request = new_request
    requests.get = lambda url, **kwargs: new_request('GET', url, **kwargs)
    requests.post = lambda url, **kwargs: new_request('POST', url, **kwargs)
    
    # Patch OpenAI client
    import openai
    original_openai_init = openai.OpenAI.__init__
    def patched_openai_init(self, *args, **kwargs):
        kwargs['http_client'] = httpx.Client(verify=False, timeout=60)
        return original_openai_init(self, *args, **kwargs)
    openai.OpenAI.__init__ = patched_openai_init

else:
    app.logger.info("SSL verification is ENABLED")
    # Even with SSL enabled, ensure we have proper certificates
    os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
    os.environ['SSL_CERT_FILE'] = certifi.where()

# Configure LLM for Qwen-Agent
llm_cfg = {
    "model": LLM_MODEL_NAME,
    "model_server": VLLM_BASE_URL,
    "api_key": API_KEY,
    "generate_cfg": {
        "top_p": 0.8,
        "temperature": 0.7,
        "max_tokens": 2000,
    }
}

app.logger.info(f"LLM Configuration: {llm_cfg}")
app.logger.info(f"SSL Verification: {'DISABLED' if not VERIFY_SSL else 'ENABLED'}")
app.logger.info(f"Playwright Service: {PLAYWRIGHT_SERVICE_URL}")

# Configure Tools
tools_for_assistant = ['code_interpreter']
app.logger.info(f"Tools initialized: {tools_for_assistant}")

# Simplified system prompt that works better with code_interpreter
system_prompt = """You are a helpful AI assistant with web browsing capabilities.

When asked about current information (sports scores, news, weather, etc.), use the code_interpreter tool to search the web.

IMPORTANT: When using code_interpreter, write simple, complete Python code blocks. Here's the correct format:

For web searches, use this template:
```python
import requests
from bs4 import BeautifulSoup
import os

# Configure SSL
os.environ['REQUESTS_CA_BUNDLE'] = ''
os.environ['SSL_CERT_FILE'] = ''

# Search for information
query = "YOUR SEARCH QUERY HERE"

# Direct approach - try specific sports sites
if "score" in query.lower() or "game" in query.lower():
    # Use Playwright service for JavaScript sites
    playwright_url = "http://playwright-service:3000/scrape"
    
    urls_to_try = [
        "https://www.espn.com/nhl/scoreboard",
        "https://www.espn.com/nba/scoreboard", 
        "https://www.thescore.com/nhl/news"
    ]
    
    for url in urls_to_try:
        try:
            print(f"Checking {url}...")
            payload = {"url": url, "action": "content", "timeout": 20000}
            response = requests.post(playwright_url, json=payload, timeout=25, verify=False)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    content = result.get('data', '')
                    soup = BeautifulSoup(content, 'html.parser')
                    text = soup.get_text()
                    
                    # Look for relevant information
                    lines = text.split('\\n')
                    found_info = False
                    
                    for line in lines:
                        line = line.strip()
                        # Look for team names and scores
                        if any(term in line.lower() for term in query.lower().split()):
                            if len(line) > 15:  # Skip very short lines
                                print(f"Found: {line}")
                                found_info = True
                    
                    if found_info:
                        print(f"\\nSuccessfully found information on {url}")
                        break
        except Exception as e:
            print(f"Error with {url}: {str(e)[:50]}")
            continue

# Fallback to simple web search
if not found_info:
    try:
        # Try a simple HTTP request
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        search_url = f"https://www.thescore.com/nhl/news"
        response = requests.get(search_url, headers=headers, timeout=10, verify=False)
        
        if response.status_code == 200:
            print("Fallback search successful")
            # Extract text and look for relevant info
            soup = BeautifulSoup(response.text, 'html.parser')
            text = soup.get_text()[:5000]  # First 5000 chars
            
            # Find relevant lines
            for line in text.split('\\n'):
                if any(term in line.lower() for term in query.lower().split()):
                    print(line.strip()[:200])
    except:
        print("Unable to retrieve current information. Please check official sports websites.")
```

Remember:
1. Always configure SSL settings at the start
2. Use the Playwright service for JavaScript-heavy sites
3. Try multiple sources
4. Handle errors gracefully
5. Print clear results"""

# Test connections
def test_vllm_connection():
    """Test connection to vLLM server"""
    try:
        app.logger.info(f"Testing connection to vLLM models endpoint: {VLLM_MODELS_URL}")
        response = requests.get(VLLM_MODELS_URL, verify=VERIFY_SSL, timeout=10)
        if response.status_code == 200:
            app.logger.info("✅ Successfully connected to vLLM server")
            models = response.json()
            app.logger.info(f"Available models: {[model.get('id', 'unknown') for model in models.get('data', [])]}")
            return True
        else:
            app.logger.error(f"❌ vLLM server returned status code: {response.status_code}")
            return False
    except Exception as e:
        app.logger.error(f"❌ Failed to connect to vLLM server: {e}")
        return False

def test_playwright_service():
    """Test connection to Playwright service"""
    try:
        app.logger.info(f"Testing connection to Playwright service: {PLAYWRIGHT_SERVICE_URL}")
        response = requests.get(f"{PLAYWRIGHT_SERVICE_URL}/health", timeout=10)
        if response.status_code == 200:
            result = response.json()
            app.logger.info(f"✅ Playwright service healthy: {result}")
            return True
        else:
            app.logger.error(f"❌ Playwright service returned status code: {response.status_code}")
            return False
    except Exception as e:
        app.logger.error(f"❌ Failed to connect to Playwright service: {e}")
        return False

# Create Assistant Agent
bot = None
try:
    # Test connections first
    vllm_ok = test_vllm_connection()
    playwright_ok = test_playwright_service()
    
    if vllm_ok:
        # Initialize without the unsupported parameter
        bot = Assistant(
            llm=llm_cfg,
            system_message=system_prompt,
            function_list=tools_for_assistant
        )
        app.logger.info("✅ Assistant agent initialized successfully")
        
        if playwright_ok:
            app.logger.info("✅ Full stack ready: LLM + Playwright service")
        else:
            app.logger.warning("⚠️ LLM ready but Playwright service unavailable")
    else:
        app.logger.error("❌ Cannot initialize Assistant agent - vLLM connection failed")
except Exception as e:
    app.logger.error(f"❌ Failed to initialize Assistant agent: {e}", exc_info=True)


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health')
def health():
    """Health check endpoint"""
    vllm_status = test_vllm_connection()
    playwright_status = test_playwright_service()
    
    return jsonify({
        "status": "healthy" if bot and vllm_status else "unhealthy",
        "agent": "initialized" if bot else "not_initialized",
        "vllm": "connected" if vllm_status else "disconnected", 
        "playwright": "connected" if playwright_status else "disconnected",
        "web_scraping": "playwright-service",
        "timestamp": time.time()
    }), 200 if (bot and vllm_status) else 503

@app.route('/chat', methods=['POST'])
def chat():
    if not bot:
        app.logger.error("Chat request received, but Assistant agent is not initialized.")
        return jsonify({"error": "Agent not initialized. Check backend logs and vLLM connection."}), 500

    try:
        data = request.json
        user_query = data.get('query')

        if not user_query:
            return jsonify({"error": "No query provided"}), 400

        app.logger.info(f"Received query: {user_query}")

        current_messages = [{'role': 'user', 'content': user_query}]
        
        start_time = time.time()
        timeout = 60  # 60 seconds timeout
        
        app.logger.info("🔄 Starting response generation...")
        
        try:
            all_message_batches = []
            for batch in bot.run(messages=current_messages):
                all_message_batches.append(batch)
                if time.time() - start_time > timeout:
                    app.logger.warning("⚠️ Response generation timeout")
                    break
            
            all_messages = []
            for batch in all_message_batches:
                all_messages.extend(batch)
            
            app.logger.info(f"✅ Total messages collected: {len(all_messages)}")
            
            latest_assistant_content = ""  # Will store the content of the LAST assistant message
            code_output_parts = []
            errors_encountered = False
            
            for msg in all_messages:
                role = msg.get('role', '')
                
                if role == 'assistant':
                    content = msg.get('content', '')
                    current_message_text = ""
                    if isinstance(content, str):
                        current_message_text = content.strip()
                    elif isinstance(content, list):
                        parts = []
                        for item in content:
                            if isinstance(item, dict) and item.get('type') == 'text':
                                parts.append(item.get('text', ''))
                        current_message_text = "".join(parts).strip() # Join parts without adding extra newlines here
                    
                    # If this message has actual content and is not a skippable/error line,
                    # consider it as the current candidate for the final response.
                    if current_message_text and not any(skip in current_message_text for skip in [
                            'Invalid json', 'TypeError:', 'ValueError:', 
                            'PermissionError:', 'Exception reporting mode',
                            'UserWarning:', 'IPython parent' # Add any other undesirable intermediate outputs
                        ]):
                        latest_assistant_content = current_message_text # Overwrite with the latest valid assistant message

                elif role == 'tool_outputs':
                    outputs = msg.get('content', [])
                    for output_item in outputs:
                        output_text = str(output_item.get('output', ''))
                        
                        if any(err in output_text.lower() for err in ['error:', 'failed', 'exception:']): # Make error check case-insensitive
                            errors_encountered = True
                        
                        # Extract useful output from tools
                        if output_text and len(output_text) > 5: # Reduced length check slightly
                            lines = output_text.split('\n')
                            for line in lines:
                                line = line.strip()
                                if line and not any(skip.lower() in line.lower() for skip in [
                                    'exception reporting', 'traceback', 'file "',
                                    'userwarning', 'ipython parent', '--- Logging error ---'
                                ]):
                                    # Be more selective or ensure formatting if adding to code_output_parts
                                    if any(keep.lower() in line.lower() for keep in ['found:', 'checking', 'successful', 'score:', 'result:']):
                                        code_output_parts.append(line)
                                    # You might want to add other relevant tool outputs as well.

            processing_time = time.time() - start_time
            app.logger.info(f"✅ Response processing completed in {processing_time:.2f}s")

            final_text = latest_assistant_content.strip()
            code_output = "\n".join(code_output_parts).strip()
            
            # Construct the final response
            if not final_text or len(final_text) < 20: # If assistant's final response is too short or empty
                if code_output and not errors_encountered:
                    final_text = "Based on my search:\n\n" + code_output
                elif errors_encountered: # Prioritize error message if errors occurred
                    final_text = "I encountered some issues while searching for that information. "
                    final_text += "For the most current sports scores, I recommend checking:\n"
                    final_text += "- ESPN.com\n- TheScore.com\n- Official team websites"
                # Fallback if no good assistant response and no useful code_output
                elif not final_text or len(final_text) < 20 : # Check again if final_text is still bad
                     final_text = "I attempted to search for that information but couldn't retrieve current results. "
                     final_text += "For real-time sports scores and information, please check official sources like ESPN or TheScore."


        except Exception as e:
            app.logger.error(f"❌ Error during bot.run() or message processing: {e}", exc_info=True)
            final_text = "I encountered an error while processing your request. Please try again with a simpler question."

        app.logger.info(f"✅ Sending response - Length: {len(final_text)} characters")
        # Ensure final_text is not empty before sending
        if not final_text:
             final_text = "I'm sorry, I couldn't generate a response. Please try again."
        
        return jsonify({"response": final_text})

    except Exception as e:
        app.logger.error(f"❌ Unhandled error in /chat endpoint: {e}", exc_info=True)
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)