#!/bin/sh
# Simplified entrypoint for development

# Ensure directories exist with proper permissions
echo "Setting up development environment..."
mkdir -p /app/.nuxt /app/.output /app/node_modules
chmod -R 777 /app/.nuxt /app/.output /app/node_modules

# Check if command argument was provided
if [ $# -gt 0 ]; then
    echo "Running custom command: $@"
    exec "$@"
else
    # Default: just keep container running for manual development
    echo "Container is ready for development."
    echo "To start the dev server manually:"
    echo "  docker-compose exec frontend npm run dev"
    echo ""
    echo "To access bash shell:"
    echo "  docker-compose exec frontend bash"
    echo ""
    exec tail -f /dev/null
fi
if [ "$NODE_ENV" = "development" ]; then
    echo "Starting in DEVELOPMENT mode..."
    
    # Check if command argument was provided
    if [ $# -gt 0 ]; then
        echo "Running custom command: $@"
        exec "$@"
    else
        # Default: just keep container running for manual development
        echo "Container is ready for development."
        echo "To start the dev server manually:"
        echo "  docker-compose exec frontend npm run dev"
        echo ""
        echo "Or to debug with network tools:"
        echo "  docker-compose exec frontend bash"
        echo ""
        exec tail -f /dev/null
    fi
else
    # Production fallback
    echo "Starting in PRODUCTION mode..."
    exec node .output/server/index.mjs
fi
