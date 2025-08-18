#!/bin/bash
# Script Deployment untuk Raspberry Pi 4
# File: scripts/deploy-raspberry-pi.sh

set -e  # Exit on any error

echo "🚀 Starting Hotspot Portal deployment untuk Raspberry Pi 4..."

# Colors untuk output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function untuk print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running on Raspberry Pi
check_raspberry_pi() {
    print_status "Checking sistem..."
    
    if [ -f /proc/cpuinfo ]; then
        if grep -q "Raspberry Pi" /proc/cpuinfo; then
            print_success "Raspberry Pi terdeteksi"
            
            # Check memory
            TOTAL_MEM=$(free -m | awk 'NR==2{printf "%.0f", $2}')
            if [ "$TOTAL_MEM" -lt 3500 ]; then
                print_warning "Memory kurang dari 4GB ($TOTAL_MEM MB). Deployment akan menggunakan konfigurasi low-memory."
                export LOW_MEMORY=true
            else
                print_success "Memory mencukupi: ${TOTAL_MEM}MB"
            fi
        else
            print_warning "Bukan Raspberry Pi, melanjutkan deployment..."
        fi
    fi
}

# Setup environment
setup_environment() {
    print_status "Setting up environment untuk Raspberry Pi 4..."
    
    # Install dependencies jika belum ada
    if ! command -v docker &> /dev/null; then
        print_status "Installing Docker..."
        curl -fsSL https://get.docker.com -o get-docker.sh
        sh get-docker.sh
        sudo usermod -aG docker $USER
        print_success "Docker installed"
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        print_status "Installing Docker Compose..."
        sudo apt-get update
        sudo apt-get install -y docker-compose-plugin
        print_success "Docker Compose installed"
    fi
    
    # Optimize Docker untuk Raspberry Pi 4
    if [ ! -f /etc/docker/daemon.json ]; then
        print_status "Optimizing Docker for Raspberry Pi 4..."
        sudo tee /etc/docker/daemon.json > /dev/null <<EOF
{
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "10m",
        "max-file": "3"
    },
    "storage-driver": "overlay2",
    "default-ulimits": {
        "nofile": {
            "Name": "nofile",
            "Hard": 64000,
            "Soft": 64000
        }
    }
}
EOF
        sudo systemctl restart docker
        print_success "Docker optimized"
    fi
}

# Clear cache
clear_all_cache() {
    print_status "🧹 Clearing all cache untuk fresh deployment..."
    
    # Clear Docker cache
    docker system prune -f --volumes
    
    # Clear application cache
    rm -rf ./backend/__pycache__ 2>/dev/null || true
    rm -rf ./backend/.cache/* 2>/dev/null || true
    rm -rf ./frontend/.nuxt 2>/dev/null || true
    rm -rf ./frontend/node_modules/.cache 2>/dev/null || true
    
    print_success "Cache cleared"
}

# Build and deploy
deploy_application() {
    print_status "Building dan deploying aplikasi..."
    
    # Check environment files
    if [ ! -f ./backend/.env.prod ]; then
        print_error "File ./backend/.env.prod tidak ditemukan!"
        exit 1
    fi
    
    if [ ! -f ./frontend/.env.prod ]; then
        print_error "File ./frontend/.env.prod tidak ditemukan!"
        exit 1
    fi
    
    # Stop existing containers
    print_status "Stopping existing containers..."
    docker-compose -f docker-compose.prod.yml down --remove-orphans || true
    
    # Build dengan optimasi untuk Raspberry Pi 4
    print_status "Building containers untuk Raspberry Pi 4..."
    DOCKER_BUILDKIT=1 docker-compose -f docker-compose.prod.yml build --no-cache
    
    # Start services dengan dependencies
    print_status "Starting services..."
    docker-compose -f docker-compose.prod.yml up -d
    
    # Wait for services to be healthy
    print_status "Waiting for services to be ready..."
    sleep 30
    
    # Check health
    check_services_health
}

# Check service health
check_services_health() {
    print_status "Checking service health..."
    
    services=("db" "redis" "backend" "frontend")
    
    for service in "${services[@]}"; do
        print_status "Checking $service..."
        
        max_attempts=30
        attempts=0
        
        while [ $attempts -lt $max_attempts ]; do
            if docker-compose -f docker-compose.prod.yml ps $service | grep -q "healthy\|Up"; then
                print_success "$service is healthy"
                break
            fi
            
            attempts=$((attempts+1))
            sleep 10
            
            if [ $attempts -eq $max_attempts ]; then
                print_error "$service is not healthy after ${max_attempts} attempts"
                docker-compose -f docker-compose.prod.yml logs $service
                exit 1
            fi
        done
    done
}

# Setup monitoring
setup_monitoring() {
    print_status "Setting up monitoring..."
    
    # Create monitoring script
    cat > /tmp/hotspot-monitor.sh << 'EOF'
#!/bin/bash
# Hotspot Portal Monitoring Script

LOG_FILE="/var/log/hotspot-portal-monitor.log"

log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> $LOG_FILE
}

# Check services
services=("hotspot-portal-prod-db" "hotspot-portal-prod-redis" "hotspot-portal-prod-backend" "hotspot-portal-prod-frontend")

for service in "${services[@]}"; do
    if ! docker ps | grep -q $service; then
        log_message "ERROR: Service $service is down"
        docker-compose -f /path/to/docker-compose.prod.yml restart $service
        log_message "INFO: Restarted service $service"
    fi
done

# Check memory usage
MEMORY_USAGE=$(free | grep Mem | awk '{printf("%.1f"), $3/$2 * 100.0}')
if (( $(echo "$MEMORY_USAGE > 90" | bc -l) )); then
    log_message "WARNING: High memory usage: ${MEMORY_USAGE}%"
fi

# Check disk space
DISK_USAGE=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
if [ "$DISK_USAGE" -gt 80 ]; then
    log_message "WARNING: High disk usage: ${DISK_USAGE}%"
fi
EOF

    sudo cp /tmp/hotspot-monitor.sh /usr/local/bin/hotspot-monitor.sh
    sudo chmod +x /usr/local/bin/hotspot-monitor.sh
    
    # Setup cron job
    (crontab -l 2>/dev/null; echo "*/5 * * * * /usr/local/bin/hotspot-monitor.sh") | crontab -
    
    print_success "Monitoring setup completed"
}

# Performance optimization untuk Raspberry Pi 4
optimize_performance() {
    print_status "Applying Raspberry Pi 4 performance optimizations..."
    
    # Optimize kernel parameters
    sudo tee -a /etc/sysctl.conf > /dev/null <<EOF

# Hotspot Portal Optimizations for Raspberry Pi 4
vm.swappiness=10
vm.vfs_cache_pressure=50
net.core.rmem_max=134217728
net.core.wmem_max=134217728
net.ipv4.tcp_rmem=4096 65536 134217728
net.ipv4.tcp_wmem=4096 65536 134217728
net.core.netdev_max_backlog=5000
net.ipv4.tcp_congestion_control=bbr
EOF
    
    # Apply immediately
    sudo sysctl -p
    
    print_success "Performance optimizations applied"
}

# Main execution
main() {
    print_status "🔥 Hotspot Portal Raspberry Pi 4 Deployment Script"
    print_status "================================================="
    
    check_raspberry_pi
    setup_environment
    clear_all_cache
    optimize_performance
    deploy_application
    setup_monitoring
    
    print_success "🎉 Deployment completed successfully!"
    print_status "Aplikasi dapat diakses di:"
    print_status "- Frontend: http://$(hostname -I | awk '{print $1}'):3000"
    print_status "- Backend API: http://$(hostname -I | awk '{print $1}'):5010"
    print_status ""
    print_status "Untuk monitoring:"
    print_status "- docker-compose -f docker-compose.prod.yml logs -f"
    print_status "- docker-compose -f docker-compose.prod.yml ps"
    print_status ""
    print_warning "Jangan lupa untuk:"
    print_warning "1. Setup firewall untuk port 3000 dan 5010"
    print_warning "2. Configure reverse proxy (Nginx) jika diperlukan"
    print_warning "3. Setup SSL certificate untuk production"
    print_warning "4. Monitor logs: tail -f /var/log/hotspot-portal-monitor.log"
}

# Run main function
main "$@"
