#!/bin/bash
# Docker development helper script

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🐳 Docker Development Helper${NC}"
echo "=================================="

# Function to check if container is running
check_container() {
    if docker ps --format "table {{.Names}}" | grep -q "hotspot-portal-dev-frontend"; then
        return 0
    else
        return 1
    fi
}

# Function to start development
start_dev() {
    echo -e "${GREEN}🚀 Starting development container...${NC}"
    
    if check_container; then
        echo -e "${YELLOW}⚠️  Container already running${NC}"
        echo -e "${BLUE}🔄 Restarting development server...${NC}"
        docker exec hotspot-portal-dev-frontend /app/scripts/dev-start.sh
    else
        echo -e "${BLUE}📦 Building and starting container...${NC}"
        docker-compose -f docker-compose.dev.yml up -d --build
        
        echo -e "${GREEN}✅ Container started!${NC}"
        echo -e "${BLUE}📊 Checking logs...${NC}"
        sleep 3
        docker logs hotspot-portal-dev-frontend --tail 20
    fi
    
    echo ""
    echo -e "${GREEN}🌐 Application URLs:${NC}"
    echo "   📱 Frontend: https://dev.sobigidul.com"
    echo "   🔧 Direct:   http://localhost:3000"
    echo ""
    echo -e "${BLUE}📋 Useful commands:${NC}"
    echo "   🔍 Logs:     docker logs hotspot-portal-dev-frontend -f"
    echo "   🚀 Restart:  docker exec hotspot-portal-dev-frontend /app/scripts/dev-start.sh"
    echo "   🛑 Stop:     docker-compose -f docker-compose.dev.yml down"
}

# Function to show logs
show_logs() {
    echo -e "${BLUE}📊 Showing container logs...${NC}"
    docker logs hotspot-portal-dev-frontend -f
}

# Function to stop development
stop_dev() {
    echo -e "${RED}🛑 Stopping development container...${NC}"
    docker-compose -f docker-compose.dev.yml down
    echo -e "${GREEN}✅ Container stopped!${NC}"
}

# Function to restart development server
restart_dev() {
    echo -e "${YELLOW}🔄 Restarting development server...${NC}"
    if check_container; then
        docker exec hotspot-portal-dev-frontend /app/scripts/dev-start.sh
    else
        echo -e "${RED}❌ Container not running. Use 'start' command first.${NC}"
    fi
}

# Function to exec into container
exec_container() {
    echo -e "${BLUE}🔧 Executing into container...${NC}"
    if check_container; then
        docker exec -it hotspot-portal-dev-frontend /bin/bash
    else
        echo -e "${RED}❌ Container not running. Use 'start' command first.${NC}"
    fi
}

# Main menu
case "$1" in
    "start")
        start_dev
        ;;
    "stop")
        stop_dev
        ;;
    "restart")
        restart_dev
        ;;
    "logs")
        show_logs
        ;;
    "exec")
        exec_container
        ;;
    "status")
        if check_container; then
            echo -e "${GREEN}✅ Container is running${NC}"
            docker ps --filter "name=hotspot-portal-dev-frontend" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
        else
            echo -e "${RED}❌ Container is not running${NC}"
        fi
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|logs|exec|status}"
        echo ""
        echo "Commands:"
        echo "  start   - Start development container"
        echo "  stop    - Stop development container"
        echo "  restart - Restart development server inside container"
        echo "  logs    - Show container logs"
        echo "  exec    - Execute shell inside container"
        echo "  status  - Check container status"
        exit 1
        ;;
esac
