#!/bin/bash
# monitor_arp_warming.sh - Check if ARP warming thread is running continuously

echo "Monitoring ARP warming thread activity..."
echo "This script will watch the logs for ARP warming thread stop messages"
echo "If our fix is working, we should NOT see 'Requested stop for ARP warming thread' repeatedly"
echo "Press Ctrl+C to exit"
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Start time for reference
start_time=$(date +%s)

# Track stop message count
stop_count=0

echo "Starting monitoring at $(date)"
echo "----------------------------------------------"

docker logs -f hotspot-portal-dev-backend | while read -r line; do
    if [[ $line == *"[ARP-WARMING] Requested stop for ARP warming thread"* ]]; then
        stop_count=$((stop_count+1))
        current_time=$(date +%s)
        elapsed=$((current_time-start_time))
        
        echo -e "${RED}[DETECTED]${NC} ARP warming thread stop request #$stop_count (after ${elapsed}s)"
    elif [[ $line == *"[ARP-WARMING]"* ]]; then
        # Log other ARP warming related messages
        if [[ $line == *"Successfully initialized ARP warming system"* ]]; then
            echo -e "${GREEN}[GOOD]${NC} $line"
        else
            echo -e "${YELLOW}[INFO]${NC} $line"
        fi
    fi
done
