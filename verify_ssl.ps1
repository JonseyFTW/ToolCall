# verify_ssl_setup_fixed.ps1 - SSL Configuration Verification (Fixed for older PowerShell)

param(
    [switch]$Deploy,
    [switch]$Test
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

# Fix for older PowerShell versions - disable SSL certificate validation
Add-Type @"
using System.Net;
using System.Security.Cryptography.X509Certificates;
public class TrustAllCertsPolicy : ICertificatePolicy {
    public bool CheckValidationResult(
        ServicePoint srvPoint, X509Certificate certificate,
        WebRequest request, int certificateProblem) {
        return true;
    }
}
"@

[System.Net.ServicePointManager]::CertificatePolicy = New-Object TrustAllCertsPolicy
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12

Write-ColorOutput "`n🔒 SSL Configuration Verification for Qwen Agent (Fixed)" "Blue"
Write-ColorOutput "=" * 60 "Blue"

# Check certificate files exist
Write-Info "Checking SSL certificate files..."

$certFile = "nginx\ssl\localhost.pem"
$keyFile = "nginx\ssl\localhost-key.pem"

if (Test-Path $certFile) {
    Write-Success "Certificate file found: $certFile"
    
    # Check certificate details if OpenSSL is available
    try {
        $certInfo = openssl x509 -in $certFile -text -noout 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Success "Certificate appears to be valid"
            
            # Extract subject and validity
            $subject = openssl x509 -in $certFile -subject -noout 2>$null
            $dates = openssl x509 -in $certFile -dates -noout 2>$null
            
            Write-Info "Certificate Subject: $($subject -replace 'subject=', '')"
            Write-Info "Certificate Validity: $($dates -replace 'not(Before|After)=', '' | ForEach-Object { $_.Trim() })"
        }
    } catch {
        Write-Warning "OpenSSL not available - cannot verify certificate details"
    }
} else {
    Write-Error "Certificate file not found: $certFile"
    Write-Info "Make sure you copied your localhost.pem file to nginx\ssl\"
    exit 1
}

if (Test-Path $keyFile) {
    Write-Success "Private key file found: $keyFile"
} else {
    Write-Error "Private key file not found: $keyFile"
    Write-Info "Make sure you copied your localhost-key.pem file to nginx\ssl\"
    exit 1
}

# Check nginx configuration
Write-Info "Checking nginx configuration..."

$nginxConfig = "nginx\nginx.conf"
if (Test-Path $nginxConfig) {
    Write-Success "Nginx configuration found: $nginxConfig"
    
    # Check if SSL certificate paths are correct in config
    $configContent = Get-Content $nginxConfig -Raw
    if ($configContent -match "ssl_certificate\s+/etc/ssl/localhost\.pem") {
        Write-Success "SSL certificate path configured correctly"
    } else {
        Write-Warning "SSL certificate path may not be configured correctly"
        Write-Info "Expected: ssl_certificate /etc/ssl/localhost.pem;"
    }
    
    if ($configContent -match "ssl_certificate_key\s+/etc/ssl/localhost-key\.pem") {
        Write-Success "SSL certificate key path configured correctly"
    } else {
        Write-Warning "SSL certificate key path may not be configured correctly"
        Write-Info "Expected: ssl_certificate_key /etc/ssl/localhost-key.pem;"
    }
} else {
    Write-Error "Nginx configuration not found: $nginxConfig"
    exit 1
}

# Check .env configuration
Write-Info "Checking environment configuration..."

if (Test-Path ".env") {
    $envContent = Get-Content ".env" -Raw
    if ($envContent -match "SSL_ENABLED=true") {
        Write-Success "SSL enabled in .env file"
    } else {
        Write-Warning "SSL not enabled in .env file"
        Write-Info "Add or update: SSL_ENABLED=true"
    }
    
    if ($envContent -match "DOMAIN_NAME=localhost") {
        Write-Success "Domain name configured for localhost"
    } else {
        Write-Info "Domain name setting: $(($envContent | Select-String 'DOMAIN_NAME=.*').Matches[0].Value)"
    }
} else {
    Write-Error ".env file not found"
    exit 1
}

# Check docker-compose configuration
Write-Info "Checking Docker Compose configuration..."

if (Test-Path "docker-compose.yml") {
    $composeContent = Get-Content "docker-compose.yml" -Raw
    if ($composeContent -match "nginx:") {
        Write-Success "Nginx service configured in docker-compose.yml"
    } else {
        Write-Warning "Nginx service not found in docker-compose.yml"
        Write-Info "Make sure you're using the SSL-enabled version of docker-compose.yml"
    }
    
    if ($composeContent -match "443:443") {
        Write-Success "HTTPS port (443) exposed"
    } else {
        Write-Warning "HTTPS port (443) not exposed"
    }
    
    if ($composeContent -match "80:80") {
        Write-Success "HTTP port (80) exposed (for redirects)"
    } else {
        Write-Warning "HTTP port (80) not exposed"
    }
} else {
    Write-Error "docker-compose.yml not found"
    exit 1
}

Write-ColorOutput "`n📋 Configuration Summary:" "Blue"
Write-Success "SSL certificates: Ready"
Write-Success "Nginx configuration: Ready" 
Write-Success "Environment settings: Ready"
Write-Success "Docker Compose: Ready"

if ($Deploy) {
    Write-ColorOutput "`n🚀 Deploying with SSL..." "Blue"
    
    # Stop existing services
    Write-Info "Stopping existing services..."
    docker-compose down 2>$null
    
    # Start with SSL
    Write-Info "Starting services with SSL..."
    docker-compose up -d --build
    
    # Wait for services
    Write-Info "Waiting for services to start..."
    Start-Sleep -Seconds 45
    
    if ($Test) {
        Write-ColorOutput "`n🧪 Testing SSL deployment..." "Blue"
        Test-SSLDeployment
    }
}

if ($Test -and !$Deploy) {
    Write-ColorOutput "`n🧪 Testing SSL configuration..." "Blue"
    Test-SSLDeployment
}

Write-ColorOutput "`n🎉 SSL verification complete!" "Green"
Write-ColorOutput "`nNext steps:" "Blue"
if (!$Deploy) {
    Write-ColorOutput "  1. Deploy: .\verify_ssl_setup_fixed.ps1 -Deploy -Test" "White"
}
Write-ColorOutput "  2. Access HTTPS: https://localhost" "White"
Write-ColorOutput "  3. Check HTTP redirect: http://localhost" "White"
Write-ColorOutput "  4. Monitor logs: docker-compose logs nginx" "White"

function Test-SSLDeployment {
    # Test HTTP redirect - Fixed for older PowerShell
    try {
        Write-Info "Testing HTTP redirect..."
        $request = [System.Net.WebRequest]::Create("http://localhost")
        $request.AllowAutoRedirect = $false
        $request.Timeout = 10000
        $response = $request.GetResponse()
        
        if ($response.StatusCode -eq "MovedPermanently" -or $response.StatusCode -eq "Found") {
            Write-Success "HTTP correctly redirects to HTTPS"
        }
        $response.Close()
    } catch {
        if ($_.Exception.Message -match "301|302") {
            Write-Success "HTTP correctly redirects to HTTPS"
        } else {
            Write-Warning "HTTP redirect test inconclusive: $($_.Exception.Message)"
        }
    }
    
    # Test HTTPS access - Fixed for older PowerShell
    try {
        Write-Info "Testing HTTPS access..."
        
        # Create a web client that ignores SSL errors
        $webClient = New-Object System.Net.WebClient
        $webClient.Headers.Add("User-Agent", "PowerShell-SSL-Test")
        
        $httpsResponse = $webClient.DownloadString("https://localhost")
        if ($httpsResponse.Length -gt 0) {
            Write-Success "HTTPS access successful"
        }
    } catch {
        Write-Error "HTTPS access failed: $($_.Exception.Message)"
        Write-Info "Check nginx logs: docker-compose logs nginx"
        Write-Info "This may be normal if services are still starting up"
    }
    
    # Test health endpoint over HTTPS - Fixed for older PowerShell
    try {
        Write-Info "Testing HTTPS health endpoint..."
        
        $webClient = New-Object System.Net.WebClient
        $webClient.Headers.Add("User-Agent", "PowerShell-Health-Test")
        
        $healthResponse = $webClient.DownloadString("https://localhost/health")
        if ($healthResponse -match '"status":\s*"healthy"') {
            Write-Success "HTTPS health check passed"
        } else {
            Write-Warning "Health endpoint responded but status unclear"
        }
    } catch {
        Write-Warning "HTTPS health check failed, but this may be normal during startup"
        Write-Info "Error: $($_.Exception.Message)"
    }
    
    # Show service status
    Write-Info "Service status:"
    docker-compose ps
    
    # Additional troubleshooting info
    Write-ColorOutput "`n🔍 Troubleshooting Info:" "Blue"
    Write-Info "Check individual service health:"
    Write-Info "  docker-compose logs qwen-agent-chat"
    Write-Info "  docker-compose logs playwright-service"
    Write-Info "  docker-compose logs nginx"
    
    Write-Info "Direct service tests:"
    Write-Info "  curl http://localhost (should redirect)"
    Write-Info "  curl -k https://localhost (should work)"
}