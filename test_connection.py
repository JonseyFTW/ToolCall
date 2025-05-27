#!/usr/bin/env python3
"""
Test script to verify Playwright is working correctly in Docker environment.
Run this inside the container to debug browser issues.

Usage:
    python test_playwright.py
"""

import os
import sys
from playwright.sync_api import sync_playwright

def test_basic_playwright():
    """Test basic Playwright functionality"""
    print("🧪 Testing basic Playwright functionality...")
    
    try:
        with sync_playwright() as p:
            print(f"✅ Playwright imported successfully")
            print(f"📋 Available browsers: {list(p.devices.keys())[:5]}...")  # Show first 5 devices
            
            # Test browser launch with Docker-appropriate settings
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--no-first-run',
                    '--no-zygote',
                    '--disable-gpu',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor'
                ]
            )
            
            print("✅ Browser launched successfully")
            
            # Test page creation and navigation
            page = browser.new_page()
            print("✅ Page created successfully")
            
            # Test simple HTML content
            page.set_content('<html><body><h1>Test Page</h1><p>Hello World!</p></body></html>')
            title = page.title()
            content = page.inner_text('body')
            
            print(f"✅ Page title: '{title}'")
            print(f"✅ Page content: '{content.strip()}'")
            
            browser.close()
            print("✅ Browser closed successfully")
            
            return True
            
    except Exception as e:
        print(f"❌ Basic Playwright test failed: {e}")
        return False

def test_web_navigation():
    """Test navigating to a real website"""
    print("\n🧪 Testing web navigation...")
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--no-first-run',
                    '--no-zygote',
                    '--disable-gpu',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor'
                ]
            )
            
            page = browser.new_page()
            
            # Test with a simple, reliable website
            test_url = "https://httpbin.org/html"
            print(f"🌐 Navigating to: {test_url}")
            
            page.goto(test_url, wait_until='domcontentloaded', timeout=15000)
            
            title = page.title()
            content_length = len(page.content())
            
            print(f"✅ Successfully loaded page")
            print(f"📄 Title: '{title}'")
            print(f"📊 Content length: {content_length} characters")
            
            browser.close()
            return True
            
    except Exception as e:
        print(f"❌ Web navigation test failed: {e}")
        return False

def test_nba_sports_site():
    """Test accessing a sports website (like what the user was trying)"""
    print("\n🧪 Testing sports website access...")
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--no-first-run',
                    '--no-zygote',
                    '--disable-gpu',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor'
                ]
            )
            
            page = browser.new_page()
            
            # Test with ESPN (simpler than NBA.com)
            test_url = "https://www.espn.com"
            print(f"🏀 Navigating to: {test_url}")
            
            page.goto(test_url, wait_until='domcontentloaded', timeout=20000)
            
            title = page.title()
            print(f"✅ Successfully loaded ESPN")
            print(f"📄 Title: '{title}'")
            
            # Try to find some basketball-related content
            try:
                # Look for any text containing "NBA" or "basketball"
                nba_elements = page.query_selector_all('text=NBA')
                basketball_elements = page.query_selector_all('text=basketball')
                
                print(f"🏀 Found {len(nba_elements)} NBA mentions")
                print(f"🏀 Found {len(basketball_elements)} basketball mentions")
                
                if nba_elements or basketball_elements:
                    print("✅ Successfully found sports content")
                else:
                    print("⚠️  No basketball content found (might be normal)")
                    
            except Exception as e:
                print(f"⚠️  Could not search for basketball content: {e}")
            
            browser.close()
            return True
            
    except Exception as e:
        print(f"❌ Sports website test failed: {e}")
        return False

def check_environment():
    """Check the environment and dependencies"""
    print("🔧 Checking environment...")
    
    # Check environment variables
    env_vars = ['DISPLAY', 'PLAYWRIGHT_BROWSERS_PATH', 'PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS']
    for var in env_vars:
        value = os.environ.get(var, 'Not set')
        print(f"   {var}: {value}")
    
    # Check if we're in a container
    if os.path.exists('/.dockerenv'):
        print("   🐳 Running inside Docker container")
    else:
        print("   💻 Running on host system")
    
    # Check if Xvfb is running
    import subprocess
    try:
        result = subprocess.run(['pgrep', 'Xvfb'], capture_output=True, text=True)
        if result.returncode == 0:
            print("   🖥️  Xvfb is running")
        else:
            print("   ⚠️  Xvfb might not be running")
    except:
        print("   ❓ Could not check Xvfb status")

def main():
    """Run all tests"""
    print("🚀 Playwright Docker Test Suite")
    print("=" * 50)
    
    # Check environment first
    check_environment()
    print()
    
    # Run tests
    results = []
    
    results.append(test_basic_playwright())
    results.append(test_web_navigation())
    results.append(test_nba_sports_site())
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 TEST RESULTS:")
    print(f"   Basic Playwright: {'✅ PASS' if results[0] else '❌ FAIL'}")
    print(f"   Web Navigation: {'✅ PASS' if results[1] else '❌ FAIL'}")
    print(f"   Sports Website: {'✅ PASS' if results[2] else '❌ FAIL'}")
    
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"\n🎉 ALL TESTS PASSED ({passed}/{total})!")
        print("✅ Playwright is working correctly in this environment.")
    else:
        print(f"\n⚠️  SOME TESTS FAILED ({passed}/{total})")
        print("\n🔧 Troubleshooting suggestions:")
        if not results[0]:
            print("   • Playwright installation might be incomplete")
            print("   • Try: playwright install --with-deps chromium")
        if not results[1] or not results[2]:
            print("   • Network connectivity issues")
            print("   • Browser security restrictions")
            print("   • Try running with different browser arguments")

if __name__ == "__main__":
    main()