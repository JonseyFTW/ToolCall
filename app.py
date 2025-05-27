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

# --- SSL Configuration based on environment ---
if not VERIFY_SSL:
    app.logger.info("SSL verification is DISABLED based on VLLM_VERIFY_SSL environment variable")
    
    # Disable SSL warnings
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    # Set environment variables
    os.environ['PYTHONHTTPSVERIFY'] = '0'
    os.environ['CURL_CA_BUNDLE'] = ''
    os.environ['REQUESTS_CA_BUNDLE'] = ''
    
    # Global SSL context modification
    ssl._create_default_https_context = ssl._create_unverified_context
    
    # Monkey patch httpx and requests globally
    import requests
    from requests.adapters import HTTPAdapter
    
    class InsecureHTTPAdapter(HTTPAdapter):
        def init_poolmanager(self, *args, **kwargs):
            import ssl
            kwargs['ssl_context'] = ssl.create_default_context()
            kwargs['ssl_context'].check_hostname = False
            kwargs['ssl_context'].verify_mode = ssl.CERT_NONE
            return super().init_poolmanager(*args, **kwargs)
    
    # Create a session with disabled SSL verification
    session = requests.Session()
    session.mount('https://', InsecureHTTPAdapter())
    session.mount('http://', InsecureHTTPAdapter())
    
    # Monkey patch requests module
    original_request = requests.request
    def patched_request(*args, **kwargs):
        kwargs['verify'] = False
        return original_request(*args, **kwargs)
    requests.request = patched_request
    requests.get = lambda *args, **kwargs: patched_request('GET', *args, **kwargs)
    requests.post = lambda *args, **kwargs: patched_request('POST', *args, **kwargs)
    
    # Patch OpenAI client before importing qwen_agent
    import openai
    original_openai_init = openai.OpenAI.__init__
    def patched_openai_init(self, *args, **kwargs):
        kwargs['http_client'] = httpx.Client(verify=False, timeout=60)
        return original_openai_init(self, *args, **kwargs)
    openai.OpenAI.__init__ = patched_openai_init

else:
    app.logger.info("SSL verification is ENABLED")

# Configure LLM for Qwen-Agent
llm_cfg = {
    "model": LLM_MODEL_NAME,
    "model_server": VLLM_BASE_URL,
    "api_key": API_KEY,
    "generate_cfg": {
        "top_p": 0.8,
    }
}

app.logger.info(f"LLM Configuration: {llm_cfg}")
app.logger.info(f"SSL Verification: {'DISABLED' if not VERIFY_SSL else 'ENABLED'}")
app.logger.info(f"Playwright Service: {PLAYWRIGHT_SERVICE_URL}")

# Configure Tools
tools_for_assistant = ['code_interpreter']
app.logger.info(f"Tools initialized: {tools_for_assistant}")

# Enhanced system prompt with Playwright service integration
system_prompt = (
    "You are a helpful AI assistant with advanced web browsing capabilities. Your primary goal is to answer the user's questions accurately. "
    "If you don't know the answer, or if the question requires up-to-date information "
    "(e.g., current events, recent data, specific website content), "
    "you MUST use the 'code_interpreter' tool. "
    "\n"
    "For web browsing, you have access to a professional Playwright service that can handle JavaScript-heavy websites. "
    "Use this Python code template for web scraping:\n"
    "```python\n"
    "import requests\n"
    "import json\n"
    "from bs4 import BeautifulSoup\n\n"
    "# Playwright service URL (enterprise-grade browser automation)\n"
    "PLAYWRIGHT_SERVICE = 'http://playwright-service:3000'\n\n"
    "def scrape_with_playwright(url, action='content'):\n"
    "    \"\"\"Use enterprise Playwright service for reliable web scraping\"\"\"\n"
    "    try:\n"
    "        response = requests.post(f'{PLAYWRIGHT_SERVICE}/scrape', \n"
    "                               json={\n"
    "                                   'url': url,\n"
    "                                   'action': action,  # 'content', 'text', 'title'\n"
    "                                   'timeout': 15000\n"
    "                               }, \n"
    "                               timeout=30)\n"
    "        response.raise_for_status()\n"
    "        result = response.json()\n"
    "        \n"
    "        if result.get('success'):\n"
    "            return result.get('data')\n"
    "        else:\n"
    "            print(f'Playwright error: {result.get(\"error\")}')\n"
    "            return None\n"
    "    except Exception as e:\n"
    "        print(f'Error calling Playwright service: {e}')\n"
    "        return None\n\n"
    "# Example usage for sports scores:\n"
    "print('Fetching NBA scores from ESPN...')\n"
    "espn_html = scrape_with_playwright('https://www.espn.com/nba/scoreboard')\n"
    "\n"
    "if espn_html:\n"
    "    soup = BeautifulSoup(espn_html, 'html.parser')\n"
    "    print(f'Page title: {soup.title.string if soup.title else \"No title\"}')\n"
    "    \n"
    "    # Look for Thunder/OKC games\n"
    "    page_text = soup.get_text().lower()\n"
    "    if 'thunder' in page_text or 'okc' in page_text or 'oklahoma city' in page_text:\n"
    "        print('Found Thunder game information!')\n"
    "        \n"
    "        # Extract game information\n"
    "        game_elements = soup.find_all(['div', 'span', 'p'], \n"
    "                                    string=lambda text: text and \n"
    "                                    ('thunder' in text.lower() or 'okc' in text.lower()))\n"
    "        \n"
    "        for element in game_elements[:5]:  # First 5 matches\n"
    "            # Get parent container for more context\n"
    "            parent = element.find_parent(['div', 'section', 'article'])\n"
    "            if parent:\n"
    "                context = parent.get_text(strip=True)[:200]  # First 200 chars\n"
    "                print(f'Thunder mention: {context}')\n"
    "    else:\n"
    "        print('No Thunder games found on current scoreboard')\n"
    "        print('Trying alternative approach...')\n"
    "        \n"
    "        # Look for recent games or alternative sources\n"
    "        alt_url = 'https://www.nba.com/thunder/schedule'\n"
    "        thunder_page = scrape_with_playwright(alt_url)\n"
    "        if thunder_page:\n"
    "            soup2 = BeautifulSoup(thunder_page, 'html.parser')\n"
    "            print(f'Thunder schedule page loaded: {soup2.title.string if soup2.title else \"No title\"}')\n"
    "else:\n"
    "    print('Failed to load ESPN page, trying simpler HTTP request...')\n"
    "    # Fallback to simple requests\n"
    "    try:\n"
    "        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}\n"
    "        resp = requests.get('https://www.espn.com/nba/teams', headers=headers, timeout=10)\n"
    "        if resp.status_code == 200:\n"
    "            print('Fallback method successful')\n"
    "            soup_fallback = BeautifulSoup(resp.content, 'html.parser')\n"
    "            # Process fallback content...\n"
    "    except Exception as e:\n"
    "        print(f'Fallback also failed: {e}')\n"
    "```\n"
    "\n"
    "The Playwright service is enterprise-grade and can handle:\n"
    "- JavaScript-heavy websites\n"
    "- Modern SPAs (Single Page Applications)\n"
    "- Dynamic content loading\n"
    "- Sports websites like ESPN, NBA.com, etc.\n"
    "\n"
    "Always extract relevant information and present it clearly to the user. "
    "If web scraping fails, suggest manual verification of the source."
)

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
        
        # DEFINITIVE FIX: Convert generator to list FIRST, then process
        app.logger.info("🔄 Starting response generation...")
        start_time = time.time()
        
        try:
            # CRITICAL: Consume the ENTIRE generator first
            app.logger.info("🔄 Consuming generator completely...")
            all_message_batches = list(bot.run(messages=current_messages))
            app.logger.info(f"✅ Generator consumed: {len(all_message_batches)} batches")
            
            # Flatten all batches into a single list
            all_messages = []
            for batch in all_message_batches:
                all_messages.extend(batch)
            
            app.logger.info(f"✅ Total messages collected: {len(all_messages)}")
            
            # NOW process the complete collected response
            final_text = ""
            tool_activities = []
            
            # Process messages by type
            for i, msg in enumerate(all_messages):
                role = msg.get('role', '')
                app.logger.debug(f"Processing message {i+1}/{len(all_messages)}: {role}")
                
                if role == 'assistant':
                    content = msg.get('content', '')
                    if isinstance(content, str):
                        final_text += content
                    elif isinstance(content, list):
                        for item in content:
                            if item.get('type') == 'text':
                                final_text += item.get('text', '')
                
                elif role == 'tool_calls':
                    tool_calls = msg.get('content', [])
                    for call in tool_calls:
                        if call.get('type') == 'tool_code':
                            tool_name = call.get('tool_name', 'code_interpreter')
                            tool_activities.append(f"🔧 Executed {tool_name}")
                
                elif role == 'tool_outputs':
                    tool_outputs = msg.get('content', [])
                    for output in tool_outputs:
                        tool_name = output.get('tool_name', 'tool')
                        output_text = str(output.get('output', ''))
                        
                        if output_text and len(output_text) > 20:
                            if 'Error' not in output_text and 'Exception' not in output_text:
                                if 'Playwright' in output_text or 'scrape' in output_text.lower():
                                    tool_activities.append(f"🌐 Web scraping completed")
                                else:
                                    tool_activities.append(f"✅ Code execution completed")
                            else:
                                tool_activities.append(f"⚠️ Tool encountered issues")

            processing_time = time.time() - start_time
            app.logger.info(f"✅ Response processing completed in {processing_time:.2f}s")

        except Exception as e:
            app.logger.error(f"❌ Error during bot.run(): {e}", exc_info=True)
            return jsonify({"error": f"Error processing query: {str(e)}"}), 500

        # Build the final response
        complete_response = final_text.strip()
        
        if not complete_response:
            if tool_activities:
                complete_response = "I processed your request using tools, but didn't generate a text response. Check the tool activity for details."
            else:
                complete_response = "I received your query but didn't generate a response. Please try rephrasing your question."

        # Add tool activity summary
        if tool_activities:
            complete_response += f"\n\n**Tool Activity:**\n" + "\n".join(tool_activities)

        app.logger.info(f"✅ Sending complete response - Length: {len(complete_response)} characters")
        app.logger.info(f"✅ Response preview: {complete_response[:100]}...")
        
        return jsonify({"response": complete_response})

    except Exception as e:
        app.logger.error(f"❌ Unhandled error in /chat endpoint: {e}", exc_info=True)
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)