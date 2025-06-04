#!/usr/bin/env python3
"""
Enterprise Qwen Agent System Validation Test
Tests the enhanced web search capabilities without problematic switches
"""

import requests
import json
import time
import sys
import os
from urllib.parse import urljoin

# Configuration
BASE_URL = "http://localhost:5001"
PLAYWRIGHT_URL = "http://localhost:3000"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_header(title):
    print(f"\n{Colors.BLUE}{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.BLUE}{Colors.BOLD}{title.center(60)}{Colors.END}")
    print(f"{Colors.BLUE}{Colors.BOLD}{'='*60}{Colors.END}")

def print_test(name):
    print(f"\n{Colors.YELLOW}🧪 Testing: {name}{Colors.END}")

def print_success(message):
    print(f"{Colors.GREEN}✅ {message}{Colors.END}")

def print_error(message):
    print(f"{Colors.RED}❌ {message}{Colors.END}")

def print_warning(message):
    print(f"{Colors.YELLOW}⚠️  {message}{Colors.END}")

def test_health_endpoints():
    """Test health endpoints for both services"""
    print_test("Health Endpoints")
    
    # Test main application health
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=10)
        if response.status_code == 200:
            health_data = response.json()
            print_success(f"Main app health: {health_data.get('status', 'unknown')}")
            
            services = health_data.get('services', {})
            for service, status in services.items():
                if status == 'connected' or status == 'initialized':
                    print_success(f"  {service}: {status}")
                else:
                    print_error(f"  {service}: {status}")
                    
            capabilities = health_data.get('capabilities', {})
            for cap, enabled in capabilities.items():
                if enabled:
                    print_success(f"  Capability {cap}: enabled")
                else:
                    print_warning(f"  Capability {cap}: disabled")
        else:
            print_error(f"Main app health check failed: HTTP {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Failed to connect to main app: {e}")
        return False
    
    # Test Playwright service health
    try:
        response = requests.get(f"{PLAYWRIGHT_URL}/health", timeout=10)
        if response.status_code == 200:
            health_data = response.json()
            print_success(f"Playwright service: {health_data.get('status', 'unknown')}")
            
            metrics = health_data.get('metrics', {})
            print_success(f"  Browser instances: {metrics.get('activeBrowsers', 0)}/{metrics.get('maxBrowsers', 0)}")
            print_success(f"  Cache size: {metrics.get('cacheSize', 0)} items")
            print_success(f"  Uptime: {metrics.get('uptime', 0):.1f}s")
        else:
            print_error(f"Playwright health check failed: HTTP {response.status_code}")
            return False
    except Exception as e:
        print_error(f"Failed to connect to Playwright service: {e}")
        return False
    
    return True

def test_simple_scraping():
    """Test basic scraping functionality"""
    print_test("Basic Web Scraping")
    
    test_cases = [
        {
            "name": "Simple HTTP site",
            "url": "http://httpbin.org/html",
            "action": "content"
        },
        {
            "name": "HTTPS site with SSL issues disabled",
            "url": "https://httpbin.org/html", 
            "action": "content"
        },
        {
            "name": "Title extraction",
            "url": "http://example.com",
            "action": "title"
        }
    ]
    
    for test_case in test_cases:
        try:
            print(f"  Testing: {test_case['name']}")
            
            payload = {
                "url": test_case["url"],
                "action": test_case["action"],
                "timeout": 15000
            }
            
            response = requests.post(f"{PLAYWRIGHT_URL}/scrape", json=payload, timeout=20)
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    data_length = len(str(result.get('data', '')))
                    print_success(f"    Retrieved {data_length} characters in {result.get('processingTime', 0)}ms")
                else:
                    print_error(f"    Scraping failed: {result.get('error', 'Unknown error')}")
                    return False
            else:
                print_error(f"    HTTP {response.status_code}: {response.text[:100]}")
                return False
                
        except Exception as e:
            print_error(f"    Exception: {e}")
            return False
    
    return True

def test_qwen_agent_basic():
    """Test basic Qwen Agent functionality without web search"""
    print_test("Qwen Agent Basic Response")
    
    test_queries = [
        "What is 2+2?",
        "Explain quantum computing in simple terms",
        "What are the benefits of renewable energy?"
    ]
    
    for query in test_queries:
        try:
            print(f"  Query: {query}")
            
            payload = {"query": query}
            response = requests.post(f"{BASE_URL}/chat", json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                response_text = result.get('response', '')
                metadata = result.get('metadata', {})
                
                if len(response_text) > 20:
                    print_success(f"    Response length: {len(response_text)} chars")
                    print_success(f"    Processing time: {metadata.get('processing_time', 'N/A')}")
                    
                    # Check if it's a valid response (not an error message)
                    if not any(error_term in response_text.lower() for error_term in 
                             ['error', 'failed', 'cannot', 'unable', 'technical issues']):
                        print_success(f"    Valid response received")
                    else:
                        print_warning(f"    Response contains error indicators")
                        print(f"    First 100 chars: {response_text[:100]}...")
                else:
                    print_error(f"    Response too short: {response_text}")
                    return False
            else:
                print_error(f"    HTTP {response.status_code}: {response.text[:100]}")
                return False
                
        except Exception as e:
            print_error(f"    Exception: {e}")
            return False
    
    return True

def test_web_search_capability():
    """Test web search through Qwen Agent"""
    print_test("Web Search Through Qwen Agent")
    
    web_search_queries = [
        "What's the current weather in New York?",
        "Latest technology news today",
        "Current stock price of Apple"
    ]
    
    for query in web_search_queries:
        try:
            print(f"  Query: {query}")
            
            payload = {"query": query}
            start_time = time.time()
            response = requests.post(f"{BASE_URL}/chat", json=payload, timeout=60)
            end_time = time.time()
            
            if response.status_code == 200:
                result = response.json()
                response_text = result.get('response', '')
                metadata = result.get('metadata', {})
                
                if len(response_text) > 50:
                    print_success(f"    Response length: {len(response_text)} chars")
                    print_success(f"    Total time: {end_time - start_time:.1f}s")
                    
                    # Check for web search indicators
                    web_search_performed = metadata.get('web_search_performed', False)
                    if web_search_performed:
                        print_success(f"    Web search was performed")
                    else:
                        print_warning(f"    No web search detected")
                    
                    # Check response quality
                    if 'Information gathered from web sources' in response_text:
                        print_success(f"    Web sources credited")
                    
                    # Look for current information indicators
                    current_indicators = ['today', 'current', 'latest', 'now', '2024', '2025']
                    if any(indicator in response_text.lower() for indicator in current_indicators):
                        print_success(f"    Response contains current information")
                    else:
                        print_warning(f"    Response may not contain current information")
                        
                else:
                    print_error(f"    Response too short: {response_text}")
                    return False
            else:
                print_error(f"    HTTP {response.status_code}: {response.text[:200]}")
                return False
                
        except Exception as e:
            print_error(f"    Exception: {e}")
            return False
    
    return True

def test_ssl_configuration():
    """Test SSL configuration is working correctly"""
    print_test("SSL Configuration")
    
    # Test that SSL verification is properly disabled where needed
    ssl_test_urls = [
        "https://httpbin.org/get",
        "https://jsonplaceholder.typicode.com/posts/1"
    ]
    
    for url in ssl_test_urls:
        try:
            print(f"  Testing SSL with: {url}")
            
            # Test direct requests (should work with our SSL config)
            response = requests.get(url, verify=False, timeout=10)
            if response.status_code == 200:
                print_success(f"    Direct SSL request successful")
            else:
                print_error(f"    Direct SSL request failed: {response.status_code}")
                return False
            
            # Test through Playwright service
            payload = {
                "url": url,
                "action": "content",
                "timeout": 15000
            }
            
            response = requests.post(f"{PLAYWRIGHT_URL}/scrape", json=payload, timeout=20)
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    print_success(f"    Playwright SSL request successful")
                else:
                    print_error(f"    Playwright SSL request failed: {result.get('error')}")
                    return False
            else:
                print_error(f"    Playwright SSL test failed: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            print_error(f"    SSL test exception: {e}")
            return False
    
    return True

def generate_test_report(results):
    """Generate a comprehensive test report"""
    print_header("TEST RESULTS SUMMARY")
    
    total_tests = len(results)
    passed_tests = sum(1 for result in results.values() if result)
    failed_tests = total_tests - passed_tests
    
    print(f"\nTotal Tests: {total_tests}")
    print_success(f"Passed: {passed_tests}")
    if failed_tests > 0:
        print_error(f"Failed: {failed_tests}")
    
    print(f"\nDetailed Results:")
    for test_name, result in results.items():
        if result:
            print_success(f"  {test_name}")
        else:
            print_error(f"  {test_name}")
    
    print(f"\nSystem Status: ", end="")
    if failed_tests == 0:
        print_success("ALL SYSTEMS OPERATIONAL")
        print("\n🎉 Your Qwen Agent enterprise system is ready for production!")
        print("\nNext steps:")
        print("  • Monitor system performance")
        print("  • Test with real-world queries") 
        print("  • Configure monitoring and alerts")
        print("  • Scale based on usage patterns")
    else:
        print_error("ISSUES DETECTED")
        print("\n🔧 System issues found. Please check:")
        print("  • Docker services are running")
        print("  • vLLM server is accessible")
        print("  • Network connectivity")
        print("  • SSL configuration")
        print("  • Resource availability")
    
    return failed_tests == 0

def main():
    """Run all tests"""
    print_header("QWEN AGENT ENTERPRISE VALIDATION SUITE")
    print("Testing enhanced web search capabilities without problematic switches")
    
    # Allow services to start up
    print("\n⏳ Waiting for services to initialize...")
    time.sleep(5)
    
    # Run test suite
    test_results = {}
    
    test_results["Health Endpoints"] = test_health_endpoints()
    test_results["Basic Web Scraping"] = test_simple_scraping() 
    test_results["SSL Configuration"] = test_ssl_configuration()
    test_results["Qwen Agent Basic"] = test_qwen_agent_basic()
    test_results["Web Search Integration"] = test_web_search_capability()
    
    # Generate comprehensive report
    success = generate_test_report(test_results)
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())