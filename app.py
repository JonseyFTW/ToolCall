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
import re
from urllib.parse import quote, urljoin
from datetime import datetime

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
    
    # Set environment variables
    os.environ['PYTHONHTTPSVERIFY'] = '0'
    os.environ['CURL_CA_BUNDLE'] = certifi.where()
    os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
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
    os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
    os.environ['SSL_CERT_FILE'] = certifi.where()

# Configure LLM for Qwen-Agent
llm_cfg = {
    "model": LLM_MODEL_NAME,
    "model_server": VLLM_BASE_URL,
    "api_key": API_KEY,
    "generate_cfg": {
        "top_p": 0.9,
        "temperature": 0.3,
        "max_tokens": 4000,
        "frequency_penalty": 0.1,
        "presence_penalty": 0.1,
    }
}

app.logger.info(f"LLM Configuration: {llm_cfg}")
app.logger.info(f"SSL Verification: {'DISABLED' if not VERIFY_SSL else 'ENABLED'}")
app.logger.info(f"Playwright Service: {PLAYWRIGHT_SERVICE_URL}")

# Configure Tools - ONLY use code_interpreter for maximum compatibility
tools_for_assistant = ['code_interpreter']
app.logger.info(f"Tools initialized: {tools_for_assistant}")

# Enhanced system prompt for enterprise web search capabilities
system_prompt = """You are an advanced AI assistant with enterprise-grade web search capabilities. You can access current information from the internet using the code_interpreter tool.

## Web Search Guidelines

When users ask about current information, recent events, live data, or anything that requires up-to-date information, use the code_interpreter tool with this approach:

### For Web Searches:
```python
import requests
import json
from bs4 import BeautifulSoup
import re
from urllib.parse import quote
import os

# Configure environment for SSL handling
os.environ['REQUESTS_CA_BUNDLE'] = ''
os.environ['SSL_CERT_FILE'] = ''

def search_web(query, max_results=3):
    \"\"\"
    Enterprise web search function using Playwright service
    \"\"\"
    print(f"🔍 Searching for: {query}")
    
    playwright_url = "http://playwright-service:3000/scrape"
    
    # Multi-source search strategy
    search_sources = [
        {
            "name": "Google Search",
            "url": f"https://www.google.com/search?q={quote(query)}&num=10",
            "extract_links": True
        },
        {
            "name": "DuckDuckGo",
            "url": f"https://duckduckgo.com/?q={quote(query)}",
            "extract_links": True
        }
    ]
    
    # Domain-specific sources based on query type
    if any(term in query.lower() for term in ['news', 'breaking', 'latest', 'today']):
        search_sources.extend([
            {"name": "BBC News", "url": "https://www.bbc.com/news"},
            {"name": "Reuters", "url": "https://www.reuters.com"},
            {"name": "Associated Press", "url": "https://apnews.com"}
        ])
    
    elif any(term in query.lower() for term in ['sports', 'game', 'score', 'nfl', 'nba', 'nhl', 'mlb']):
        search_sources.extend([
            {"name": "ESPN", "url": "https://www.espn.com"},
            {"name": "The Score", "url": "https://www.thescore.com"},
            {"name": "Sports Illustrated", "url": "https://www.si.com"}
        ])
    
    elif any(term in query.lower() for term in ['stock', 'market', 'finance', 'trading']):
        search_sources.extend([
            {"name": "Yahoo Finance", "url": "https://finance.yahoo.com"},
            {"name": "MarketWatch", "url": "https://www.marketwatch.com"},
            {"name": "CNBC", "url": "https://www.cnbc.com"}
        ])
    
    elif any(term in query.lower() for term in ['weather', 'forecast', 'temperature']):
        search_sources.extend([
            {"name": "Weather.com", "url": "https://weather.com"},
            {"name": "AccuWeather", "url": "https://www.accuweather.com"}
        ])
    
    results = []
    
    for source in search_sources[:max_results]:
        try:
            print(f"📡 Checking {source['name']}...")
            
            payload = {
                "url": source["url"],
                "action": "content",
                "timeout": 20000
            }
            
            response = requests.post(playwright_url, json=payload, timeout=25, verify=False)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    content = result.get('data', '')
                    
                    # Extract relevant information
                    soup = BeautifulSoup(content, 'html.parser')
                    
                    # Remove script and style elements
                    for script in soup(["script", "style", "nav", "footer", "header"]):
                        script.decompose()
                    
                    text = soup.get_text()
                    lines = [line.strip() for line in text.splitlines() if line.strip()]
                    
                    # Find relevant content based on query keywords
                    query_words = query.lower().split()
                    relevant_lines = []
                    
                    for line in lines:
                        line_lower = line.lower()
                        # Check if line contains query terms
                        relevance_score = sum(1 for word in query_words if word in line_lower)
                        if relevance_score > 0 and len(line) > 20:  # Meaningful content
                            relevant_lines.append((line, relevance_score))
                    
                    # Sort by relevance and take top results
                    relevant_lines.sort(key=lambda x: x[1], reverse=True)
                    top_content = [line[0] for line in relevant_lines[:15]]
                    
                    if top_content:
                        results.append({
                            "source": source["name"],
                            "url": source["url"],
                            "content": top_content
                        })
                        print(f"✅ Found relevant content from {source['name']}")
                    
                    # Extract links for further exploration if specified
                    if source.get("extract_links") and len(results) < max_results:
                        links = soup.find_all('a', href=True)
                        for link in links[:5]:  # Check first 5 links
                            href = link.get('href', '')
                            if href.startswith('http') and any(word in link.text.lower() for word in query_words):
                                try:
                                    link_payload = {
                                        "url": href,
                                        "action": "content",
                                        "timeout": 15000
                                    }
                                    link_response = requests.post(playwright_url, json=link_payload, timeout=20, verify=False)
                                    if link_response.status_code == 200:
                                        link_result = link_response.json()
                                        if link_result.get('success'):
                                            link_content = link_result.get('data', '')
                                            link_soup = BeautifulSoup(link_content, 'html.parser')
                                            link_text = link_soup.get_text()[:1000]  # First 1000 chars
                                            if any(word in link_text.lower() for word in query_words):
                                                results.append({
                                                    "source": f"Link from {source['name']}",
                                                    "url": href,
                                                    "content": [link_text[:500]]
                                                })
                                                break
                                except:
                                    continue
                    
            else:
                print(f"❌ Failed to access {source['name']}: HTTP {response.status_code}")
                
        except Exception as e:
            print(f"❌ Error with {source['name']}: {str(e)[:100]}")
            continue
    
    return results

# Execute search
query = "REPLACE_WITH_ACTUAL_QUERY"
search_results = search_web(query)

if search_results:
    print(f"\\n🎯 SEARCH RESULTS FOR: {query}")
    print("=" * 60)
    
    for i, result in enumerate(search_results, 1):
        print(f"\\n{i}. SOURCE: {result['source']}")
        print(f"   URL: {result['url']}")
        print("   CONTENT:")
        for content_line in result['content'][:5]:  # Show top 5 lines per source
            if content_line.strip():
                print(f"   • {content_line[:200]}...")
        print("-" * 40)
    
    # Summary
    print(f"\\n📊 SUMMARY:")
    print(f"Found information from {len(search_results)} sources")
    print(f"Search completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
else:
    print(f"❌ No relevant information found for: {query}")
    print("💡 Try rephrasing your query or check these sources manually:")
    print("   • Google.com")
    print("   • News websites (BBC, Reuters, AP)")
    print("   • Specialized sites based on your topic")
```

### Usage Instructions:
1. Replace "REPLACE_WITH_ACTUAL_QUERY" with the user's actual search query
2. The function will automatically determine the best sources based on query type
3. Results are ranked by relevance and presented clearly
4. Multiple sources are checked for comprehensive information

### For Real-time Data:
- Sports scores: Use ESPN, The Score, official team websites
- Financial data: Yahoo Finance, MarketWatch, CNBC
- News: BBC, Reuters, Associated Press
- Weather: Weather.com, AccuWeather

Always provide sources and timestamps for credibility and transparency."""

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
        # Initialize Qwen Agent - remove any unsupported parameters
        bot = Assistant(
            llm=llm_cfg,
            system_message=system_prompt,
            function_list=tools_for_assistant
        )
        app.logger.info("✅ Assistant agent initialized successfully")
        
        if playwright_ok:
            app.logger.info("✅ Full stack ready: LLM + Playwright service")
        else:
            app.logger.warning("⚠️ LLM ready but Playwright service unavailable - web search may be limited")
    else:
        app.logger.error("❌ Cannot initialize Assistant agent - vLLM connection failed")
except Exception as e:
    app.logger.error(f"❌ Failed to initialize Assistant agent: {e}", exc_info=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health')
def health():
    """Enhanced health check endpoint"""
    vllm_status = test_vllm_connection()
    playwright_status = test_playwright_service()
    
    health_data = {
        "status": "healthy" if bot and vllm_status else "unhealthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "qwen_agent": "initialized" if bot else "not_initialized",
            "vllm": "connected" if vllm_status else "disconnected", 
            "playwright": "connected" if playwright_status else "disconnected"
        },
        "capabilities": {
            "web_search": playwright_status,
            "code_execution": bool(bot),
            "real_time_data": playwright_status
        },
        "configuration": {
            "model": LLM_MODEL_NAME,
            "ssl_verification": VERIFY_SSL,
            "tools": tools_for_assistant
        }
    }
    
    return jsonify(health_data), 200 if (bot and vllm_status) else 503

@app.route('/chat', methods=['POST'])
def chat():
    """Enhanced chat endpoint with improved error handling"""
    if not bot:
        app.logger.error("Chat request received, but Assistant agent is not initialized.")
        return jsonify({
            "error": "Agent not initialized. Check backend logs and vLLM connection.",
            "details": "The Qwen Agent could not be initialized. Verify vLLM server connection."
        }), 500

    try:
        data = request.json
        user_query = data.get('query')

        if not user_query:
            return jsonify({"error": "No query provided"}), 400

        app.logger.info(f"Received query: {user_query}")

        # Prepare messages for Qwen Agent
        current_messages = [{'role': 'user', 'content': user_query}]
        
        start_time = time.time()
        timeout = 120  # 2 minutes timeout for complex web searches
        
        app.logger.info("🔄 Starting response generation...")
        
        try:
            # Process with Qwen Agent
            all_message_batches = []
            for batch in bot.run(messages=current_messages):
                all_message_batches.append(batch)
                if time.time() - start_time > timeout:
                    app.logger.warning("⚠️ Response generation timeout")
                    break
            
            # Flatten all messages
            all_messages = []
            for batch in all_message_batches:
                all_messages.extend(batch)
            
            app.logger.info(f"✅ Total messages collected: {len(all_messages)}")
            
            # Enhanced message processing
            final_response = ""
            web_search_performed = False
            errors_encountered = []
            
            for msg in all_messages:
                role = msg.get('role', '')
                
                if role == 'assistant':
                    content = msg.get('content', '')
                    if isinstance(content, str):
                        # Filter out system messages and errors
                        if not any(skip in content.lower() for skip in [
                            'invalid json', 'typeerror:', 'valueerror:', 
                            'permissionerror:', 'exception reporting'
                        ]):
                            if content.strip() and len(content) > 10:
                                final_response = content.strip()
                    elif isinstance(content, list):
                        text_parts = []
                        for item in content:
                            if isinstance(item, dict) and item.get('type') == 'text':
                                text_parts.append(item.get('text', ''))
                        combined_text = "".join(text_parts).strip()
                        if combined_text and len(combined_text) > 10:
                            final_response = combined_text
                
                elif role == 'tool_calls':
                    # Check if web search was performed
                    tool_calls = msg.get('content', [])
                    for call in tool_calls:
                        if isinstance(call, dict):
                            code_content = str(call.get('code', ''))
                            if 'search_web' in code_content or 'playwright' in code_content.lower():
                                web_search_performed = True
                
                elif role == 'tool_outputs':
                    # Process tool outputs for useful information
                    outputs = msg.get('content', [])
                    for output_item in outputs:
                        output_text = str(output_item.get('output', ''))
                        
                        # Check for errors
                        if any(err in output_text.lower() for err in ['error:', 'failed', 'exception:']):
                            errors_encountered.append(output_text[:200])
                        
                        # Extract search results if present
                        if 'SEARCH RESULTS FOR:' in output_text:
                            # If we have good search results, use them
                            if len(output_text) > 200 and not errors_encountered:
                                final_response = self.format_search_results(output_text)

            processing_time = time.time() - start_time
            app.logger.info(f"✅ Response processing completed in {processing_time:.2f}s")

            # Ensure we have a good response
            if not final_response or len(final_response) < 20:
                if web_search_performed and not errors_encountered:
                    final_response = "I searched for that information, but the results weren't clear enough to provide a definitive answer. For the most current information, I recommend checking official sources directly."
                elif errors_encountered:
                    final_response = f"I encountered some technical issues while searching for that information. Here are some reliable sources you can check directly:\n\n• Google Search\n• Official websites related to your query\n• News sources like BBC, Reuters, or Associated Press"
                else:
                    final_response = "I'm not able to provide current information on that topic right now. You might want to check official sources or news websites for the latest updates."

            # Add search indicator if applicable
            if web_search_performed and final_response and len(final_response) > 50:
                final_response += "\n\n*Information gathered from web sources*"

        except Exception as e:
            app.logger.error(f"❌ Error during bot.run(): {e}", exc_info=True)
            final_response = "I encountered an error while processing your request. Please try rephrasing your question or check the system logs for details."

        app.logger.info(f"✅ Sending response - Length: {len(final_response)} characters")
        
        return jsonify({
            "response": final_response,
            "metadata": {
                "processing_time": f"{processing_time:.2f}s",
                "web_search_performed": web_search_performed,
                "timestamp": datetime.now().isoformat()
            }
        })

    except Exception as e:
        app.logger.error(f"❌ Unhandled error in /chat endpoint: {e}", exc_info=True)
        return jsonify({
            "error": f"An unexpected error occurred: {str(e)}",
            "details": "Check server logs for more information"
        }), 500

    def format_search_results(self, raw_output):
        """Format search results for better presentation"""
        lines = raw_output.split('\n')
        formatted = []
        
        for line in lines:
            line = line.strip()
            if line and not line.startswith('=') and not line.startswith('-'):
                if line.startswith('SOURCE:'):
                    formatted.append(f"\n**{line}**")
                elif line.startswith('•'):
                    formatted.append(line)
                elif len(line) > 20:
                    formatted.append(line)
        
        return '\n'.join(formatted[:30])  # Limit output length

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)