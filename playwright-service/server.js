const express = require('express');
const { chromium } = require('playwright');
const cors = require('cors');
const helmet = require('helmet');

const app = express();
const port = 3000;

// Security middleware
app.use(helmet({
    contentSecurityPolicy: false,
    crossOriginEmbedderPolicy: false
}));
app.use(cors());
app.use(express.json({ limit: '10mb' }));

// Rate limiting (simple implementation)
const requestCounts = new Map();
const RATE_LIMIT = process.env.REQUESTS_PER_MINUTE || 30;
const RATE_WINDOW = 60000; // 1 minute

// Simple cache implementation
const cache = new Map();
const CACHE_TTL = (process.env.CACHE_TTL_MINUTES || 5) * 60 * 1000;

// Browser pool configuration
const MAX_BROWSER_INSTANCES = parseInt(process.env.MAX_BROWSER_INSTANCES) || 3;
const BROWSER_IDLE_TIMEOUT = 30000; // 30 seconds

// Enhanced browser configuration for enterprise environments
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
        '--disable-features=TranslateUI,VizDisplayCompositor',
        '--disable-blink-features=AutomationControlled',
        '--disable-extensions',
        '--disable-plugins',
        '--disable-default-apps',
        '--disable-background-networking',
        '--disable-sync',
        '--disable-translate',
        '--hide-scrollbars',
        '--mute-audio',
        '--no-default-browser-check',
        '--disable-logging',
        '--disable-permissions-api',
        '--disable-presentation-api',
        '--disable-remote-fonts',
        '--disable-speech-api',
        '--disable-file-system',
        '--disable-sensors',
        '--disable-geolocation',
        '--disable-notifications'
    ],
    ignoreDefaultArgs: ['--enable-automation'],
    ignoreHTTPSErrors: true,
    timeout: 30000
};

// Browser pool management class
class BrowserPool {
    constructor() {
        this.browsers = new Map();
        this.lastUsed = new Map();
    }

    async getBrowser() {
        // Clean up idle browsers first
        await this.cleanupIdleBrowsers();

        // Try to reuse existing browser
        for (let [id, browser] of this.browsers) {
            if (browser && browser.isConnected && browser.isConnected()) {
                try {
                    // Test if browser is responsive
                    const contexts = browser.contexts();
                    if (contexts.length < 5) { // Limit concurrent contexts
                        this.lastUsed.set(id, Date.now());
                        return browser;
                    }
                } catch (error) {
                    this.browsers.delete(id);
                    this.lastUsed.delete(id);
                }
            } else {
                this.browsers.delete(id);
                this.lastUsed.delete(id);
            }
        }

        // Create new browser if pool not full
        if (this.browsers.size < MAX_BROWSER_INSTANCES) {
            try {
                const browser = await chromium.launch(browserConfig);
                const id = Date.now() + Math.random();
                this.browsers.set(id, browser);
                this.lastUsed.set(id, Date.now());
                console.log(`✅ Created new browser instance (${this.browsers.size}/${MAX_BROWSER_INSTANCES})`);
                return browser;
            } catch (error) {
                console.error('❌ Failed to create browser:', error);
                throw error;
            }
        }

        // If pool is full, wait and retry
        await new Promise(resolve => setTimeout(resolve, 1000));
        return this.getBrowser();
    }

    async cleanupIdleBrowsers() {
        const now = Date.now();
        for (let [id, lastUsed] of this.lastUsed) {
            if (now - lastUsed > BROWSER_IDLE_TIMEOUT) {
                try {
                    const browser = this.browsers.get(id);
                    if (browser && browser.isConnected && browser.isConnected()) {
                        await browser.close();
                        console.log(`🧹 Cleaned up idle browser ${id}`);
                    }
                } catch (error) {
                    console.warn(`Warning: Failed to close browser ${id}:`, error.message);
                }
                this.browsers.delete(id);
                this.lastUsed.delete(id);
            }
        }
    }

    async closeAll() {
        for (let [id, browser] of this.browsers) {
            try {
                if (browser && browser.isConnected && browser.isConnected()) {
                    await browser.close();
                }
            } catch (error) {
                console.warn(`Warning: Failed to close browser ${id}:`, error.message);
            }
        }
        this.browsers.clear();
        this.lastUsed.clear();
    }
}

// Create single browser pool instance
const browserPoolInstance = new BrowserPool();

// Rate limiting middleware
function rateLimitMiddleware(req, res, next) {
    const clientIp = req.ip || req.connection.remoteAddress;
    const now = Date.now();
    
    if (!requestCounts.has(clientIp)) {
        requestCounts.set(clientIp, { count: 1, windowStart: now });
        return next();
    }
    
    const clientData = requestCounts.get(clientIp);
    
    if (now - clientData.windowStart > RATE_WINDOW) {
        // Reset window
        clientData.count = 1;
        clientData.windowStart = now;
        return next();
    }
    
    if (clientData.count >= RATE_LIMIT) {
        return res.status(429).json({
            success: false,
            error: 'Rate limit exceeded',
            retryAfter: Math.ceil((RATE_WINDOW - (now - clientData.windowStart)) / 1000)
        });
    }
    
    clientData.count++;
    next();
}

// Apply rate limiting
app.use(rateLimitMiddleware);

// Initialize browser pool
async function initializeBrowserPool() {
    try {
        // Pre-warm one browser instance
        await browserPoolInstance.getBrowser();
        console.log('✅ Browser pool initialized successfully');
        return true;
    } catch (error) {
        console.error('❌ Failed to initialize browser pool:', error);
        return false;
    }
}

// Enhanced health check endpoint
app.get('/health', async (req, res) => {
    const healthData = {
        status: 'healthy',
        timestamp: new Date().toISOString(),
        service: 'playwright-scraper',
        version: '2.0.0',
        metrics: {
            activeBrowsers: browserPoolInstance.browsers.size,
            maxBrowsers: MAX_BROWSER_INSTANCES,
            cacheSize: cache.size,
            uptime: process.uptime(),
            memoryUsage: process.memoryUsage()
        },
        capabilities: [
            'web-scraping',
            'javascript-rendering',
            'multi-source-search',
            'content-extraction',
            'intelligent-caching',
            'rate-limiting'
        ]
    };

    // Test browser availability
    try {
        const browser = await browserPoolInstance.getBrowser();
        healthData.browserStatus = 'available';
        // Don't close, let pool manage it
    } catch (error) {
        healthData.status = 'degraded';
        healthData.browserStatus = 'unavailable';
        healthData.error = error.message;
    }

    res.json(healthData);
});

// Enhanced scraping endpoint with FIXED API calls
app.post('/scrape', async (req, res) => {
    const startTime = Date.now();
    let page = null;
    let browser = null;
    
    try {
        const { 
            url, 
            selector = null, 
            action = 'content',
            waitFor = 'domcontentloaded',
            timeout = 20000,
            userAgent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            extractLinks = false,
            smartExtraction = true,
            cacheKey = null
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
        let parsedUrl;
        try {
            parsedUrl = new URL(url);
        } catch (urlError) {
            return res.status(400).json({
                success: false,
                error: 'Invalid URL format',
                timestamp: new Date().toISOString()
            });
        }

        // Check cache first
        const cacheKeyToUse = cacheKey || `${action}:${url}`;
        if (cache.has(cacheKeyToUse)) {
            const cachedResult = cache.get(cacheKeyToUse);
            if (Date.now() - cachedResult.timestamp < CACHE_TTL) {
                console.log(`💾 Cache hit for ${url}`);
                return res.json({
                    ...cachedResult.data,
                    cached: true,
                    timestamp: new Date().toISOString()
                });
            } else {
                cache.delete(cacheKeyToUse);
            }
        }

        console.log(`📡 Scraping request: ${url} (action: ${action})`);
        
        // Get browser from pool
        browser = await browserPoolInstance.getBrowser();
        
        // Create new page with enhanced configuration
        page = await browser.newPage();
        
        // FIXED: Use correct Playwright API for setting user agent
        await page.setExtraHTTPHeaders({
            'User-Agent': userAgent,
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Upgrade-Insecure-Requests': '1'
        });
        
        // Set viewport size
        await page.setViewportSize({ width: 1920, height: 1080 });

        // Block unnecessary resources for faster loading
        await page.route('**/*', (route) => {
            const resourceType = route.request().resourceType();
            if (['image', 'stylesheet', 'font', 'media'].includes(resourceType)) {
                route.abort();
            } else {
                route.continue();
            }
        });
        
        // Navigate to URL with enhanced error handling
        let response;
        try {
            response = await page.goto(url, { 
                waitUntil: waitFor,
                timeout: timeout 
            });
        } catch (gotoError) {
            // Try alternative approach for difficult sites
            console.log(`Retry navigation for ${url}`);
            await page.goto('about:blank');
            await page.evaluate(`window.location.href = "${url}"`);
            await page.waitForLoadState('domcontentloaded', { timeout: timeout });
        }

        // Wait for dynamic content to load
        await page.waitForTimeout(2000);

        let result;
        
        // Execute requested action with smart extraction
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
                    result = await extractIntelligentText(page, smartExtraction);
                }
                break;
                
            case 'html':
            case 'content':
            default:
                if (smartExtraction) {
                    result = await extractSmartContent(page, parsedUrl.hostname);
                } else {
                    result = await page.content();
                }
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
                            elements.slice(0, 10).map(async (el) => ({ // Limit to 10 elements
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

            case 'links':
                result = await extractLinks(page, extractLinks);
                break;
        }
        
        const processingTime = Date.now() - startTime;
        
        const responseData = { 
            success: true, 
            data: result,
            url: url,
            action: action,
            processingTime: processingTime,
            timestamp: new Date().toISOString(),
            cached: false
        };

        // Cache successful results (excluding screenshots)
        if (action !== 'screenshot' && result) {
            cache.set(cacheKeyToUse, {
                data: responseData,
                timestamp: Date.now()
            });
        }
        
        console.log(`✅ Scraping completed for ${url} in ${processingTime}ms`);
        
        res.json(responseData);
        
    } catch (error) {
        const processingTime = Date.now() - startTime;
        console.error(`❌ Scraping error for ${req.body.url}:`, error.message);
        
        res.status(500).json({ 
            success: false, 
            error: error.message,
            url: req.body.url || 'unknown',
            processingTime: processingTime,
            timestamp: new Date().toISOString(),
            errorType: error.name
        });
        
    } finally {
        // Always close the page, let pool manage browser
        if (page) {
            try {
                await page.close();
            } catch (closeError) {
                console.warn('Warning: Failed to close page:', closeError.message);
            }
        }
    }
});

// Smart content extraction functions
async function extractSmartContent(page, hostname) {
    return await page.evaluate((hostname) => {
        // Remove unwanted elements
        const unwantedSelectors = [
            'script', 'style', 'nav', 'header', 'footer', 
            '.advertisement', '.ad', '.sidebar', '.menu',
            '[role="banner"]', '[role="navigation"]', '[role="complementary"]'
        ];
        
        unwantedSelectors.forEach(selector => {
            const elements = document.querySelectorAll(selector);
            elements.forEach(el => el.remove());
        });

        // Site-specific extraction rules
        let mainContent = '';
        
        if (hostname.includes('wikipedia')) {
            const content = document.querySelector('#mw-content-text, .mw-parser-output');
            mainContent = content ? content.innerHTML : document.body.innerHTML;
        } else if (hostname.includes('reddit')) {
            const posts = document.querySelectorAll('[data-testid="post-container"]');
            mainContent = Array.from(posts).slice(0, 10).map(p => p.innerHTML).join('\n');
        } else if (hostname.includes('news') || hostname.includes('bbc') || hostname.includes('cnn')) {
            const article = document.querySelector('article, .story-body, .article-body, main');
            mainContent = article ? article.innerHTML : document.body.innerHTML;
        } else {
            // Generic extraction
            const main = document.querySelector('main, article, .content, .main-content, #content');
            mainContent = main ? main.innerHTML : document.body.innerHTML;
        }

        return mainContent || document.body.innerHTML;
    }, hostname);
}

// Intelligent text extraction
async function extractIntelligentText(page, smart = true) {
    if (!smart) {
        return await page.evaluate(() => document.body.textContent || document.body.innerText);
    }

    return await page.evaluate(() => {
        // Remove unwanted elements
        const unwanted = document.querySelectorAll('script, style, nav, header, footer, .ad, .advertisement');
        unwanted.forEach(el => el.remove());

        // Get text with structure preservation
        const walker = document.createTreeWalker(
            document.body,
            NodeFilter.SHOW_TEXT,
            {
                acceptNode: function(node) {
                    // Skip empty text nodes
                    if (node.textContent.trim().length === 0) {
                        return NodeFilter.FILTER_REJECT;
                    }
                    
                    // Skip text in unwanted parent elements
                    let parent = node.parentElement;
                    while (parent) {
                        const tagName = parent.tagName.toLowerCase();
                        if (['script', 'style', 'nav', 'header', 'footer'].includes(tagName)) {
                            return NodeFilter.FILTER_REJECT;
                        }
                        parent = parent.parentElement;
                    }
                    
                    return NodeFilter.FILTER_ACCEPT;
                }
            }
        );

        const textNodes = [];
        let node;
        while (node = walker.nextNode()) {
            textNodes.push(node.textContent.trim());
        }

        return textNodes.join(' ').replace(/\s+/g, ' ').trim();
    });
}

// Link extraction
async function extractLinks(page, intelligent = true) {
    return await page.evaluate((intelligent) => {
        const links = Array.from(document.querySelectorAll('a[href]'));
        
        return links
            .map(link => ({
                url: link.href,
                text: link.textContent.trim(),
                title: link.title || '',
                internal: link.hostname === window.location.hostname
            }))
            .filter(link => {
                if (!intelligent) return true;
                
                // Filter out common unwanted links
                const unwantedPatterns = [
                    /javascript:/i,
                    /mailto:/i,
                    /tel:/i,
                    /#$/,
                    /\.(pdf|doc|docx|xls|xlsx)$/i
                ];
                
                return !unwantedPatterns.some(pattern => pattern.test(link.url)) &&
                       link.text.length > 0 && link.text.length < 100;
            })
            .slice(0, 50); // Limit to 50 links
    }, intelligent);
}

// Cache management endpoints
app.get('/cache/stats', (req, res) => {
    res.json({
        keys: cache.size,
        ttl: CACHE_TTL,
        maxAge: CACHE_TTL / 1000
    });
});

app.delete('/cache', (req, res) => {
    cache.clear();
    res.json({ success: true, message: 'Cache cleared' });
});

// Graceful shutdown with enhanced cleanup
const gracefulShutdown = async (signal) => {
    console.log(`\n🛑 Received ${signal}, shutting down gracefully...`);
    
    try {
        // Close all browsers in pool
        await browserPoolInstance.closeAll();
        console.log('✅ All browsers closed');
        
        // Clear cache
        cache.clear();
        console.log('✅ Cache cleared');
        
        process.exit(0);
    } catch (error) {
        console.error('❌ Error during shutdown:', error);
        process.exit(1);
    }
};

process.on('SIGINT', () => gracefulShutdown('SIGINT'));
process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));

// Enhanced startup
app.listen(port, async () => {
    console.log(`🚀 Enhanced Playwright service running on port ${port}`);
    console.log(`📊 Health check: http://localhost:${port}/health`);
    console.log(`🔧 Scraping endpoint: POST http://localhost:${port}/scrape`);
    console.log(`💾 Cache stats: GET http://localhost:${port}/cache/stats`);
    
    const poolReady = await initializeBrowserPool();
    if (!poolReady) {
        console.error('❌ Failed to initialize browser pool - service may not work correctly');
    } else {
        console.log('✅ Enterprise Playwright service fully operational');
    }
});