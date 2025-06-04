#!/bin/bash

echo "🔍 Validating project structure..."

# Check required directories
dirs=(
    "templates"
    "playwright-service"
    "data/playwright-cache"
    "logs"
    "nginx/ssl"
    "monitoring/prometheus"
    "secrets"
)

for dir in "${dirs[@]}"; do
    if [ -d "$dir" ]; then
        echo "✅ Directory exists: $dir"
    else
        echo "❌ Missing directory: $dir"
    fi
done

# Check required files that should be created
files=(
    ".env"
    ".gitignore"
    "README.md"
    "monitoring/prometheus/prometheus.yml"
)

for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        echo "✅ File exists: $file"
    else
        echo "❌ Missing file: $file"
    fi
done

echo ""
echo "📋 Files you need to create from artifacts:"
needed_files=(
    "app.py"
    "requirements.txt"
    "Dockerfile"
    "docker-compose.yml"
    "templates/index.html"
    "playwright-service/server.js"
    "playwright-service/package.json"
    "playwright-service/Dockerfile"
    "deploy.sh"
)

for file in "${needed_files[@]}"; do
    if [ -f "$file" ]; then
        echo "✅ $file"
    else
        echo "⏳ TODO: $file"
    fi
done

echo ""
echo "🎯 Next steps:"
echo "1. Copy artifact contents to the TODO files above"
echo "2. Update .env with your vLLM configuration" 
echo "3. Make deploy.sh executable: chmod +x deploy.sh"
echo "4. Deploy: ./deploy.sh --test"
