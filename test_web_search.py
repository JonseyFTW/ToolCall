#!/usr/bin/env python3
"""
Fixed test script with proper SSL handling
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import ssl
import urllib3

# Disable SSL warnings for testing
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Set environment variables
os.environ['PYTHONHTTPSVERIFY'] = '0'
os.environ['CURL_CA_BUNDLE'] = ''
os.environ['REQUESTS_CA_BUNDLE'] = ''
os.environ['SSL_CERT_FILE'] = ''

def test_playwright_health():
    """Test Playwright service health"""
    print("🧪 Testing Playwright service health...")
    
    try:
        # Health check doesn't need SSL
        response = requests.get("http://playwright-service:3000/health", timeout=5)
        print(f"Health check status: {response.status_code}")
        if response.status_code == 200:
            print(f"Response: {json.dumps(response.json(), indent=2)}")
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False

def test_simple_http():
    """Test simple HTTP request (no SSL)"""
    print("\n🧪 Testing simple HTTP request...")
    
    try:
        response = requests.get("http://httpbin.org/get", timeout=10)
        print(f"HTTP request status: {response.status_code}")
        return response.status_code == 200
    except Exception as e:
        print(f"❌ HTTP request failed: {e}")
        return False

def test_playwright_scrape():
    """Test Playwright scraping with a simpler target"""
    print("\n🧪 Testing Playwright scrape...")
    
    playwright_url = "http://playwright-service:3000/scrape"
    
    # Start with a simple, reliable website
    test_targets = [
        {
            "name": "HTTPBin HTML",
            "url": "http://httpbin.org/html",
            "action": "content"
        },
        {
            "name": "Example.com",
            "url": "http://example.com",
            "action": "content"
        }
    ]
    
    for target in test_targets:
        try:
            print(f"\nTesting {target['name']} at {target['url']}...")
            
            payload = {
                "url": target["url"],
                "action": target["action"],
                "timeout": 10000
            }
            
            response = requests.post(playwright_url, json=payload, timeout=15)
            print(f"Response status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                if result.get('success'):
                    content = result.get('data', '')
                    print(f"✅ Success! Retrieved {len(content)} characters")
                    
                    # Show first 200 chars
                    print(f"Content preview: {content[:200]}...")
                    return True
                else:
                    print(f"❌ Scrape failed: {result.get('error')}")
            else:
                print(f"❌ HTTP {response.status_code}")
                print(f"Response: {response.text[:500]}")
                
        except Exception as e:
            print(f"❌ Error: {e}")
            
    return False

def test_direct_request_with_ssl_fix():
    """Test direct HTTPS request with SSL fixes"""
    print("\n🧪 Testing direct HTTPS request...")
    
    try:
        # Create a session with SSL disabled
        session = requests.Session()
        session.verify = False
        
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; TestBot/1.0)'}
        response = session.get("https://httpbin.org/get", headers=headers, timeout=10)
        
        print(f"HTTPS request status: {response.status_code}")
        if response.status_code == 200:
            print("✅ HTTPS request successful")
            return True
            
    except Exception as e:
        print(f"❌ HTTPS request failed: {e}")
        
    return False

def check_playwright_logs():
    """Suggest checking Playwright logs"""
    print("\n📋 To check Playwright service logs, run:")
    print("   docker-compose logs --tail=50 playwright-service")
    print("\n📋 To test Playwright from host machine:")
    print("   curl http://localhost:3000/health")
    print("\n📋 To restart Playwright service:")
    print("   docker-compose restart playwright-service")

if __name__ == "__main__":
    print("🚀 SSL and Web Scraping Test Suite")
    print("=" * 50)
    
    results = []
    
    # Test in order of complexity
    results.append(("Playwright Health", test_playwright_health()))
    results.append(("Simple HTTP", test_simple_http()))
    results.append(("Direct HTTPS", test_direct_request_with_ssl_fix()))
    results.append(("Playwright Scrape", test_playwright_scrape()))
    
    print("\n" + "=" * 50)
    print("📊 TEST RESULTS:")
    for name, result in results:
        print(f"  {name}: {'✅' if result else '❌'}")
    
    if all(r[1] for r in results):
        print("\n✅ All tests passed!")
    else:
        print("\n⚠️  Some tests failed.")
        check_playwright_logs()