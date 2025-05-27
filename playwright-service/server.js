const express = require('express');
const { chromium, firefox } = require('playwright');
const cors = require('cors');
const helmet = require('helmet');

const app = express();
const port = 3000;

// Security middleware
app.use(helmet());
app.use(cors());
app.use(express.json({ limit: '10mb' }));

// Global browser instance
let browser = null;

// Enterprise-grade browser configuration
const browserConfig = {
    headless: true,
    args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-accelerated-2d-canvas',
        '--no-first-run',
        '--no-zygote',
        '--disable-gpu',
        '--disable-background-timer-throttling',
        '--disable-backgrounding-occluded-windows',
        '--disable-renderer-backgrounding',
        '--disable-web-security',
        '--disable-features=TranslateUI,VizDisplayCompositor'
    ]
};

// Initialize browser
async function initBrowser() {
    try {
        browser = await chromium.launch(browserConfig);
        console.log('✅ Playwright browser initialized successfully');
        return true;
    } catch (error) {
        console.error('❌ Failed to initialize browser:', error);
        return false;
    }
}

// Health check endpoint
app.get('/health', (req, res) => {
    res.json({ 
        status: 'healthy', 
        browser: !!browser,
        timestamp: new Date().toISOString(),
        service: 'playwright-scraper',
        version: '1.0.0'
    });
});

// Main scraping endpoint
app.post('/scrape', async (req, res) => {
    const startTime = Date.now();
    let page = null;
    
    try {
        const { 
            url, 
            selector = null, 
            action = 'content',
            waitFor = 'domcontentloaded',
            timeout = 15000,
            userAgent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        } = req.body;
        
        // Validation
        if (!url) {
            return res.status(400).json({ 
                success: false, 
                error: 'URL is required',
                timestamp: new Date().toISOString()
            });
        }

        // Validate URL format
        try {
            new URL(url);
        } catch (urlError) {
            return res.status(400).json({
                success: false,
                error: 'Invalid URL format',
                timestamp: new Date().toISOString()
            });
        }

        console.log(`📡 Scraping request: ${url} (action: ${action})`);
        
        // Create new page
        page = await browser.newPage();
        
        // Set user agent and viewport
        await page.setUserAgent(userAgent);
        await page.setViewportSize({ width: 1920, height: 1080 });
        
        // Set extra headers
        await page.setExtraHTTPHeaders({
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        });
        
        // Navigate to URL
        await page.goto(url, { 
            waitUntil: waitFor,
            timeout: timeout 
        });

        // Wait a bit for dynamic content
        await page.waitForTimeout(1000);

        let result;
        
        // Execute requested action
        switch (action.toLowerCase()) {
            case 'title':
                result = await page.title();
                break;
                
            case 'text':
                if (selector) {
                    try {
                        result = await page.textContent(selector);
                    } catch {
                        result = await page.evaluate(() => document.body.textContent || document.body.innerText);
                    }
                } else {
                    result = await page.evaluate(() => document.body.textContent || document.body.innerText);
                }
                break;
                
            case 'html':
            case 'content':
            default:
                result = await page.content();
                break;
                
            case 'screenshot':
                result = await page.screenshot({ 
                    type: 'png',
                    fullPage: false,
                    encoding: 'base64'
                });
                break;
                
            case 'element':
                if (selector) {
                    try {
                        const element = await page.locator(selector).first();
                        result = await element.textContent();
                    } catch {
                        result = null;
                    }
                } else {
                    result = null;
                }
                break;
                
            case 'elements':
                if (selector) {
                    try {
                        const elements = await page.locator(selector).all();
                        result = await Promise.all(
                            elements.map(async (el) => ({
                                text: await el.textContent(),
                                html: await el.innerHTML()
                            }))
                        );
                    } catch {
                        result = [];
                    }
                } else {
                    result = [];
                }
                break;
        }
        
        const processingTime = Date.now() - startTime;
        
        console.log(`✅ Scraping completed for ${url} in ${processingTime}ms`);
        
        res.json({ 
            success: true, 
            data: result,
            url: url,
            action: action,
            processingTime: processingTime,
            timestamp: new Date().toISOString()
        });
        
    } catch (error) {
        const processingTime = Date.now() - startTime;
        console.error(`❌ Scraping error for ${req.body.url}:`, error.message);
        
        res.status(500).json({ 
            success: false, 
            error: error.message,
            url: req.body.url || 'unknown',
            processingTime: processingTime,
            timestamp: new Date().toISOString()
        });
        
    } finally {
        // Always close the page
        if (page) {
            try {
                await page.close();
            } catch (closeError) {
                console.warn('Warning: Failed to close page:', closeError.message);
            }
        }
    }
});

// Batch scraping endpoint (for multiple URLs)
app.post('/scrape-batch', async (req, res) => {
    const startTime = Date.now();
    
    try {
        const { urls, action = 'content', timeout = 15000 } = req.body;
        
        if (!Array.isArray(urls) || urls.length === 0) {
            return res.status(400).json({
                success: false,
                error: 'URLs array is required'
            });
        }
        
        if (urls.length > 10) {
            return res.status(400).json({
                success: false,
                error: 'Maximum 10 URLs allowed per batch'
            });
        }
        
        console.log(`📡 Batch scraping: ${urls.length} URLs`);
        
        const results = await Promise.allSettled(
            urls.map(async (url) => {
                const response = await fetch('http://localhost:3000/scrape', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url, action, timeout })
                });
                return response.json();
            })
        );
        
        const processingTime = Date.now() - startTime;
        
        res.json({
            success: true,
            results: results.map((result, index) => ({
                url: urls[index],
                success: result.status === 'fulfilled' && result.value.success,
                data: result.status === 'fulfilled' ? result.value.data : null,
                error: result.status === 'rejected' ? result.reason : 
                       (result.value && !result.value.success ? result.value.error : null)
            })),
            processingTime: processingTime,
            timestamp: new Date().toISOString()
        });
        
    } catch (error) {
        console.error('❌ Batch scraping error:', error);
        res.status(500).json({
            success: false,
            error: error.message,
            timestamp: new Date().toISOString()
        });
    }
});

// Graceful shutdown
process.on('SIGINT', async () => {
    console.log('\n🛑 Shutting down Playwright service...');
    if (browser) {
        await browser.close();
        console.log('✅ Browser closed');
    }
    process.exit(0);
});

process.on('SIGTERM', async () => {
    console.log('\n🛑 Received SIGTERM, shutting down...');
    if (browser) {
        await browser.close();
        console.log('✅ Browser closed');
    }
    process.exit(0);
});

// Start server
app.listen(port, async () => {
    console.log(`🚀 Playwright service running on port ${port}`);
    console.log(`📊 Health check: http://localhost:${port}/health`);
    console.log(`🔧 Scraping endpoint: POST http://localhost:${port}/scrape`);
    
    const browserReady = await initBrowser();
    if (!browserReady) {
        console.error('❌ Failed to start browser - service may not work correctly');
    }
});