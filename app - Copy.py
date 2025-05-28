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

# Enhanced system prompt with dynamic web browsing capabilities
system_prompt = """You are a helpful AI assistant with advanced web browsing capabilities. 

When you need to search for current information (like sports scores, news, stock prices, weather, or any real-time data), use the code_interpreter tool with this approach:

STEP 1: First, define all necessary functions and imports:

```python
import requests
import json
from bs4 import BeautifulSoup
import re
from urllib.parse import quote, urlparse

# Playwright service function
def scrape_with_playwright(url, action='content', timeout=20000):
    \"\"\"Use Playwright service for JavaScript-heavy sites\"\"\"
    PLAYWRIGHT_SERVICE = 'http://playwright-service:3000'
    
    try:
        response = requests.post(
            f'{PLAYWRIGHT_SERVICE}/scrape', 
            json={
                'url': url,
                'action': action,
                'timeout': timeout
            }, 
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('success'):
                return result.get('data')
    except Exception as e:
        print(f'Playwright failed: {e}')
    
    # Fallback to simple requests
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        }
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            print("Fallback to requests successful")
            return resp.text
    except:
        pass
    
    return None

# Google search function to find relevant URLs
def search_google(query, num_results=5):
    \"\"\"Search Google to find relevant URLs\"\"\"
    search_url = f"https://www.google.com/search?q={quote(query)}&num={num_results}"
    
    html = scrape_with_playwright(search_url)
    if not html:
        return []
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract search result URLs
    urls = []
    for link in soup.find_all('a', href=True):
        href = link['href']
        if href.startswith('/url?q='):
            # Extract actual URL from Google's redirect
            actual_url = href.split('/url?q=')[1].split('&')[0]
            if actual_url.startswith('http'):
                urls.append(actual_url)
                if len(urls) >= num_results:
                    break
    
    # If no URLs found, try alternative selectors
    if not urls:
        for div in soup.find_all('div', class_=['g', 'Gx5Zad']):
            link = div.find('a', href=True)
            if link and link['href'].startswith('http'):
                urls.append(link['href'])
    
    return urls[:num_results]

# Smart content extraction
def extract_relevant_content(html, keywords):
    \"\"\"Extract content relevant to keywords\"\"\"
    if not html:
        return ""
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.decompose()
    
    # Get text
    text = soup.get_text()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    
    # Find relevant sentences
    relevant_content = []
    keywords_lower = [kw.lower() for kw in keywords]
    
    for i, line in enumerate(lines):
        line_lower = line.lower()
        if any(keyword in line_lower for keyword in keywords_lower):
            # Include context (surrounding lines)
            start = max(0, i-2)
            end = min(len(lines), i+3)
            context = lines[start:end]
            relevant_content.extend(context)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_content = []
    for line in relevant_content:
        if line not in seen:
            seen.add(line)
            unique_content.append(line)
    
    return '\\n'.join(unique_content[:50])  # Limit to 50 most relevant lines
```

STEP 2: Now search for information based on the user's query:

```python
# Example for searching current information
user_query = "REPLACE_WITH_USER_QUERY"

# First, try searching Google for relevant sources
print(f"Searching for: {user_query}")
search_results = search_google(user_query)

if search_results:
    print(f"Found {len(search_results)} relevant sources")
    
    # Try to scrape each result
    all_content = []
    for i, url in enumerate(search_results[:3]):  # Check top 3 results
        print(f"\\nChecking source {i+1}: {url}")
        
        html = scrape_with_playwright(url)
        if html:
            # Extract relevant content based on query keywords
            keywords = user_query.split()
            relevant_content = extract_relevant_content(html, keywords)
            
            if relevant_content:
                all_content.append(f"From {urlparse(url).netloc}:\\n{relevant_content}")
                print(f"Found relevant information from {urlparse(url).netloc}")
    
    if all_content:
        print("\\n=== RELEVANT INFORMATION FOUND ===")
        for content in all_content:
            print(content)
            print("-" * 40)
else:
    # Fallback to direct URL attempts for specific queries
    if any(term in user_query.lower() for term in ['nba', 'basketball', 'thunder', 'okc']):
        direct_urls = [
            'https://www.espn.com/nba/scoreboard',
            'https://www.nba.com/games',
            'https://www.thescore.com/nba/news'
        ]
        
        for url in direct_urls:
            print(f"Trying {url}")
            html = scrape_with_playwright(url)
            if html:
                # Process sports scores...
                pass
```

IMPORTANT GUIDELINES:
1. ALWAYS define all functions before using them
2. Use Google search first to find the most relevant and current sources
3. Extract only relevant content to avoid overwhelming the response
4. Present information clearly with sources cited
5. If one approach fails, try alternatives
6. For specific domains (sports, finance, weather), you can also try direct URLs

COMMON SEARCH PATTERNS:
- Sports scores: Search "[team name] score today" or "[sport] scores"
- Stock prices: Search "[company] stock price" or "[ticker] current price"
- Weather: Search "weather [location]" or "[location] forecast"
- News: Search "[topic] news today" or "latest [topic] updates"
- Product info: Search "[product name] reviews" or "[product] specifications"

Always aim to provide the most current and accurate information available."""

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
        
        # Consume the ENTIRE generator first
        app.logger.info("🔄 Starting response generation...")
        start_time = time.time()
        
        try:
            # Consume generator completely
            all_message_batches = list(bot.run(messages=current_messages))
            all_messages = []
            for batch in all_message_batches:
                all_messages.extend(batch)
            
            app.logger.info(f"✅ Total messages collected: {len(all_messages)}")
            
            # Process messages
            final_text = ""
            tool_activities = []
            code_executed = False
            web_scraped = False
            search_performed = False
            
            for msg in all_messages:
                role = msg.get('role', '')
                
                if role == 'assistant':
                    content = msg.get('content', '')
                    if isinstance(content, str):
                        # Filter out error messages and code output
                        if not any(error_term in content for error_term in 
                                 ['The code encountered an error', 'NameError:', 
                                  'Exception:', 'Traceback', 'scrape_with_playwright function is not available',
                                  'KeyError:', 'TypeError:', 'AttributeError:']):
                            # Also filter out duplicate content
                            if content not in final_text:
                                final_text += content
                    elif isinstance(content, list):
                        for item in content:
                            if item.get('type') == 'text':
                                text = item.get('text', '')
                                if not any(error_term in text for error_term in 
                                         ['The code encountered an error', 'NameError:', 
                                          'Exception:', 'Traceback', 'KeyError:', 'TypeError:']):
                                    if text not in final_text:
                                        final_text += text
                
                elif role == 'tool_calls':
                    code_executed = True
                    tool_calls = msg.get('content', [])
                    for call in tool_calls:
                        if call.get('type') == 'tool_code':
                            code_content = str(call.get('code', ''))
                            if 'search_google' in code_content:
                                search_performed = True
                
                elif role == 'tool_outputs':
                    tool_outputs = msg.get('content', [])
                    for output in tool_outputs:
                        output_text = str(output.get('output', ''))
                        if any(term in output_text for term in ['Fetching', 'Searching for:', 'Found relevant']):
                            web_scraped = True

            processing_time = time.time() - start_time
            app.logger.info(f"✅ Response processing completed in {processing_time:.2f}s")

            # Clean up the final text
            final_text = final_text.strip()
            
            # Remove duplicate sentences
            sentences = final_text.split('. ')
            seen = set()
            unique_sentences = []
            for sentence in sentences:
                sentence = sentence.strip()
                if sentence and sentence not in seen:
                    seen.add(sentence)
                    unique_sentences.append(sentence)
            
            final_text = '. '.join(unique_sentences)
            if final_text and not final_text.endswith('.'):
                final_text += '.'

        except Exception as e:
            app.logger.error(f"❌ Error during bot.run(): {e}", exc_info=True)
            return jsonify({"error": f"Error processing query: {str(e)}"}), 500

        # Build response
        if not final_text or len(final_text) < 20:
            if code_executed:
                final_text = "I attempted to search for the information but encountered some technical issues. Please try asking your question in a different way, or check the sources directly."
            else:
                final_text = "I couldn't generate a proper response. Please try rephrasing your question."

        # Add subtle activity indicators only if relevant
        if code_executed and web_scraped:
            if search_performed:
                final_text += "\n\n*Searched multiple sources for current information*"
            else:
                final_text += "\n\n*Retrieved current information from web sources*"

        app.logger.info(f"✅ Sending response - Length: {len(final_text)} characters")
        
        return jsonify({"response": final_text})

    except Exception as e:
        app.logger.error(f"❌ Unhandled error in /chat endpoint: {e}", exc_info=True)
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)