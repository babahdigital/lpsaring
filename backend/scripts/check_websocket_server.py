"""
WebSocket connection diagnostic tool for backend

This script tests the internal WebSocket connectivity within the backend container
to help diagnose issues with WebSocket connections that might be causing login problems.

Usage:
docker-compose exec backend python scripts/check_websocket_server.py
"""

import os
import sys
import socket
import threading
import time
from datetime import datetime

# Color codes for terminal
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

def check_websocket_server(host='localhost', port=5000, path='/api/ws/client-updates'):
    """Check if the WebSocket server is running and reachable"""
    print(f"{YELLOW}[CHECKING WEBSOCKET SERVER]{RESET} {host}:{port}{path}")
    
    try:
        # First try a simple TCP connection to the port
        start = datetime.now()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        result = s.connect_ex((host, port))
        end = datetime.now()
        duration = (end - start).total_seconds()
        
        if result == 0:
            print(f"{GREEN}[SUCCESS]{RESET} TCP connection to {host}:{port} established (took {duration:.3f}s)")
        else:
            print(f"{RED}[ERROR]{RESET} TCP connection to {host}:{port} failed, error code: {result}")
            return False
        
        s.close()
        
        # Now try to perform a WebSocket handshake
        try:
            import requests
            
            # First check regular HTTP to see if the server is responding
            http_url = f"http://{host}:{port}/api/health-check"
            try:
                resp = requests.get(http_url, timeout=5)
                print(f"{GREEN}[SUCCESS]{RESET} HTTP health check: Status {resp.status_code}")
            except Exception as e:
                print(f"{RED}[ERROR]{RESET} HTTP health check failed: {e}")
            
            # Try a WebSocket upgrade request manually
            ws_headers = {
                'Connection': 'Upgrade',
                'Upgrade': 'websocket',
                'Sec-WebSocket-Key': 'dGhlIHNhbXBsZSBub25jZQ==',
                'Sec-WebSocket-Version': '13',
            }
            
            ws_url = f"http://{host}:{port}{path}"
            try:
                resp = requests.get(ws_url, headers=ws_headers, timeout=5)
                if resp.status_code == 101:
                    print(f"{GREEN}[SUCCESS]{RESET} WebSocket upgrade successful")
                    return True
                else:
                    print(f"{RED}[ERROR]{RESET} WebSocket upgrade failed: Status {resp.status_code}")
                    print(f"{BLUE}[RESPONSE]{RESET} Headers: {resp.headers}")
                    print(f"{BLUE}[RESPONSE]{RESET} Content: {resp.text[:200]}...")
                    return False
            except Exception as e:
                print(f"{RED}[ERROR]{RESET} WebSocket upgrade request failed: {e}")
                return False
                
        except ImportError:
            print(f"{YELLOW}[WARNING]{RESET} Python requests module not available, skipping HTTP checks")
            return None
        
    except Exception as e:
        print(f"{RED}[ERROR]{RESET} WebSocket server check failed: {e}")
        return False

def check_websocket_config_files():
    """Check WebSocket configuration files"""
    print(f"\n{YELLOW}[CHECKING WEBSOCKET CONFIG FILES]{RESET}")
    
    # Check Flask WebSocket routes
    websocket_routes_path = "app/infrastructure/http/websocket_routes.py"
    if not os.path.exists(websocket_routes_path):
        print(f"{RED}[ERROR]{RESET} Cannot find WebSocket routes file: {websocket_routes_path}")
    else:
        print(f"{GREEN}[FOUND]{RESET} WebSocket routes file: {websocket_routes_path}")
        
        try:
            with open(websocket_routes_path, 'r') as f:
                content = f.read()
                
            # Check for key WebSocket patterns
            patterns = {
                "Client updates route": "/client-updates",
                "WebSocket decorator": "@websocket",
                "Socket IO": "socketio",
                "Legacy endpoint": "/api/ws/client-updates",
            }
            
            for name, pattern in patterns.items():
                if pattern in content:
                    print(f"{GREEN}[FOUND]{RESET} {name} in WebSocket routes")
                else:
                    print(f"{RED}[MISSING]{RESET} {name} not found in WebSocket routes")
        
        except Exception as e:
            print(f"{RED}[ERROR]{RESET} Failed to analyze WebSocket routes file: {e}")
    
    # Check Nginx WebSocket config
    nginx_ws_config = "../../infrastructure/nginx/config/proxy_params_ws.conf"
    if not os.path.exists(nginx_ws_config):
        print(f"{RED}[ERROR]{RESET} Cannot find Nginx WebSocket config file: {nginx_ws_config}")
    else:
        print(f"{GREEN}[FOUND]{RESET} Nginx WebSocket config file: {nginx_ws_config}")
        
        try:
            with open(nginx_ws_config, 'r') as f:
                content = f.read()
            
            # Check for key Nginx WebSocket patterns
            patterns = {
                "Upgrade header": "Upgrade",
                "Connection header": "Connection",
                "HTTP 1.1": "http_version 1.1",
                "WebSocket protocol": "websocket",
            }
            
            for name, pattern in patterns.items():
                if pattern.lower() in content.lower():
                    print(f"{GREEN}[FOUND]{RESET} {name} in Nginx WebSocket config")
                else:
                    print(f"{RED}[MISSING]{RESET} {name} not found in Nginx WebSocket config")
                    
            # Specifically check for HTTP 1.1 which is critical for WebSockets
            if "http_version 1.1" not in content.lower():
                print(f"{YELLOW}[RECOMMENDATION]{RESET} Add 'proxy_http_version 1.1;' to Nginx WebSocket config")
        
        except Exception as e:
            print(f"{RED}[ERROR]{RESET} Failed to analyze Nginx WebSocket config file: {e}")

def check_browser_websocket_connection():
    """Generate HTML to test WebSocket connection from browser"""
    print(f"\n{YELLOW}[GENERATING BROWSER TEST]{RESET}")
    
    html_file = "websocket_test.html"
    
    html_content = """<!DOCTYPE html>
<html>
<head>
    <title>WebSocket Test Page</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 20px;
        }
        #status {
            font-weight: bold;
            margin-bottom: 10px;
        }
        #log {
            border: 1px solid #ccc;
            padding: 10px;
            height: 300px;
            overflow-y: scroll;
            font-family: monospace;
            background-color: #f5f5f5;
        }
        .success {
            color: green;
        }
        .error {
            color: red;
        }
        .warning {
            color: orange;
        }
        .info {
            color: blue;
        }
        button {
            padding: 8px 12px;
            margin: 5px;
            cursor: pointer;
        }
    </style>
</head>
<body>
    <h1>WebSocket Connection Test</h1>
    
    <div id="status">Status: Not connected</div>
    
    <div>
        <button id="connectBtn">Connect</button>
        <button id="disconnectBtn" disabled>Disconnect</button>
        <button id="pingBtn" disabled>Send Ping</button>
    </div>
    
    <h3>Connection URL:</h3>
    <select id="urlSelect" style="width: 100%; margin-bottom: 10px;">
        <option value="ws://localhost:5000/api/ws/client-updates">ws://localhost:5000/api/ws/client-updates (Backend Direct)</option>
        <option value="ws://localhost:5000/client-updates">ws://localhost:5000/client-updates (Backend Direct - Alternate)</option>
        <option value="ws://localhost/api/ws/client-updates">ws://localhost/api/ws/client-updates (Local Nginx)</option>
        <option value="wss://dev.sobigidul.com/api/ws/client-updates">wss://dev.sobigidul.com/api/ws/client-updates (Production)</option>
        <option value="custom">Custom URL...</option>
    </select>
    <input type="text" id="customUrl" style="width: 100%; display: none;" placeholder="Enter custom WebSocket URL...">
    
    <h3>Connection Log:</h3>
    <div id="log"></div>
    
    <script>
        let socket = null;
        const status = document.getElementById('status');
        const log = document.getElementById('log');
        const connectBtn = document.getElementById('connectBtn');
        const disconnectBtn = document.getElementById('disconnectBtn');
        const pingBtn = document.getElementById('pingBtn');
        const urlSelect = document.getElementById('urlSelect');
        const customUrl = document.getElementById('customUrl');
        
        function logMessage(message, type = 'info') {
            const timestamp = new Date().toISOString();
            const entry = document.createElement('div');
            entry.className = type;
            entry.textContent = `[${timestamp}] ${message}`;
            log.appendChild(entry);
            log.scrollTop = log.scrollHeight;
        }
        
        function updateButtonStates(connected) {
            connectBtn.disabled = connected;
            disconnectBtn.disabled = !connected;
            pingBtn.disabled = !connected;
        }
        
        connectBtn.addEventListener('click', function() {
            try {
                let url;
                if (urlSelect.value === 'custom') {
                    url = customUrl.value;
                } else {
                    url = urlSelect.value;
                }
                
                if (!url) {
                    logMessage('Please enter a valid WebSocket URL', 'error');
                    return;
                }
                
                logMessage(`Connecting to ${url}...`);
                socket = new WebSocket(url);
                
                socket.onopen = function(e) {
                    status.textContent = 'Status: Connected';
                    status.className = 'success';
                    logMessage('Connection established', 'success');
                    updateButtonStates(true);
                };
                
                socket.onmessage = function(event) {
                    let msg;
                    try {
                        msg = JSON.parse(event.data);
                        logMessage(`Received message: ${JSON.stringify(msg)}`, 'info');
                    } catch (e) {
                        logMessage(`Received raw message: ${event.data}`, 'info');
                    }
                };
                
                socket.onclose = function(event) {
                    if (event.wasClean) {
                        logMessage(`Connection closed cleanly, code=${event.code} reason=${event.reason}`, 'warning');
                    } else {
                        logMessage('Connection died', 'error');
                    }
                    status.textContent = 'Status: Disconnected';
                    status.className = 'error';
                    updateButtonStates(false);
                };
                
                socket.onerror = function(error) {
                    logMessage(`Error: ${error.message}`, 'error');
                    status.textContent = 'Status: Error';
                    status.className = 'error';
                };
                
            } catch (e) {
                logMessage(`Failed to connect: ${e.message}`, 'error');
            }
        });
        
        disconnectBtn.addEventListener('click', function() {
            if (socket) {
                socket.close();
                logMessage('Disconnected by user', 'warning');
            }
        });
        
        pingBtn.addEventListener('click', function() {
            if (socket && socket.readyState === WebSocket.OPEN) {
                const pingMessage = JSON.stringify({
                    type: 'ping',
                    timestamp: new Date().toISOString()
                });
                socket.send(pingMessage);
                logMessage(`Sent: ${pingMessage}`, 'info');
            } else {
                logMessage('Cannot send message, connection not open', 'error');
            }
        });
        
        urlSelect.addEventListener('change', function() {
            if (this.value === 'custom') {
                customUrl.style.display = 'block';
            } else {
                customUrl.style.display = 'none';
            }
        });
        
        // Initial setup
        logMessage('WebSocket test page loaded', 'info');
        logMessage('Click "Connect" to test WebSocket connection', 'info');
    </script>
</body>
</html>
"""
    
    try:
        with open(html_file, 'w') as f:
            f.write(html_content)
        
        print(f"{GREEN}[SUCCESS]{RESET} Created WebSocket test file: {html_file}")
        print(f"{YELLOW}[INSTRUCTIONS]{RESET} To test WebSocket connection from a browser:")
        print(f"1. Open the file {html_file} in a web browser")
        print(f"2. Select the WebSocket URL to test")
        print(f"3. Click 'Connect' to test the connection")
        print(f"4. Check the connection log for results")
        
    except Exception as e:
        print(f"{RED}[ERROR]{RESET} Failed to create WebSocket test file: {e}")

def main():
    """Main function"""
    print(f"{YELLOW}{'='*50}{RESET}")
    print(f"{YELLOW}[WEBSOCKET DIAGNOSTIC TOOL]{RESET}")
    print(f"{YELLOW}{'='*50}{RESET}")
    
    check_websocket_server()
    check_websocket_config_files()
    check_browser_websocket_connection()
    
    print(f"\n{YELLOW}[RECOMMENDATIONS]{RESET}")
    print(f"1. Ensure 'proxy_http_version 1.1;' is set in Nginx WebSocket config")
    print(f"2. Check that Redis is running properly as it's used for WebSocket messaging")
    print(f"3. Test WebSocket connection using the generated HTML file")
    print(f"4. Check backend logs for WebSocket connection errors")
    print(f"5. Verify frontend code is handling WebSocket reconnection properly")

if __name__ == "__main__":
    main()
