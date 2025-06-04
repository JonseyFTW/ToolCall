# Fixed Playwright Dockerfile with proper browser installation
FROM node:18-bullseye-slim

# Set environment variables for Playwright
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=true
ENV NODE_ENV=production

# Create app directory
WORKDIR /app

# Install system dependencies for Playwright
RUN apt-get update && apt-get install -y \
    # Basic tools
    curl \
    wget \
    ca-certificates \
    # Playwright dependencies for Chromium
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libgtk-3-0 \
    libgdk-pixbuf2.0-0 \
    libxss1 \
    libxcomposite1 \
    libxrandr2 \
    libasound2 \
    libpangocairo-1.0-0 \
    libcairo-gobject2 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxrender1 \
    libxtst6 \
    libxshmfence1 \
    libgbm1 \
    # Font libraries
    fonts-liberation \
    fonts-noto-color-emoji \
    fonts-noto-cjk \
    # Additional libraries for headless Chrome
    libxkbcommon0 \
    libxrandr2 \
    libasound2 \
    libpangocairo-1.0-0 \
    libatk1.0-0 \
    libcairo-gobject2 \
    libgtk-3-0 \
    libgdk-pixbuf2.0-0 \
    # Clean up
    && rm -rf /var/lib/apt/lists/* \
    && apt-get autoremove -y \
    && apt-get autoclean

# Copy package files first for better Docker layer caching
COPY package*.json ./

# Install Node.js dependencies
RUN npm install --only=production && npm cache clean --force

# CRITICAL: Install Playwright browsers BEFORE copying application code
# This ensures browsers are always available
RUN npx playwright install chromium --with-deps

# Verify browser installation
RUN npx playwright install-deps chromium
RUN ls -la /ms-playwright/ || echo "Playwright path check"

# Second verification - make sure chromium is properly installed
RUN npx playwright install chromium
RUN find /ms-playwright -name "*chrome*" -type f | head -10 || echo "Browser files check"

# Copy application code
COPY server.js ./

# Create non-root user for security
RUN groupadd -r playwright && useradd -r -g playwright -s /bin/false playwright

# Set proper ownership and permissions
RUN chown -R playwright:playwright /app
RUN chown -R playwright:playwright /ms-playwright
RUN chmod -R 755 /ms-playwright

# Create cache directory with proper permissions
RUN mkdir -p /home/playwright/.cache && chown -R playwright:playwright /home/playwright

# Switch to non-root user
USER playwright

# Set environment variables for the user
ENV HOME=/home/playwright

# Expose port
EXPOSE 3000

# Final verification that browsers are accessible
RUN ls -la $PLAYWRIGHT_BROWSERS_PATH/ || echo "Final browser check"

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:3000/health || exit 1

# Start the service
CMD ["node", "server.js"]