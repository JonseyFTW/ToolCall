# Use official Node.js LTS image
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
    # Playwright dependencies
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
    # Additional libraries
    libxkbcommon0 \
    # Clean up
    && rm -rf /var/lib/apt/lists/* \
    && apt-get autoremove -y \
    && apt-get autoclean

# Copy package files
COPY package*.json ./

# Install Node.js dependencies
RUN npm install --only=production && npm cache clean --force

# Install Playwright browsers
RUN npx playwright install chromium --with-deps

# Verify Playwright installation
RUN npx playwright --version

# Copy application code
COPY server.js ./

# Create non-root user for security
RUN groupadd -r playwright && useradd -r -g playwright -s /bin/false playwright
RUN chown -R playwright:playwright /app /ms-playwright

# Switch to non-root user
USER playwright

# Expose port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:3000/health || exit 1

# Start the service
CMD ["node", "server.js"]