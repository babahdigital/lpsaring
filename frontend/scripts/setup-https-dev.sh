#!/bin/bash

# Script untuk setup HTTPS development dengan HMR yang bekerja
echo "🔧 Setting up HTTPS Development Environment..."

# Check if mkcert is installed
if ! command -v mkcert &> /dev/null; then
    echo "❌ mkcert is not installed. Installing..."
    
    # Install mkcert based on OS
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        curl -JLO "https://dl.filippo.io/mkcert/latest?for=linux/amd64"
        chmod +x mkcert-v*-linux-amd64
        sudo mv mkcert-v*-linux-amd64 /usr/local/bin/mkcert
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        brew install mkcert
    else
        echo "❌ Unsupported OS. Please install mkcert manually: https://github.com/FiloSottile/mkcert"
        exit 1
    fi
fi

# Setup local CA
echo "🔒 Setting up local Certificate Authority..."
mkcert -install

# Create certificates for development
echo "📜 Creating SSL certificates..."
mkdir -p .ssl
mkcert -key-file .ssl/key.pem -cert-file .ssl/cert.pem localhost 127.0.0.1 dev.sobigidul.com ::1

# Create environment file for HTTPS
echo "⚙️ Creating HTTPS environment configuration..."
cat > .env.https << EOF
# HTTPS Development Configuration
NUXT_DEV_HTTPS=true
NUXT_SSL_CERT=.ssl/cert.pem
NUXT_SSL_KEY=.ssl/key.pem
NUXT_HOST=0.0.0.0
NUXT_PORT=3000

# HMR Configuration
NUXT_HMR_PROTOCOL=wss
NUXT_HMR_HOST=dev.sobigidul.com
NUXT_HMR_PORT=443
EOF

# Create npm scripts for HTTPS development
echo "📝 Updating package.json with HTTPS scripts..."
if command -v jq &> /dev/null; then
    # Use jq if available for safe JSON editing
    jq '.scripts["dev:https"] = "cp .env.https .env && nuxt dev --https --ssl-cert .ssl/cert.pem --ssl-key .ssl/key.pem"' package.json > package.json.tmp && mv package.json.tmp package.json
    jq '.scripts["dev:http"] = "rm -f .env && nuxt dev"' package.json > package.json.tmp && mv package.json.tmp package.json
else
    echo "⚠️ jq not found. Please manually add these scripts to package.json:"
    echo '  "dev:https": "cp .env.https .env && nuxt dev --https --ssl-cert .ssl/cert.pem --ssl-key .ssl/key.pem"'
    echo '  "dev:http": "rm -f .env && nuxt dev"'
fi

echo ""
echo "✅ HTTPS Development Setup Complete!"
echo ""
echo "🚀 Usage:"
echo "  npm run dev:https  - Start with HTTPS (for production-like testing)"
echo "  npm run dev:http   - Start with HTTP (for local development)"
echo "  npm run dev        - Start with current configuration"
echo ""
echo "🔒 HTTPS URLs:"
echo "  https://localhost:3000/"
echo "  https://dev.sobigidul.com:3000/ (if DNS is configured)"
echo ""
echo "💡 Tips:"
echo "  - Use dev:https when testing with dev.sobigidul.com domain"
echo "  - Use dev:http for faster local development"
echo "  - HMR will work properly with both configurations"
echo ""
echo "🔧 Troubleshooting:"
echo "  - If certificate warnings appear, run: mkcert -install"
echo "  - For DNS issues, add '127.0.0.1 dev.sobigidul.com' to /etc/hosts"
