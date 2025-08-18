#!/bin/bash
# This script installs dependencies that might be missing in the Docker container

echo "Installing missing dependencies..."

# Install Flask-Sock if not already installed
pip install flask-sock || echo "Failed to install flask-sock"

# Install other dependencies that might be missing
pip install simple-websocket schedule || echo "Failed to install supporting packages"

# Check installation
pip list | grep -E "flask-sock|simple-websocket|schedule"

echo "Dependencies installation complete!"
