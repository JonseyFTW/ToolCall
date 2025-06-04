# Qwen Agent Enterprise Deployment Guide

## 🚀 Quick Start

### Prerequisites
- Docker and Docker Compose v2.x
- 8GB+ RAM recommended
- 4+ CPU cores for optimal performance
- vLLM server running Qwen3-32B model
- Network access to vLLM endpoint

### 1. Environment Setup

Create `.env` file in project root:
```bash
# vLLM Configuration (CRITICAL: Remove problematic switches)
VLLM_MODEL=Qwen/Qwen3-32B-Instruct
VLLM_BASE_URL=https://vllm.rangeresources.com/v1/
VLLM_API_KEY=your_actual_api_key_here
VLLM_VERIFY_SSL=False

# Performance Tuning
QWEN_AGENT_MAX_TOKENS=4000
QWEN_AGENT_TEMPERATURE=0.3
RESPONSE_TIMEOUT=120

# Playwright Configuration
MAX_BROWSER_INSTANCES=3
REQUESTS_PER_MINUTE=30
CACHE_TTL_MINUTES=5

# Security
ENABLE_RATE_LIMITING=true
LOG_LEVEL=info
```

### 2. vLLM Server Configuration

**IMPORTANT**: Ensure your vLLM server is configured WITHOUT these problematic switches:
- ❌ `--enable-auto-tool-choice` 
- ❌ `--tool-call-parser hermes`

Correct vLLM startup command:
```bash
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen3-32B-Instruct \
  --host 0.0.0.0 \
  --port 8000 \
  --api-key your_api_key \
  --served-model-name Qwen/Qwen3-32B-Instruct \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.9
```

### 3. Quick Deployment

```bash
# Clone or prepare your project directory
mkdir qwen-agent-enterprise && cd qwen-agent-enterprise

# Create required directories
mkdir -p data/playwright-cache logs playwright-service/logs

# Start the stack
docker-compose up -d

# Verify deployment
python test_system_validation.py
```

### 4. Access Points

- **Web Interface**: http://localhost:5001
- **API Health**: http://localhost:5001/health
- **Playwright Health**: http://localhost:3000/health (internal)

## 🏗️ Architecture Overview

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Web Client    │◄──►│  Qwen Agent      │◄──►│   vLLM Server   │
│   (Browser)     │    │  Flask App       │    │ (Qwen3-32B)     │
└─────────────────┘    │  Port: 5001      │    │ External        │
                       └──────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌──────────────────┐
                       │ Playwright       │
                       │ Service          │
                       │ Port: 3000       │
                       └──────────────────┘
```

## 🔧 Configuration Details

### Qwen Agent Configuration

The enhanced `app.py` includes:

1. **Standard Tool Calling**: Uses only `code_interpreter` tool for maximum compatibility
2. **Smart SSL Handling**: Automatic SSL certificate management with fallbacks
3. **Enhanced Error Handling**: Robust message processing and error recovery
4. **Dynamic Web Search**: Intelligent source selection based on query type
5. **Performance Monitoring**: Built-in metrics and health checks

### Key Features

#### Web Search Capabilities
- **Multi-source Search**: Google, DuckDuckGo, domain-specific sites
- **Intelligent Routing**: Sports queries → ESPN, News → BBC/Reuters, etc.
- **Content Extraction**: Smart parsing to extract relevant information
- **Source Attribution**: Clear citation of information sources

#### Enterprise Features
- **Rate Limiting**: Configurable request limits
- **Caching**: Intelligent caching with TTL
- **Monitoring**: Health checks and metrics
- **Scalability**: Browser pool management
- **Security**: Non-root execution, resource limits

## 📊 Monitoring & Maintenance

### Health Monitoring

```bash
# Check overall system health
curl http://localhost:5001/health | jq

# Check Playwright service status
curl http://localhost:3000/health | jq

# Monitor cache performance
curl http://localhost:3000/cache/stats | jq
```

### Log Monitoring

```bash
# View application logs
docker-compose logs -f qwen-agent-chat

# View Playwright service logs
docker-compose logs -f playwright-service

# Monitor system resources
docker stats
```

### Performance Tuning

#### For High Load Environments:

1. **Scale Browser Instances**:
```yaml
environment:
  - MAX_BROWSER_INSTANCES=5
  - CONCURRENT_REQUESTS=5
```

2. **Increase Cache Duration**:
```yaml
environment:
  - CACHE_TTL_MINUTES=10
  - CACHE_MAX_KEYS=2000
```

3. **Add Redis for Distributed Caching**:
```yaml
services:
  redis:
    image: redis:7-alpine
    command: redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru
```

## 🔒 Security Considerations

### Production Security Checklist

- [ ] Change default API keys
- [ ] Enable HTTPS with proper certificates
- [ ] Configure firewall rules
- [ ] Set up log rotation
- [ ] Enable resource monitoring
- [ ] Configure backup procedures
- [ ] Set up SSL certificate renewal
- [ ] Review and limit network access

### Secure Configuration Example

```yaml
environment:
  # Use secrets for sensitive data
  - VLLM_API_KEY_FILE=/run/secrets/vllm_api_key
  - SSL_CERT_PATH=/etc/ssl/certs/app.crt
  - SSL_KEY_PATH=/etc/ssl/private/app.key

secrets:
  vllm_api_key:
    file: ./secrets/vllm_api_key.txt
```

## 🚀 Scaling for Production

### Horizontal Scaling

Deploy multiple instances behind a load balancer:

```yaml
services:
  qwen-agent-chat-1:
    # ... service config
  qwen-agent-chat-2:
    # ... service config
  
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
```

### Resource Optimization

#### Memory Optimization:
```yaml
deploy:
  resources:
    limits:
      memory: 6G    # Adjust based on usage
      cpus: '3.0'
    reservations:
      memory: 3G
      cpus: '1.5'
```

#### Storage Optimization:
```yaml
volumes:
  - /fast-ssd/playwright-cache:/ms-playwright:rw
  - /logs-volume/:/app/logs:rw
```

## 🐛 Troubleshooting

### Common Issues

#### 1. JSON Parsing Errors
**Cause**: Using `--enable-auto-tool-choice` or `--tool-call-parser hermes` with vLLM
**Solution**: Remove these switches from vLLM startup command

#### 2. SSL Certificate Errors
**Cause**: Certificate validation issues
**Solution**: Verify `VLLM_VERIFY_SSL=False` is set and SSL patches are applied

#### 3. Browser Launch Failures
**Cause**: Insufficient resources or Docker permissions
**Solution**: 
```bash
# Increase shared memory
docker run --shm-size=1g ...

# Or use tmpfs
tmpfs:
  - /dev/shm:rw,nosuid,nodev,size=1g
```

#### 4. Poor Search Performance
**Cause**: Network issues or rate limiting
**Solution**: Adjust timeout and retry settings:
```yaml
environment:
  - SEARCH_TIMEOUT=30
  - MAX_RETRIES=3
  - REQUESTS_PER_MINUTE=60
```

### Debug Mode

Enable verbose logging:
```yaml
environment:
  - DEBUG=True
  - LOG_LEVEL=debug
  - PLAYWRIGHT_DEBUG=1
```

### Performance Benchmarking

Run the included benchmark script:
```bash
python benchmark_system.py --queries 100 --concurrent 5
```

## 📈 Production Deployment

### Step-by-Step Production Setup

1. **Prepare Environment**:
```bash
# Create production directory
mkdir /opt/qwen-agent-enterprise
cd /opt/qwen-agent-enterprise

# Set up proper permissions
sudo chown -R $USER:$USER /opt/qwen-agent-enterprise
```

2. **Configure SSL/TLS**:
```bash
# Generate or obtain SSL certificates
sudo certbot certonly --standalone -d your-domain.com

# Update docker-compose for HTTPS
```

3. **Set up Monitoring**:
```bash
# Deploy with monitoring stack
docker-compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d
```

4. **Configure Backups**:
```bash
# Set up automated backups
crontab -e
# Add: 0 2 * * * /opt/qwen-agent-enterprise/backup.sh
```

5. **Performance Testing**:
```bash
# Load testing
./load_test.sh --duration 300 --users 50

# Monitor during testing
./monitor_performance.sh
```

### Maintenance Schedule

- **Daily**: Check logs and health status
- **Weekly**: Review performance metrics and optimize cache
- **Monthly**: Update dependencies and security patches
- **Quarterly**: Performance review and capacity planning

## 🔄 Updates and Maintenance

### Updating the System

```bash
# Pull latest images
docker-compose pull

# Restart with zero downtime
docker-compose up -d --force-recreate --no-deps qwen-agent-chat
docker-compose up -d --force-recreate --no-deps playwright-service
```

### Backup and Recovery

```bash
# Backup configuration and data
tar -czf qwen-agent-backup-$(date +%Y%m%d).tar.gz \
  docker-compose.yml .env data/ logs/

# Recovery
tar -xzf qwen-agent-backup-YYYYMMDD.tar.gz
docker-compose up -d
```

## 📞 Support and Community

### Getting Help

1. **Check logs first**: `docker-compose logs`
2. **Run health checks**: `curl localhost:5001/health`
3. **Test with validation script**: `python test_system_validation.py`
4. **Review this documentation**
5. **Check GitHub issues or internal support channels**

### Contributing Improvements

When making changes:
1. Test thoroughly with validation script
2. Update documentation
3. Follow security best practices
4. Consider backward compatibility

---

## 🎯 Success Metrics

Your deployment is successful when:

- ✅ All health checks pass
- ✅ Web search returns current information
- ✅ Response times < 30 seconds for complex queries
- ✅ No JSON parsing errors in logs
- ✅ SSL connections work without warnings
- ✅ System handles concurrent requests smoothly
- ✅ Cache hit rate > 20% after initial warm-up

**Remember**: The key to success is removing the problematic vLLM switches (`--enable-auto-tool-choice` and `--tool-call-parser hermes`) and using the standard Qwen Agent tool calling mechanism.