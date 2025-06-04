#!/bin/bash

# Qwen Agent Enterprise Deployment Script
# This script automates the deployment of the enterprise-ready Qwen Agent system

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_NAME="qwen-agent-enterprise"
COMPOSE_FILES="-f docker-compose.yml"
MONITORING_ENABLED=false
SSL_ENABLED=false
PRODUCTION_MODE=false

# Functions
print_header() {
    echo -e "${BLUE}${1}${NC}"
    echo -e "${BLUE}$(echo "$1" | sed 's/./=/g')${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Help function
show_help() {
    cat << EOF
Qwen Agent Enterprise Deployment Script

Usage: $0 [OPTIONS]

OPTIONS:
    -h, --help              Show this help message
    -m, --monitoring        Enable monitoring stack (Prometheus, Grafana, etc.)
    -s, --ssl              Enable SSL/HTTPS configuration
    -p, --production       Production mode (includes monitoring, SSL, and optimizations)
    -d, --dev              Development mode (minimal setup)
    --clean                Clean existing deployment
    --logs                 Show logs after deployment
    --test                 Run system validation tests after deployment
    --update               Update existing deployment

EXAMPLES:
    $0                     # Basic deployment
    $0 --monitoring        # Deploy with monitoring
    $0 --production        # Full production deployment
    $0 --clean             # Clean and redeploy
    $0 --update --test     # Update and test

ENVIRONMENT VARIABLES:
    VLLM_MODEL            # Model name (default: Qwen/Qwen3-32B-Instruct)
    VLLM_BASE_URL         # vLLM server URL
    VLLM_API_KEY          # API key for vLLM server
    DOMAIN_NAME           # Domain for SSL setup

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -m|--monitoring)
            MONITORING_ENABLED=true
            COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.monitoring.yml"
            shift
            ;;
        -s|--ssl)
            SSL_ENABLED=true
            shift
            ;;
        -p|--production)
            PRODUCTION_MODE=true
            MONITORING_ENABLED=true
            SSL_ENABLED=true
            COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.monitoring.yml"
            shift
            ;;
        -d|--dev)
            print_info "Development mode enabled"
            shift
            ;;
        --clean)
            print_info "Cleaning existing deployment..."
            docker-compose down -v --remove-orphans 2>/dev/null || true
            docker system prune -f
            shift
            ;;
        --logs)
            SHOW_LOGS=true
            shift
            ;;
        --test)
            RUN_TESTS=true
            shift
            ;;
        --update)
            UPDATE_MODE=true
            shift
            ;;
        *)
            print_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Main deployment function
main() {
    print_header "🚀 Qwen Agent Enterprise Deployment"
    
    # Check prerequisites
    check_prerequisites
    
    # Setup environment
    setup_environment
    
    # Create directory structure
    create_directories
    
    # Generate configuration files
    generate_configs
    
    # SSL setup if enabled
    if [[ "$SSL_ENABLED" == true ]]; then
        setup_ssl
    fi
    
    # Deploy services
    deploy_services
    
    # Wait for services to be ready
    wait_for_services
    
    # Run tests if requested
    if [[ "$RUN_TESTS" == true ]]; then
        run_tests
    fi
    
    # Show logs if requested
    if [[ "$SHOW_LOGS" == true ]]; then
        show_logs
    fi
    
    # Display deployment summary
    show_deployment_summary
}

check_prerequisites() {
    print_info "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed"
        exit 1
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is not installed"
        exit 1
    fi
    
    # Check available memory
    AVAILABLE_MEMORY=$(free -g | awk '/^Mem:/{print $7}')
    if [[ $AVAILABLE_MEMORY -lt 4 ]]; then
        print_warning "Available memory is ${AVAILABLE_MEMORY}GB. Recommended: 8GB+"
    fi
    
    # Check disk space
    AVAILABLE_DISK=$(df -BG . | awk 'NR==2{gsub(/G/,""); print $4}')
    if [[ $AVAILABLE_DISK -lt 10 ]]; then
        print_warning "Available disk space is ${AVAILABLE_DISK}GB. Recommended: 20GB+"
    fi
    
    print_success "Prerequisites check completed"
}

setup_environment() {
    print_info "Setting up environment..."
    
    # Create .env file if it doesn't exist
    if [[ ! -f .env ]]; then
        cat > .env << EOF
# Qwen Agent Enterprise Configuration
# Generated on $(date)

# vLLM Configuration
VLLM_MODEL=${VLLM_MODEL:-Qwen/Qwen3-32B-Instruct}
VLLM_BASE_URL=${VLLM_BASE_URL:-https://vllm.rangeresources.com/v1/}
VLLM_API_KEY=${VLLM_API_KEY:-123456789}
VLLM_VERIFY_SSL=False

# Application Settings
DEBUG=${PRODUCTION_MODE:+False}
RESPONSE_TIMEOUT=120
QWEN_AGENT_MAX_TOKENS=4000
QWEN_AGENT_TEMPERATURE=0.3

# Playwright Configuration
MAX_BROWSER_INSTANCES=${PRODUCTION_MODE:+5}
REQUESTS_PER_MINUTE=${PRODUCTION_MODE:+60}
CACHE_TTL_MINUTES=5

# Security
ENABLE_RATE_LIMITING=true
LOG_LEVEL=${PRODUCTION_MODE:+info}

# SSL Configuration
SSL_ENABLED=$SSL_ENABLED
DOMAIN_NAME=${DOMAIN_NAME:-localhost}

# Monitoring
MONITORING_ENABLED=$MONITORING_ENABLED
EOF
        print_success "Created .env file"
    else
        print_info "Using existing .env file"
    fi
    
    # Load environment variables
    source .env
}

create_directories() {
    print_info "Creating directory structure..."
    
    # Core directories
    mkdir -p data/playwright-cache
    mkdir -p logs/{app,playwright,nginx}
    mkdir -p nginx/ssl
    mkdir -p playwright-service/logs
    
    # Monitoring directories
    if [[ "$MONITORING_ENABLED" == true ]]; then
        mkdir -p monitoring/{prometheus,grafana,alertmanager,blackbox}
        mkdir -p monitoring/grafana/{provisioning,dashboards}
        mkdir -p monitoring/exporters/qwen-exporter
        mkdir -p monitoring/logstash/{config,pipeline}
    fi
    
    # Set permissions
    chmod -R 755 data logs
    
    print_success "Directory structure created"
}

generate_configs() {
    print_info "Generating configuration files..."
    
    # Generate Prometheus config if monitoring is enabled
    if [[ "$MONITORING_ENABLED" == true ]]; then
        cat > monitoring/prometheus/prometheus.yml << 'EOF'
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "/etc/prometheus/rules/*.yml"

alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - alertmanager:9093

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']

  - job_name: 'qwen-agent'
    static_configs:
      - targets: ['qwen-agent-chat:5001']
    metrics_path: '/health'
    scrape_interval: 30s

  - job_name: 'playwright-service'
    static_configs:
      - targets: ['playwright-service:3000']
    metrics_path: '/health'
    scrape_interval: 30s

  - job_name: 'node-exporter'
    static_configs:
      - targets: ['node-exporter:9100']

  - job_name: 'cadvisor'
    static_configs:
      - targets: ['cadvisor:8080']

  - job_name: 'blackbox'
    static_configs:
      - targets: ['blackbox-exporter:9115']

  - job_name: 'qwen-metrics'
    static_configs:
      - targets: ['qwen-metrics-exporter:8000']
EOF
        print_success "Generated Prometheus configuration"
    fi
    
    # Generate Nginx basic auth if needed
    if [[ "$SSL_ENABLED" == true ]] && [[ ! -f nginx/.htpasswd ]]; then
        echo "admin:$(openssl passwd -apr1 'admin_change_me')" > nginx/.htpasswd
        print_success "Generated Nginx basic auth"
    fi
}

setup_ssl() {
    print_info "Setting up SSL configuration..."
    
    if [[ "$DOMAIN_NAME" == "localhost" ]]; then
        # Generate self-signed certificate for localhost
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout nginx/ssl/localhost.key \
            -out nginx/ssl/localhost.crt \
            -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"
        print_success "Generated self-signed SSL certificate"
    else
        print_warning "For production, use proper SSL certificates from Let's Encrypt or your CA"
        print_info "Place your certificates at:"
        print_info "  - nginx/ssl/${DOMAIN_NAME}.crt"
        print_info "  - nginx/ssl/${DOMAIN_NAME}.key"
    fi
}

deploy_services() {
    print_info "Deploying services..."
    
    if [[ "$UPDATE_MODE" == true ]]; then
        print_info "Updating existing deployment..."
        docker-compose $COMPOSE_FILES pull
        docker-compose $COMPOSE_FILES up -d --force-recreate --remove-orphans
    else
        print_info "Starting new deployment..."
        docker-compose $COMPOSE_FILES up -d --remove-orphans
    fi
    
    print_success "Services deployed"
}

wait_for_services() {
    print_info "Waiting for services to be ready..."
    
    # Wait for main application
    print_info "Checking Qwen Agent service..."
    for i in {1..30}; do
        if curl -f http://localhost:5001/health >/dev/null 2>&1; then
            print_success "Qwen Agent service is ready"
            break
        fi
        if [[ $i -eq 30 ]]; then
            print_error "Qwen Agent service failed to start"
            return 1
        fi
        sleep 2
    done
    
    # Wait for Playwright service
    print_info "Checking Playwright service..."
    for i in {1..20}; do
        if docker-compose exec -T playwright-service curl -f http://localhost:3000/health >/dev/null 2>&1; then
            print_success "Playwright service is ready"
            break
        fi
        if [[ $i -eq 20 ]]; then
            print_error "Playwright service failed to start"
            return 1
        fi
        sleep 3
    done
    
    # Wait for monitoring services if enabled
    if [[ "$MONITORING_ENABLED" == true ]]; then
        print_info "Checking monitoring services..."
        
        # Check Prometheus
        for i in {1..15}; do
            if curl -f http://localhost:9090/-/healthy >/dev/null 2>&1; then
                print_success "Prometheus is ready"
                break
            fi
            sleep 2
        done
        
        # Check Grafana
        for i in {1..20}; do
            if curl -f http://localhost:3001/api/health >/dev/null 2>&1; then
                print_success "Grafana is ready"
                break
            fi
            sleep 3
        done
    fi
}

run_tests() {
    print_info "Running system validation tests..."
    
    if [[ -f test_system_validation.py ]]; then
        python3 test_system_validation.py
    else
        print_warning "Test script not found. Running basic connectivity tests..."
        
        # Basic health check
        if curl -f http://localhost:5001/health; then
            print_success "Basic health check passed"
        else
            print_error "Basic health check failed"
        fi
        
        # Test chat endpoint
        if curl -X POST -H "Content-Type: application/json" \
           -d '{"query":"Hello, how are you?"}' \
           http://localhost:5001/chat >/dev/null 2>&1; then
            print_success "Chat endpoint test passed"
        else
            print_error "Chat endpoint test failed"
        fi
    fi
}

show_logs() {
    print_info "Showing service logs..."
    docker-compose $COMPOSE_FILES logs --tail=50
}

show_deployment_summary() {
    print_header "🎉 Deployment Complete!"
    
    echo -e "${GREEN}Services Status:${NC}"
    docker-compose $COMPOSE_FILES ps
    
    echo -e "\n${BLUE}Access Points:${NC}"
    echo -e "🌐 Web Interface:     http://localhost:5001"
    echo -e "🔍 Health Check:     http://localhost:5001/health"
    
    if [[ "$MONITORING_ENABLED" == true ]]; then
        echo -e "📊 Prometheus:       http://localhost:9090"
        echo -e "📈 Grafana:          http://localhost:3001 (admin/admin_change_me)"
        echo -e "📋 Kibana:           http://localhost:5601"
    fi
    
    if [[ "$SSL_ENABLED" == true ]]; then
        echo -e "🔒 HTTPS Interface:  https://localhost (if configured)"
    fi
    
    echo -e "\n${YELLOW}Important Notes:${NC}"
    echo -e "• Make sure your vLLM server is running and accessible"
    echo -e "• Update API keys in .env file"
    echo -e "• Monitor resource usage in production"
    echo -e "• Check logs regularly: docker-compose logs -f"
    
    if [[ "$PRODUCTION_MODE" == true ]]; then
        echo -e "\n${RED}Production Checklist:${NC}"
        echo -e "□ Update default passwords"
        echo -e "□ Configure proper SSL certificates"
        echo -e "□ Set up log rotation"
        echo -e "□ Configure monitoring alerts"
        echo -e "□ Set up backup procedures"
        echo -e "□ Review security settings"
    fi
    
    echo -e "\n${GREEN}Deployment completed successfully!${NC}"
}

# Error handling
trap 'print_error "An error occurred during deployment. Check the logs for details."' ERR

# Run main function
main "$@"