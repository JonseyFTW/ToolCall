# setup_windows.ps1 - Windows PowerShell Setup Script for Qwen Agent Enterprise
# No SSL certificates required!

param(
    [switch]$SkipSSL = $true,
    [switch]$DevMode = $false,
    [string]$ProjectPath = "qwen-agent-enterprise"
)

# Colors for output
$Colors = @{
    Red = "Red"
    Green = "Green" 
    Yellow = "Yellow"
    Blue = "Cyan"
    White = "White"
}

function Write-ColorOutput {
    param([string]$Message, [string]$Color = "White")
    Write-Host $Message -ForegroundColor $Colors[$Color]
}

function Write-Header {
    param([string]$Title)
    Write-ColorOutput "`n$('='*60)" "Blue"
    Write-ColorOutput $Title.PadLeft(($Title.Length + 60)/2) "Blue"
    Write-ColorOutput "$('='*60)" "Blue"
}

function Write-Success {
    param([string]$Message)
    Write-ColorOutput "✅ $Message" "Green"
}

function Write-Error {
    param([string]$Message)
    Write-ColorOutput "❌ $Message" "Red"
}

function Write-Warning {
    param([string]$Message)
    Write-ColorOutput "⚠️  $Message" "Yellow"
}

function Write-Info {
    param([string]$Message)
    Write-ColorOutput "ℹ️  $Message" "Blue"
}

# Main setup function
function Setup-QwenAgentProject {
    Write-Header "🚀 Qwen Agent Enterprise - Windows Setup"
    Write-Info "Setting up project without SSL certificates (not needed for web search!)"
    
    # Check prerequisites
    Test-Prerequisites
    
    # Create project structure
    New-ProjectStructure
    
    # Create configuration files
    New-ConfigurationFiles
    
    # Create Docker files
    New-DockerFiles
    
    # Create deployment script
    New-DeploymentScript
    
    # Show completion summary
    Show-CompletionSummary
}

function Test-Prerequisites {
    Write-Info "Checking prerequisites..."
    
    # Check Docker
    try {
        $dockerVersion = docker --version
        Write-Success "Docker found: $dockerVersion"
    }
    catch {
        Write-Error "Docker not found. Please install Docker Desktop for Windows."
        Write-Info "Download from: https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe"
        exit 1
    }
    
    # Check Docker Compose
    try {
        $composeVersion = docker-compose --version
        Write-Success "Docker Compose found: $composeVersion"
    }
    catch {
        Write-Error "Docker Compose not found. Please install Docker Desktop (includes Compose)."
        exit 1
    }
    
    # Check if Docker is running
    try {
        docker info | Out-Null
        Write-Success "Docker daemon is running"
    }
    catch {
        Write-Warning "Docker daemon not running. Please start Docker Desktop."
        Write-Info "The script will continue, but you'll need to start Docker before deploying."
    }
}

function New-ProjectStructure {
    Write-Info "Creating project directory structure..."
    
    # Create main project directory
    if (!(Test-Path $ProjectPath)) {
        New-Item -ItemType Directory -Path $ProjectPath
        Write-Success "Created project directory: $ProjectPath"
    } else {
        Write-Warning "Project directory already exists: $ProjectPath"
    }
    
    Set-Location $ProjectPath
    
    # Create all required directories
    $directories = @(
        "templates",
        "playwright-service",
        "playwright-service\logs",
        "data\playwright-cache",
        "logs\app",
        "logs\playwright", 
        "logs\nginx",
        "nginx",
        "monitoring\prometheus",
        "scripts"
    )
    
    foreach ($dir in $directories) {
        if (!(Test-Path $dir)) {
            New-Item -ItemType Directory -Path $dir -Force
            Write-Success "Created directory: $dir"
        }
    }
}

function New-ConfigurationFiles {
    Write-Info "Creating configuration files..."
    
    # Create .env file
    if (!(Test-Path ".env")) {
        $envContent = @"
# Qwen Agent Enterprise Configuration for Windows
# No SSL certificates required for web search functionality!

# vLLM Configuration (Update with your actual values)
VLLM_MODEL=Qwen/Qwen3-32B-Instruct
VLLM_BASE_URL=https://vllm.rangeresources.com/v1/
VLLM_API_KEY=your_actual_api_key_here
VLLM_VERIFY_SSL=False

# Application Settings
DEBUG=True
PYTHONUNBUFFERED=1
PYTHONDONTWRITEBYTECODE=1
RESPONSE_TIMEOUT=120
QWEN_AGENT_MAX_TOKENS=4000
QWEN_AGENT_TEMPERATURE=0.3

# Playwright Configuration
MAX_BROWSER_INSTANCES=3
REQUESTS_PER_MINUTE=30
CACHE_TTL_MINUTES=5
PLAYWRIGHT_SERVICE_URL=http://playwright-service:3000

# Windows-specific settings
LOG_LEVEL=info
ENABLE_RATE_LIMITING=true

# SSL DISABLED (not needed for web search)
SSL_ENABLED=false
DOMAIN_NAME=localhost

# Monitoring (optional)
MONITORING_ENABLED=false
"@
        Set-Content -Path ".env" -Value $envContent
        Write-Success "Created .env configuration file"
    } else {
        Write-Warning ".env file already exists, skipping"
    }
    
    # Create .gitignore
    if (!(Test-Path ".gitignore")) {
        $gitignoreContent = @"
# Environment and secrets
.env
*.key
*.crt
secrets/

# Logs
logs/
*.log

# Python
__pycache__/
*.py[cod]
*`$py.class
.Python
build/
dist/
*.egg-info/

# Windows
Thumbs.db
Desktop.ini

# Docker
.docker/

# IDE
.vscode/
.idea/
*.swp

# Data
data/playwright-cache/
node_modules/
"@
        Set-Content -Path ".gitignore" -Value $gitignoreContent
        Write-Success "Created .gitignore file"
    }
    
    # Create README
    if (!(Test-Path "README.md")) {
        $readmeContent = @"
# Qwen Agent Enterprise - Windows Setup

Enterprise AI assistant with web search capabilities - optimized for Windows Docker.

## Quick Start

1. **Update Configuration**:
   ```powershell
   notepad .env  # Update with your vLLM server details
   ```

2. **Deploy**:
   ```powershell
   .\deploy.ps1
   ```

3. **Access**:
   - Web Interface: http://localhost:5001
   - Health Check: http://localhost:5001/health

## Important Notes

- **No SSL certificates required** for web search functionality
- Remove `--enable-auto-tool-choice` and `--tool-call-parser hermes` from your vLLM server
- Update API keys in `.env` file
- Ensure Docker Desktop is running before deployment

## File Structure

- `app.py` - Main Flask application
- `docker-compose.yml` - Service orchestration
- `templates/index.html` - Web interface
- `playwright-service/` - Web scraping service
- `.env` - Configuration (update this!)

## Troubleshooting

- **Port conflicts**: Change ports in docker-compose.yml
- **Performance issues**: Increase Docker Desktop memory allocation
- **Browser launch fails**: Restart Docker Desktop

For detailed setup instructions, see the deployment guide.
"@
        Set-Content -Path "README.md" -Value $readmeContent
        Write-Success "Created README.md"
    }
}

function New-DockerFiles {
    Write-Info "Creating simplified Docker Compose configuration..."
    
    if (!(Test-Path "docker-compose.yml")) {
        $dockerComposeContent = @"
version: '3.8'

services:
  # Main Qwen Agent Application
  qwen-agent-chat:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: qwen-agent-chat
    ports:
      - "5001:5001"
    environment:
      - DEBUG=`${DEBUG:-True}
      - PYTHONUNBUFFERED=1
      - PYTHONDONTWRITEBYTECODE=1
      - VLLM_VERIFY_SSL=False
      - VLLM_BASE_URL=`${VLLM_BASE_URL}
      - VLLM_MODEL=`${VLLM_MODEL}
      - VLLM_API_KEY=`${VLLM_API_KEY}
      - PLAYWRIGHT_SERVICE_URL=http://playwright-service:3000
      - RESPONSE_TIMEOUT=`${RESPONSE_TIMEOUT:-120}
      - QWEN_AGENT_MAX_TOKENS=`${QWEN_AGENT_MAX_TOKENS:-4000}
      - QWEN_AGENT_TEMPERATURE=`${QWEN_AGENT_TEMPERATURE:-0.3}
    depends_on:
      playwright-service:
        condition: service_healthy
    restart: unless-stopped
    volumes:
      - .\logs:/app/logs
    networks:
      - qwen-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5001/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s

  # Playwright Web Scraping Service  
  playwright-service:
    build:
      context: ./playwright-service
      dockerfile: Dockerfile
    container_name: playwright-service
    expose:
      - "3000"
    environment:
      - NODE_ENV=production
      - MAX_BROWSER_INSTANCES=`${MAX_BROWSER_INSTANCES:-3}
      - REQUESTS_PER_MINUTE=`${REQUESTS_PER_MINUTE:-30}
      - CACHE_TTL_MINUTES=`${CACHE_TTL_MINUTES:-5}
      - PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
      - PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=true
    restart: unless-stopped
    volumes:
      - .\data\playwright-cache:/ms-playwright
      - .\logs\playwright:/app/logs
    networks:
      - qwen-network
    # Windows-specific optimizations
    shm_size: 1gb
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 45s
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '1.0'
        reservations:
          memory: 1G
          cpus: '0.5'

networks:
  qwen-network:
    driver: bridge
    name: qwen-network

# Persistent volumes for Windows
volumes:
  playwright-cache:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: .\data\playwright-cache
"@
        Set-Content -Path "docker-compose.yml" -Value $dockerComposeContent
        Write-Success "Created docker-compose.yml (SSL-free configuration)"
    }
}

function New-DeploymentScript {
    Write-Info "Creating Windows deployment script..."
    
    $deployScriptContent = @'
# deploy.ps1 - Windows Deployment Script for Qwen Agent Enterprise

param(
    [switch]$Build,
    [switch]$Test,
    [switch]$Logs,
    [switch]$Stop,
    [switch]$Clean
)

function Write-ColorOutput {
    param([string]$Message, [string]$Color = "White")
    $Colors = @{ Red = "Red"; Green = "Green"; Yellow = "Yellow"; Blue = "Cyan"; White = "White" }
    Write-Host $Message -ForegroundColor $Colors[$Color]
}

function Write-Success { param([string]$Message); Write-ColorOutput "✅ $Message" "Green" }
function Write-Error { param([string]$Message); Write-ColorOutput "❌ $Message" "Red" }
function Write-Warning { param([string]$Message); Write-ColorOutput "⚠️  $Message" "Yellow" }
function Write-Info { param([string]$Message); Write-ColorOutput "ℹ️  $Message" "Blue" }

Write-ColorOutput "`n🚀 Qwen Agent Enterprise - Windows Deployment" "Blue"

if ($Stop) {
    Write-Info "Stopping services..."
    docker-compose down
    Write-Success "Services stopped"
    exit 0
}

if ($Clean) {
    Write-Info "Cleaning up..."
    docker-compose down -v --remove-orphans
    docker system prune -f
    Write-Success "Cleanup completed"
    exit 0
}

# Check if Docker is running
try {
    docker info | Out-Null
    Write-Success "Docker is running"
} catch {
    Write-Error "Docker is not running. Please start Docker Desktop."
    exit 1
}

# Check .env file
if (!(Test-Path ".env")) {
    Write-Error ".env file not found. Please create it with your vLLM configuration."
    exit 1
}

# Build and start services
if ($Build) {
    Write-Info "Building and starting services..."
    docker-compose up -d --build
} else {
    Write-Info "Starting services..."
    docker-compose up -d
}

# Wait for services to be healthy
Write-Info "Waiting for services to start..."
$maxAttempts = 30
$attempt = 0

do {
    Start-Sleep -Seconds 2
    $attempt++
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:5001/health" -UseBasicParsing -TimeoutSec 5
        if ($response.StatusCode -eq 200) {
            Write-Success "Qwen Agent is ready!"
            break
        }
    } catch {
        if ($attempt -eq $maxAttempts) {
            Write-Warning "Service may still be starting. Check logs if needed."
        }
    }
} while ($attempt -lt $maxAttempts)

# Run tests if requested
if ($Test) {
    Write-Info "Running basic connectivity tests..."
    
    # Test health endpoint
    try {
        $health = Invoke-RestMethod -Uri "http://localhost:5001/health"
        Write-Success "Health check passed: $($health.status)"
    } catch {
        Write-Error "Health check failed"
    }
    
    # Test chat endpoint
    try {
        $chatTest = @{ query = "Hello, how are you?" } | ConvertTo-Json
        $response = Invoke-RestMethod -Uri "http://localhost:5001/chat" -Method Post -Body $chatTest -ContentType "application/json"
        Write-Success "Chat endpoint test passed"
    } catch {
        Write-Error "Chat endpoint test failed"
    }
}

# Show logs if requested
if ($Logs) {
    Write-Info "Showing service logs..."
    docker-compose logs --tail=50
}

# Show status
Write-ColorOutput "`n📊 Service Status:" "Blue"
docker-compose ps

Write-ColorOutput "`n🌐 Access Points:" "Green"
Write-ColorOutput "   Web Interface: http://localhost:5001" "White"
Write-ColorOutput "   Health Check:  http://localhost:5001/health" "White"

Write-ColorOutput "`n💡 Useful Commands:" "Yellow"
Write-ColorOutput "   Show logs:     .\deploy.ps1 -Logs" "White"
Write-ColorOutput "   Stop services: .\deploy.ps1 -Stop" "White"
Write-ColorOutput "   Clean up:      .\deploy.ps1 -Clean" "White"
Write-ColorOutput "   Rebuild:       .\deploy.ps1 -Build" "White"

Write-Success "`nDeployment completed! 🎉"
'@
    Set-Content -Path "deploy.ps1" -Value $deployScriptContent
    Write-Success "Created deploy.ps1 script"
}

function Show-CompletionSummary {
    Write-Header "🎉 Setup Complete!"
    
    Write-ColorOutput "`n📁 Project Structure Created:" "Green"
    Write-ColorOutput "   ✅ Directory structure" "White"
    Write-ColorOutput "   ✅ Configuration files (.env, docker-compose.yml)" "White"
    Write-ColorOutput "   ✅ Deployment script (deploy.ps1)" "White"
    Write-ColorOutput "   ✅ Documentation (README.md)" "White"
    
    Write-ColorOutput "`n📋 Next Steps:" "Yellow"
    Write-ColorOutput "   1. Copy artifact contents to these files:" "White"
    Write-ColorOutput "      • app.py (Enhanced Flask application)" "White"
    Write-ColorOutput "      • requirements.txt (Python dependencies)" "White"
    Write-ColorOutput "      • Dockerfile (Main container)" "White"
    Write-ColorOutput "      • templates\index.html (Web interface)" "White"
    Write-ColorOutput "      • playwright-service\server.js (Playwright server)" "White"
    Write-ColorOutput "      • playwright-service\package.json (Node dependencies)" "White"
    Write-ColorOutput "      • playwright-service\Dockerfile (Playwright container)" "White"
    
    Write-ColorOutput "`n   2. Update configuration:" "White"
    Write-ColorOutput "      notepad .env  # Add your vLLM server details" "White"
    
    Write-ColorOutput "`n   3. Deploy:" "White"
    Write-ColorOutput "      .\deploy.ps1 -Build -Test" "White"
    
    Write-ColorOutput "`n🔑 Important Notes:" "Blue"
    Write-ColorOutput "   • No SSL certificates required for web search!" "White"
    Write-ColorOutput "   • Remove --enable-auto-tool-choice from vLLM server" "White"
    Write-ColorOutput "   • Remove --tool-call-parser hermes from vLLM server" "White"
    Write-ColorOutput "   • Update VLLM_API_KEY in .env file" "White"
    
    Write-ColorOutput "`n📍 Current Location: $(Get-Location)" "Blue"
    Write-Success "Ready for artifact file copying and deployment! 🚀"
}

# Run the setup
Setup-QwenAgentProject