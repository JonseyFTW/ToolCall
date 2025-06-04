from flask import Flask, request, jsonify, render_template
import logging
import json
import ssl
import os
import urllib3
import requests
import time
import certifi
from datetime import datetime
from typing import Dict, List, Any, Optional

app = Flask(__name__)

# --- Configuration from Environment Variables ---
LLM_MODEL_NAME = os.getenv("VLLM_MODEL", "Qwen/Qwen3-30B-A3B-FP8")
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "https://vllm.rangeresources.com/v1/")
API_KEY = os.getenv("VLLM_API_KEY", "123456789")
VERIFY_SSL = os.getenv("VLLM_VERIFY_SSL", "False").lower() in ['true', '1', 'yes', 'on']

# SerpAPI Configuration
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")  # Get free key at https://serpapi.com/
SERPAPI_ENABLED = bool(SERPAPI_KEY)

# Generation parameters
MAX_TOKENS = int(os.getenv("QWEN_AGENT_MAX_TOKENS", "4000"))
TEMPERATURE = float(os.getenv("QWEN_AGENT_TEMPERATURE", "0.3"))
RESPONSE_TIMEOUT = int(os.getenv("RESPONSE_TIMEOUT", "120"))

logging.basicConfig(level=logging.INFO)
app.logger.setLevel(logging.INFO)

# --- COMPREHENSIVE SSL BYPASS CONFIGURATION ---
if not VERIFY_SSL:
    app.logger.info("🔓 DISABLING SSL verification for all outgoing connections")
    
    # Disable SSL warnings
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    # Set environment variables
    os.environ['PYTHONHTTPSVERIFY'] = '0'
    os.environ['CURL_CA_BUNDLE'] = ''
    os.environ['REQUESTS_CA_BUNDLE'] = ''
    
    # Modify global SSL context
    try:
        ssl._create_default_https_context = ssl._create_unverified_context
        app.logger.info("✅ Global SSL context set to unverified")
    except Exception as e:
        app.logger.warning(f"Could not set global SSL context: {e}")
    
    # Monkey patch requests module
    import requests.adapters
    from requests.packages.urllib3.util.ssl_ import create_urllib3_context
    
    class NoSSLAdapter(requests.adapters.HTTPAdapter):
        """Custom adapter that completely disables SSL verification"""
        def init_poolmanager(self, *args, **kwargs):
            context = create_urllib3_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            kwargs['ssl_context'] = context
            return super().init_poolmanager(*args, **kwargs)
    
    # Create global session with SSL disabled
    global_session = requests.Session()
    global_session.verify = False
    global_session.mount('https://', NoSSLAdapter())
    global_session.mount('http://', requests.adapters.HTTPAdapter())
    
    # Monkey patch the requests module
    original_request = requests.request
    def patched_request(method, url, **kwargs):
        kwargs['verify'] = False
        return global_session.request(method, url, **kwargs)
    
    requests.request = patched_request
    requests.get = lambda url, **kwargs: patched_request('GET', url, **kwargs)
    requests.post = lambda url, **kwargs: patched_request('POST', url, **kwargs)
    
    app.logger.info("✅ Requests module patched for SSL bypass")

else:
    app.logger.info("🔒 SSL verification is ENABLED")
    global_session = requests.Session()

class DirectLLMClient:
    """Direct client for vLLM server without qwen-agent dependency"""
    
    def __init__(self):
        self.base_url = VLLM_BASE_URL.rstrip('/')
        self.chat_url = f"{self.base_url}/chat/completions"
        self.api_key = API_KEY
        
        # Create session with SSL completely disabled
        self.session = requests.Session()
        self.session.verify = False
        
        if not VERIFY_SSL:
            self.session.mount('https://', NoSSLAdapter())
            self.session.mount('http://', requests.adapters.HTTPAdapter())
            app.logger.info("✅ DirectLLMClient configured with SSL bypass")
        
        # Set up headers
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def chat_completion(self, messages: List[Dict], **kwargs) -> Dict:
        """Direct chat completion call to vLLM"""
        payload = {
            "model": LLM_MODEL_NAME,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", MAX_TOKENS),
            "temperature": kwargs.get("temperature", TEMPERATURE),
            "top_p": kwargs.get("top_p", 0.9),
            "frequency_penalty": kwargs.get("frequency_penalty", 0.1),
            "presence_penalty": kwargs.get("presence_penalty", 0.1),
            "stream": False
        }
        
        try:
            app.logger.info(f"🔗 Calling vLLM API: {self.chat_url}")
            
            response = self.session.post(
                self.chat_url,
                headers=self.headers,
                json=payload,
                timeout=RESPONSE_TIMEOUT,
                verify=False
            )
            
            if response.status_code == 200:
                app.logger.info("✅ vLLM API call successful")
                return response.json()
            else:
                app.logger.error(f"❌ vLLM API error: {response.status_code} - {response.text}")
                raise Exception(f"vLLM API error: {response.status_code}")
                
        except Exception as e:
            app.logger.error(f"❌ Failed to call vLLM API: {e}")
            raise

class SerpAPIService:
    """Enterprise web search using SerpAPI - handles any query type automatically"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://serpapi.com/search"
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 1.0  # Minimum 1 second between requests
        
        app.logger.info("✅ SerpAPI service initialized")
    
    def search(self, query: str) -> Dict[str, Any]:
        """Universal search that automatically handles sports, finance, weather, news, etc."""
        
        # Rate limiting
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last
            time.sleep(sleep_time)
        
        app.logger.info(f"🔍 SerpAPI searching: {query}")
        
        params = {
            "q": query,
            "api_key": self.api_key,
            "engine": "google",
            "hl": "en",
            "gl": "us",
            "google_domain": "google.com",
            "safe": "active",
            "num": 10
        }
        
        try:
            response = global_session.get(self.base_url, params=params, timeout=15)
            self.last_request_time = time.time()
            
            if response.status_code == 200:
                results = response.json()
                
                # Check for API errors
                if "error" in results:
                    app.logger.error(f"❌ SerpAPI error: {results['error']}")
                    return {"success": False, "error": results["error"]}
                
                # Format results into natural language
                formatted_answer = self._format_results(results, query)
                
                return {
                    "success": True,
                    "answer": formatted_answer,
                    "result_type": self._detect_result_type(results),
                    "sources": self._extract_sources(results),
                    "api_credits_used": 1
                }
                
            elif response.status_code == 401:
                app.logger.error("❌ SerpAPI authentication failed - check API key")
                return {"success": False, "error": "Invalid API key"}
                
            elif response.status_code == 429:
                app.logger.error("❌ SerpAPI rate limit exceeded")
                return {"success": False, "error": "Rate limit exceeded"}
                
            else:
                app.logger.error(f"❌ SerpAPI HTTP error: {response.status_code}")
                return {"success": False, "error": f"HTTP {response.status_code}"}
                
        except requests.exceptions.Timeout:
            app.logger.error("❌ SerpAPI timeout")
            return {"success": False, "error": "Search timeout"}
            
        except Exception as e:
            app.logger.error(f"❌ SerpAPI exception: {e}")
            return {"success": False, "error": str(e)}
    
    def _format_results(self, results: Dict, query: str) -> str:
        """Format SerpAPI results into a natural, comprehensive answer"""
        
        formatted_parts = []
        query_lower = query.lower()
        
        # 1. SPORTS RESULTS - Automatic sports data detection and formatting
        if "sports_results" in results:
            sports_data = results["sports_results"]
            
            if "games" in sports_data:
                formatted_parts.append("🏆 **Game Results:**")
                
                for game in sports_data["games"][:3]:
                    teams = game.get("teams", [])
                    if len(teams) >= 2:
                        team1, team2 = teams[0], teams[1]
                        
                        score1 = team1.get("score", "")
                        score2 = team2.get("score", "")
                        name1 = team1.get("name", "Team 1")
                        name2 = team2.get("name", "Team 2")
                        
                        status = game.get("status", "")
                        date = game.get("date", "")
                        time_info = game.get("time", "")
                        
                        # Format the game result
                        if score1 and score2:
                            game_line = f"**{name1} {score1} - {score2} {name2}**"
                        else:
                            game_line = f"**{name1} vs {name2}**"
                        
                        if status:
                            game_line += f" ({status})"
                        
                        formatted_parts.append(game_line)
                        
                        # Add date/time if available
                        if date and time_info:
                            formatted_parts.append(f"*{date} at {time_info}*")
                        elif date:
                            formatted_parts.append(f"*{date}*")
            
            elif "tournament" in sports_data:
                # Handle tournament/league standings
                tournament = sports_data["tournament"]
                if "name" in tournament:
                    formatted_parts.append(f"🏆 **{tournament['name']}**")
                
                if "standings" in tournament:
                    formatted_parts.append("**Standings:**")
                    for team in tournament["standings"][:5]:  # Top 5 teams
                        name = team.get("name", "")
                        wins = team.get("wins", "")
                        losses = team.get("losses", "")
                        if name and wins and losses:
                            formatted_parts.append(f"• {name}: {wins}-{losses}")
        
        # 2. ANSWER BOX - Direct answers (great for factual queries)
        elif "answer_box" in results:
            answer_box = results["answer_box"]
            
            if "answer" in answer_box:
                formatted_parts.append(f"**Answer:** {answer_box['answer']}")
            
            if "title" in answer_box and answer_box["title"] != answer_box.get("answer", ""):
                formatted_parts.append(f"**Source:** {answer_box['title']}")
            
            # Add additional answer box data
            if "list" in answer_box:
                formatted_parts.append("**Details:**")
                for item in answer_box["list"][:5]:
                    formatted_parts.append(f"• {item}")
        
        # 3. KNOWLEDGE GRAPH - Entity information
        elif "knowledge_graph" in results:
            kg = results["knowledge_graph"]
            
            if "title" in kg:
                formatted_parts.append(f"**{kg['title']}**")
            
            if "description" in kg:
                formatted_parts.append(kg["description"])
            
            # Add key facts
            if "attributes" in kg:
                attributes = kg["attributes"]
                formatted_parts.append("**Key Information:**")
                for attr_key, attr_value in list(attributes.items())[:5]:
                    formatted_parts.append(f"• **{attr_key}:** {attr_value}")
        
        # 4. FINANCIAL/STOCK DATA
        elif "markets" in results or any(term in query_lower for term in ['stock', 'price', '$', 'market']):
            if "markets" in results:
                markets = results["markets"]
                formatted_parts.append("📈 **Market Data:**")
                
                for market in markets[:3]:
                    name = market.get("name", "Unknown")
                    price = market.get("price", "N/A")
                    change = market.get("change", "")
                    change_percent = market.get("change_percent", "")
                    
                    market_line = f"• **{name}:** {price}"
                    if change and change_percent:
                        market_line += f" {change} ({change_percent})"
                    elif change:
                        market_line += f" {change}"
                    
                    formatted_parts.append(market_line)
        
        # 5. WEATHER DATA
        elif "weather" in results:
            weather = results["weather"]
            location = weather.get("location", "")
            
            formatted_parts.append(f"🌤️ **Weather for {location}:**")
            
            if "current" in weather:
                current = weather["current"]
                temp = current.get("temperature", "")
                condition = current.get("condition", "")
                humidity = current.get("humidity", "")
                
                current_line = f"• **Current:** {temp}"
                if condition:
                    current_line += f" - {condition}"
                formatted_parts.append(current_line)
                
                if humidity:
                    formatted_parts.append(f"• **Humidity:** {humidity}")
            
            if "forecast" in weather:
                forecast = weather["forecast"][:3]  # Next 3 days
                if forecast:
                    formatted_parts.append("• **Forecast:**")
                    for day in forecast:
                        date = day.get("date", "")
                        high = day.get("high", "")
                        low = day.get("low", "")
                        condition = day.get("condition", "")
                        
                        forecast_line = f"  - {date}: {high}/{low}"
                        if condition:
                            forecast_line += f" - {condition}"
                        formatted_parts.append(forecast_line)
        
        # 6. NEWS RESULTS
        elif "news_results" in results:
            news = results["news_results"]
            formatted_parts.append("📰 **Latest News:**")
            
            for article in news[:3]:
                title = article.get("title", "")
                source = article.get("source", "")
                date = article.get("date", "")
                snippet = article.get("snippet", "")
                
                if title:
                    news_line = f"• **{title}**"
                    if source:
                        news_line += f" - {source}"
                    if date:
                        news_line += f" ({date})"
                    formatted_parts.append(news_line)
                    
                    if snippet and len(snippet) > 20:
                        formatted_parts.append(f"  {snippet[:150]}...")
        
        # 7. SHOPPING RESULTS (for product queries)
        elif "shopping_results" in results:
            shopping = results["shopping_results"]
            formatted_parts.append("🛒 **Product Information:**")
            
            for product in shopping[:3]:
                title = product.get("title", "")
                price = product.get("price", "")
                source = product.get("source", "")
                rating = product.get("rating", "")
                
                if title:
                    product_line = f"• **{title}**"
                    if price:
                        product_line += f" - {price}"
                    if source:
                        product_line += f" (from {source})"
                    formatted_parts.append(product_line)
                    
                    if rating:
                        formatted_parts.append(f"  Rating: {rating}")
        
        # 8. FALLBACK - Organic search results
        else:
            organic = results.get("organic_results", [])
            if organic:
                formatted_parts.append("🔍 **Search Results:**")
                
                for result in organic[:3]:
                    title = result.get("title", "")
                    snippet = result.get("snippet", "")
                    
                    if title:
                        formatted_parts.append(f"• **{title}**")
                        if snippet:
                            # Clean and truncate snippet
                            clean_snippet = snippet.replace('\n', ' ').strip()
                            if len(clean_snippet) > 200:
                                clean_snippet = clean_snippet[:200] + "..."
                            formatted_parts.append(f"  {clean_snippet}")
        
        # Combine all parts
        if formatted_parts:
            answer = "\n".join(formatted_parts)
            
            # Add timestamp and source attribution
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            answer += f"\n\n*Information from Google Search via SerpAPI ({timestamp})*"
            
            return answer
        else:
            return f"I searched for '{query}' but didn't find specific information. Please try rephrasing your question or being more specific."
    
    def _detect_result_type(self, results: Dict) -> str:
        """Detect what type of information was found"""
        if "sports_results" in results:
            return "sports"
        elif "answer_box" in results:
            return "direct_answer"
        elif "knowledge_graph" in results:
            return "entity_info"
        elif "markets" in results:
            return "financial"
        elif "weather" in results:
            return "weather"
        elif "news_results" in results:
            return "news"
        elif "shopping_results" in results:
            return "shopping"
        else:
            return "general"
    
    def _extract_sources(self, results: Dict) -> List[str]:
        """Extract source URLs for citation"""
        sources = []
        
        # Add sources from different result types
        for result in results.get("organic_results", [])[:3]:
            if "link" in result:
                sources.append(result["link"])
        
        if "answer_box" in results and "link" in results["answer_box"]:
            sources.append(results["answer_box"]["link"])
        
        if "knowledge_graph" in results and "source" in results["knowledge_graph"]:
            kg_source = results["knowledge_graph"]["source"]
            if "link" in kg_source:
                sources.append(kg_source["link"])
        
        return list(set(sources))  # Remove duplicates

class QwenAssistant:
    """Main assistant class with SerpAPI integration"""
    
    def __init__(self):
        self.llm_client = DirectLLMClient()
        self.serp_api = SerpAPIService(SERPAPI_KEY) if SERPAPI_ENABLED else None
        
        if SERPAPI_ENABLED:
            app.logger.info("✅ Assistant initialized with SerpAPI search")
        else:
            app.logger.warning("⚠️ SerpAPI not configured - only direct LLM responses available")
    
    def should_search_web(self, query: str) -> bool:
        """Determine if query requires web search"""
        
        # SerpAPI is excellent for current/factual information
        web_search_indicators = [
            # Time-sensitive queries
            'current', 'latest', 'recent', 'today', 'now', 'yesterday', 'last night',
            'this week', 'this month', 'when is', 'what time', 'schedule',
            
            # Sports queries (perfect for SerpAPI)
            'score', 'game', 'match', 'result', 'final score', 'who won', 'standings',
            'cubs', 'yankees', 'dodgers', 'patriots', 'lakers', 'warriors',
            'nfl', 'nba', 'mlb', 'nhl', 'baseball', 'football', 'basketball',
            
            # Financial queries
            'stock', 'price', 'market', 'trading', 'dow jones', 'nasdaq', '$',
            
            # Weather queries
            'weather', 'forecast', 'temperature', 'rain', 'snow', 'climate',
            
            # News and events
            'news', 'breaking', 'happened', 'happening', 'update', 'status',
            
            # Shopping/product queries
            'buy', 'price of', 'cost of', 'how much', 'where to buy',
            
            # Factual lookups
            'who is', 'what is', 'where is', 'definition', 'population of',
            'capital of', 'president of', 'founded', 'headquarters'
        ]
        
        query_lower = query.lower()
        
        # Always search if SerpAPI indicators are present
        if any(indicator in query_lower for indicator in web_search_indicators):
            return True
        
        # Also search for questions that likely need current info
        question_patterns = ['who', 'what', 'where', 'when', 'why', 'how', 'which']
        if any(pattern in query_lower for pattern in question_patterns):
            # Exclude obvious general knowledge questions
            general_knowledge = [
                'how to', 'explain', 'calculate', 'solve', 'difference between',
                'advantages', 'disadvantages', 'pros and cons'
            ]
            if not any(pattern in query_lower for pattern in general_knowledge):
                return True
        
        return False
    
    def process_query(self, query: str) -> Dict[str, Any]:
        """Process user query with SerpAPI or direct LLM"""
        start_time = time.time()
        
        try:
            needs_web_search = self.should_search_web(query)
            
            if needs_web_search and self.serp_api:
                app.logger.info("🌐 Using SerpAPI for web search")
                
                # Use SerpAPI for current information
                search_result = self.serp_api.search(query)
                
                if search_result["success"]:
                    response_text = search_result["answer"]
                    web_search_performed = True
                    search_type = f"serpapi_{search_result['result_type']}"
                    sources = search_result["sources"]
                    
                    app.logger.info(f"✅ SerpAPI returned {search_result['result_type']} data")
                    
                else:
                    # Fallback to direct LLM if SerpAPI fails
                    app.logger.warning(f"⚠️ SerpAPI failed: {search_result.get('error', 'Unknown error')}")
                    response_text = self._direct_llm_response(query, search_failed=True)
                    web_search_performed = False
                    search_type = "llm_fallback"
                    sources = []
                    
            elif needs_web_search and not self.serp_api:
                # Web search needed but SerpAPI not available
                app.logger.warning("⚠️ Web search needed but SerpAPI not configured")
                response_text = self._direct_llm_response(query, no_search_available=True)
                web_search_performed = False
                search_type = "llm_no_search"
                sources = []
                
            else:
                # Direct LLM for general knowledge
                app.logger.info("🤖 Using direct LLM for general knowledge query")
                response_text = self._direct_llm_response(query)
                web_search_performed = False
                search_type = "direct_llm"
                sources = []
            
            processing_time = time.time() - start_time
            
            return {
                "response": response_text,
                "web_search_performed": web_search_performed,
                "search_type": search_type,
                "sources": sources,
                "processing_time": f"{processing_time:.2f}s",
                "timestamp": datetime.now().isoformat(),
                "success": True
            }
            
        except Exception as e:
            app.logger.error(f"Error processing query: {e}", exc_info=True)
            processing_time = time.time() - start_time
            
            return {
                "response": f"I encountered an error while processing your request: {str(e)}. Please try again or rephrase your question.",
                "web_search_performed": False,
                "search_type": "error",
                "sources": [],
                "processing_time": f"{processing_time:.2f}s",
                "timestamp": datetime.now().isoformat(),
                "success": False,
                "error": str(e)
            }
    
    def _direct_llm_response(self, query: str, search_failed: bool = False, no_search_available: bool = False) -> str:
        """Direct LLM response with appropriate context"""
        
        if search_failed:
            system_message = "You are a helpful AI assistant. The user asked a question that would benefit from current information, but web search failed. Provide the best answer you can from your knowledge and suggest ways the user can find current information."
        elif no_search_available:
            system_message = "You are a helpful AI assistant. The user asked a question that would benefit from current information, but web search is not available. Provide the best answer you can from your knowledge and clearly indicate that the information may not be current."
        else:
            system_message = "You are a helpful AI assistant. Provide accurate, informative responses based on your knowledge."
        
        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": query}
        ]
        
        try:
            response = self.llm_client.chat_completion(messages)
            llm_response = response['choices'][0]['message']['content']
            
            # Add appropriate disclaimers
            if search_failed:
                llm_response += "\n\n*Note: I attempted to search for current information but encountered an issue. For the most up-to-date information, please check reliable sources directly.*"
            elif no_search_available:
                llm_response += "\n\n*Note: This response is based on my training data and may not reflect the most current information.*"
            
            return llm_response
            
        except Exception as e:
            app.logger.error(f"Direct LLM response failed: {e}")
            return "I'm having trouble generating a response right now. Please try again in a moment."

# Test connections
def test_vllm_connection():
    """Test connection to vLLM server"""
    try:
        app.logger.info(f"Testing connection to vLLM models endpoint")
        
        headers = {"Authorization": f"Bearer {API_KEY}"}
        response = global_session.get(f"{VLLM_BASE_URL}models", headers=headers, timeout=10)
        
        if response.status_code == 200:
            models = response.json()
            app.logger.info(f"✅ Successfully connected to vLLM server")
            app.logger.info(f"Available models: {[model.get('id', 'unknown') for model in models.get('data', [])]}")
            return True
        else:
            app.logger.error(f"❌ vLLM server returned status code: {response.status_code}")
            return False
    except Exception as e:
        app.logger.error(f"❌ Failed to connect to vLLM server: {e}")
        return False

def test_serpapi_connection():
    """Test SerpAPI connection and credits"""
    if not SERPAPI_ENABLED:
        app.logger.info("ℹ️ SerpAPI not configured")
        return False
    
    try:
        app.logger.info("Testing SerpAPI connection...")
        
        # Test with a simple query
        params = {
            "q": "test query",
            "api_key": SERPAPI_KEY,
            "engine": "google",
            "num": 1
        }
        
        response = global_session.get("https://serpapi.com/search", params=params, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            if "error" in result:
                app.logger.error(f"❌ SerpAPI error: {result['error']}")
                return False
            else:
                app.logger.info("✅ SerpAPI connection successful")
                
                # Check credits if available
                if "search_metadata" in result:
                    metadata = result["search_metadata"]
                    if "total_time_taken" in metadata:
                        app.logger.info(f"SerpAPI response time: {metadata['total_time_taken']}s")
                
                return True
        elif response.status_code == 401:
            app.logger.error("❌ SerpAPI authentication failed - check API key")
            return False
        else:
            app.logger.error(f"❌ SerpAPI returned status code: {response.status_code}")
            return False
            
    except Exception as e:
        app.logger.error(f"❌ SerpAPI connection test failed: {e}")
        return False

# Initialize the assistant
assistant = None
try:
    # Test connections
    vllm_ok = test_vllm_connection()
    serpapi_ok = test_serpapi_connection()
    
    if vllm_ok:
        assistant = QwenAssistant()
        app.logger.info("✅ Enterprise assistant initialized successfully")
        
        if serpapi_ok:
            app.logger.info("✅ Full enterprise stack ready: vLLM + SerpAPI")
        else:
            app.logger.warning("⚠️ vLLM ready but SerpAPI unavailable - limited search capabilities")
    else:
        app.logger.error("❌ Cannot initialize assistant - vLLM connection failed")
except Exception as e:
    app.logger.error(f"❌ Failed to initialize assistant: {e}", exc_info=True)

# Flask routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/health')
def health():
    """Enhanced health check endpoint"""
    vllm_status = test_vllm_connection()
    serpapi_status = test_serpapi_connection() if SERPAPI_ENABLED else False
    
    health_data = {
        "status": "healthy" if assistant and vllm_status else "unhealthy",
        "timestamp": datetime.now().isoformat(),
        "services": {
            "vllm": "connected" if vllm_status else "disconnected",
            "serpapi": "connected" if serpapi_status else "not_configured" if not SERPAPI_ENABLED else "disconnected"
        },
        "capabilities": {
            "direct_llm": bool(assistant),
            "web_search": serpapi_status,
            "sports_data": serpapi_status,
            "financial_data": serpapi_status,
            "weather_data": serpapi_status,
            "news_search": serpapi_status
        },
        "configuration": {
            "model": LLM_MODEL_NAME,
            "ssl_verification": VERIFY_SSL,
            "serpapi_enabled": SERPAPI_ENABLED,
            "search_mode": "enterprise_serpapi" if SERPAPI_ENABLED else "llm_only"
        }
    }
    
    return jsonify(health_data), 200 if (assistant and vllm_status) else 503

@app.route('/chat', methods=['POST'])
def chat():
    """Enhanced chat endpoint with SerpAPI integration"""
    if not assistant:
        app.logger.error("Chat request received, but Assistant is not initialized.")
        return jsonify({
            "error": "Assistant not initialized. Check backend logs and vLLM connection.",
            "details": "The enterprise assistant could not be initialized. Verify vLLM server connection."
        }), 500

    try:
        data = request.json
        user_query = data.get('query')

        if not user_query:
            return jsonify({"error": "No query provided"}), 400

        app.logger.info(f"Received query: {user_query}")

        # Process query through the enterprise assistant
        result = assistant.process_query(user_query)
        
        if result.get('success', False):
            app.logger.info(f"✅ Response generated successfully - Length: {len(result['response'])} characters")
            
            return jsonify({
                "response": result['response'],
                "metadata": {
                    "processing_time": result['processing_time'],
                    "web_search_performed": result['web_search_performed'],
                    "search_type": result['search_type'],
                    "sources": result.get('sources', []),
                    "timestamp": result['timestamp']
                }
            })
        else:
            app.logger.error(f"❌ Query processing failed: {result.get('error', 'Unknown error')}")
            return jsonify({
                "error": "Failed to process query",
                "details": result.get('error', 'Unknown error'),
                "metadata": {
                    "processing_time": result['processing_time'],
                    "timestamp": result['timestamp']
                }
            }), 500

    except Exception as e:
        app.logger.error(f"❌ Unhandled error in /chat endpoint: {e}", exc_info=True)
        return jsonify({
            "error": f"An unexpected error occurred: {str(e)}",
            "details": "Check server logs for more information"
        }), 500

if __name__ == '__main__':
    # Print startup information
    app.logger.info("=" * 60)
    app.logger.info("🚀 ENTERPRISE QWEN ASSISTANT STARTING")
    app.logger.info("=" * 60)
    app.logger.info(f"vLLM Model: {LLM_MODEL_NAME}")
    app.logger.info(f"SerpAPI Enabled: {SERPAPI_ENABLED}")
    app.logger.info(f"SSL Verification: {'Enabled' if VERIFY_SSL else 'Disabled'}")
    
    if SERPAPI_ENABLED:
        app.logger.info("✅ Enterprise search capabilities: Sports, Weather, Finance, News")
    else:
        app.logger.warning("⚠️ SerpAPI not configured - add SERPAPI_KEY environment variable")
        app.logger.info("Get your free SerpAPI key at: https://serpapi.com/")
    
    app.logger.info("=" * 60)
    
    app.run(debug=True, host='0.0.0.0', port=5001)