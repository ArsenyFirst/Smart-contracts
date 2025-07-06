#!/bin/bash

# =============================================================================
# Jupiter RFQ Webhook System - Quick Deployment Script
# =============================================================================

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[WARNING] $1${NC}"
}

error() {
    echo -e "${RED}[ERROR] $1${NC}"
    exit 1
}

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   error "This script should not be run as root for security reasons"
fi

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to install Docker
install_docker() {
    log "Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    rm get-docker.sh
    
    # Install Docker Compose
    log "Installing Docker Compose..."
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    
    log "Docker installation completed. Please log out and log back in to apply group changes."
}

# Function to setup environment
setup_environment() {
    log "Setting up environment..."
    
    # Copy environment file
    if [[ ! -f .env ]]; then
        cp .env.webhook.example .env
        log "Created .env file from template"
    else
        warn ".env file already exists, skipping copy"
    fi
    
    # Create necessary directories
    mkdir -p logs data nginx/ssl nginx/logs config
    log "Created necessary directories"
    
    # Set permissions
    chmod 755 logs data nginx
    chmod 600 .env
    log "Set proper permissions"
}

# Function to configure nginx
setup_nginx_config() {
    local domain=$1
    local port=${2:-8080}
    
    log "Setting up Nginx configuration for domain: $domain"
    
    mkdir -p nginx
    
    cat > nginx/nginx.conf << EOF
server {
    listen 80;
    server_name $domain;
    
    # Redirect HTTP to HTTPS
    return 301 https://\$server_name\$request_uri;
}

server {
    listen 443 ssl;
    server_name $domain;
    
    # SSL configuration
    ssl_certificate /etc/nginx/ssl/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    
    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload";
    
    # Rate limiting
    limit_req_zone \$binary_remote_addr zone=webhook:10m rate=30r/m;
    
    location / {
        proxy_pass http://jupiter-webhook:$port;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # Timeouts
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
    }
    
    location /webhook/ {
        limit_req zone=webhook burst=10 nodelay;
        
        proxy_pass http://jupiter-webhook:$port;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # Special settings for webhooks
        proxy_buffering off;
        proxy_cache off;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }
    
    # Health check endpoint
    location /health {
        access_log off;
        proxy_pass http://jupiter-webhook:$port/;
    }
}
EOF
    
    log "Nginx configuration created"
}

# Function to setup SSL with Let's Encrypt
setup_ssl() {
    local domain=$1
    local email=$2
    
    log "Setting up SSL certificate for domain: $domain"
    
    if ! command_exists certbot; then
        log "Installing certbot..."
        sudo apt update
        sudo apt install -y certbot
    fi
    
    # Generate certificate
    sudo certbot certonly --standalone \
        --email "$email" \
        --agree-tos \
        --no-eff-email \
        -d "$domain"
    
    # Copy certificates to nginx directory
    sudo cp "/etc/letsencrypt/live/$domain/fullchain.pem" nginx/ssl/
    sudo cp "/etc/letsencrypt/live/$domain/privkey.pem" nginx/ssl/
    sudo chown $USER:$USER nginx/ssl/*.pem
    
    log "SSL certificate installed"
}

# Function to configure systemd service
setup_systemd_service() {
    local working_dir=$(pwd)
    local user=$(whoami)
    
    log "Setting up systemd service..."
    
    sudo tee /etc/systemd/system/jupiter-webhook.service > /dev/null << EOF
[Unit]
Description=Jupiter RFQ Webhook Server
After=network.target docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$working_dir
User=$user
Group=docker

# Start command
ExecStart=/usr/local/bin/docker-compose up -d

# Stop command
ExecStop=/usr/local/bin/docker-compose down

# Reload command
ExecReload=/usr/local/bin/docker-compose restart

[Install]
WantedBy=multi-user.target
EOF
    
    sudo systemctl daemon-reload
    sudo systemctl enable jupiter-webhook
    
    log "Systemd service configured"
}

# Function to test deployment
test_deployment() {
    local domain=${1:-localhost}
    local port=${2:-8080}
    local use_https=${3:-false}
    
    log "Testing deployment..."
    
    # Wait for services to start
    sleep 10
    
    # Test health endpoint
    if [[ "$use_https" == "true" ]]; then
        local url="https://$domain"
    else
        local url="http://$domain:$port"
    fi
    
    log "Testing health endpoint: $url"
    
    if curl -f -s "$url" > /dev/null; then
        log "✅ Health check passed"
    else
        error "❌ Health check failed"
    fi
    
    # Test webhook config endpoint
    log "Testing webhook config endpoint..."
    if curl -f -s "$url/webhook/config" > /dev/null; then
        log "✅ Webhook config endpoint working"
    else
        warn "⚠️ Webhook config endpoint not responding"
    fi
    
    # Test webhook test endpoint
    log "Testing webhook test endpoint..."
    if curl -f -s -X POST "$url/webhook/test" > /dev/null; then
        log "✅ Webhook test endpoint working"
    else
        warn "⚠️ Webhook test endpoint not responding"
    fi
    
    # Show stats
    log "Deployment statistics:"
    curl -s "$url/stats" | jq '.' 2>/dev/null || curl -s "$url/stats"
}

# Function to show deployment summary
show_summary() {
    local domain=$1
    local use_https=${2:-false}
    
    log "🎉 Deployment completed successfully!"
    echo
    echo "==================================================================="
    echo "             Jupiter RFQ Webhook System - Deployed"
    echo "==================================================================="
    echo
    if [[ "$use_https" == "true" ]]; then
        echo "🌐 Webhook URL: https://$domain/webhook/jupiter/rfq"
        echo "📊 Health Check: https://$domain/"
        echo "📈 Stats: https://$domain/stats"
        echo "⚙️  Config: https://$domain/webhook/config"
    else
        echo "🌐 Webhook URL: http://$domain:8080/webhook/jupiter/rfq"
        echo "📊 Health Check: http://$domain:8080/"
        echo "📈 Stats: http://$domain:8080/stats"
        echo "⚙️  Config: http://$domain:8080/webhook/config"
    fi
    echo
    echo "📝 Next steps:"
    echo "   1. Register your webhook URL with Jupiter team"
    echo "   2. Configure your .env file with proper secrets"
    echo "   3. Set up monitoring and alerts"
    echo "   4. Test with real RFQ data"
    echo
    echo "📋 Management commands:"
    echo "   - Start: docker-compose up -d"
    echo "   - Stop: docker-compose down"
    echo "   - Logs: docker-compose logs -f"
    echo "   - Status: docker-compose ps"
    echo
    echo "==================================================================="
}

# Main deployment function
main() {
    echo "==================================================================="
    echo "        Jupiter RFQ Webhook System - Quick Deployment"
    echo "==================================================================="
    echo
    
    # Parse command line arguments
    local DEPLOYMENT_TYPE=""
    local DOMAIN=""
    local EMAIL=""
    local SKIP_DOCKER_INSTALL=false
    local SKIP_SSL=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --local)
                DEPLOYMENT_TYPE="local"
                shift
                ;;
            --vps)
                DEPLOYMENT_TYPE="vps"
                DOMAIN="$2"
                EMAIL="$3"
                shift 3
                ;;
            --skip-docker)
                SKIP_DOCKER_INSTALL=true
                shift
                ;;
            --skip-ssl)
                SKIP_SSL=true
                shift
                ;;
            -h|--help)
                echo "Usage: $0 [OPTIONS]"
                echo
                echo "Options:"
                echo "  --local                 Local development deployment"
                echo "  --vps DOMAIN EMAIL      VPS production deployment"
                echo "  --skip-docker          Skip Docker installation"
                echo "  --skip-ssl             Skip SSL setup"
                echo "  -h, --help             Show this help message"
                echo
                echo "Examples:"
                echo "  $0 --local"
                echo "  $0 --vps yourdomain.com admin@yourdomain.com"
                exit 0
                ;;
            *)
                error "Unknown option: $1"
                ;;
        esac
    done
    
    if [[ -z "$DEPLOYMENT_TYPE" ]]; then
        error "Please specify deployment type: --local or --vps DOMAIN EMAIL"
    fi
    
    # Check prerequisites
    log "Checking prerequisites..."
    
    if [[ "$SKIP_DOCKER_INSTALL" == "false" ]]; then
        if ! command_exists docker; then
            install_docker
            warn "Docker installed. Please log out and log back in, then run this script again."
            exit 0
        fi
        
        if ! command_exists docker-compose; then
            error "Docker Compose not found. Please install it manually."
        fi
    fi
    
    if ! command_exists curl; then
        log "Installing curl..."
        sudo apt update && sudo apt install -y curl
    fi
    
    if ! command_exists jq; then
        log "Installing jq..."
        sudo apt update && sudo apt install -y jq
    fi
    
    # Setup environment
    setup_environment
    
    # Deployment specific setup
    case $DEPLOYMENT_TYPE in
        local)
            log "Setting up local development deployment..."
            
            # Update docker-compose for local development
            sed -i 's/- "80:80"/# - "80:80"/' docker-compose.yml
            sed -i 's/- "443:443"/# - "443:443"/' docker-compose.yml
            
            # Start services
            log "Starting services..."
            docker-compose up -d jupiter-webhook
            
            # Test deployment
            test_deployment localhost 8080 false
            
            # Show summary
            show_summary localhost false
            ;;
            
        vps)
            if [[ -z "$DOMAIN" ]] || [[ -z "$EMAIL" ]]; then
                error "Domain and email are required for VPS deployment"
            fi
            
            log "Setting up VPS production deployment for domain: $DOMAIN"
            
            # Setup nginx config
            setup_nginx_config "$DOMAIN"
            
            # Setup SSL if not skipped
            if [[ "$SKIP_SSL" == "false" ]]; then
                setup_ssl "$DOMAIN" "$EMAIL"
            fi
            
            # Setup systemd service
            setup_systemd_service
            
            # Update environment with domain
            sed -i "s/DOMAIN_NAME=.*/DOMAIN_NAME=$DOMAIN/" .env
            sed -i "s|PUBLIC_WEBHOOK_URL=.*|PUBLIC_WEBHOOK_URL=https://$DOMAIN/webhook/jupiter/rfq|" .env
            
            # Start services
            log "Starting services..."
            docker-compose up -d
            
            # Start systemd service
            sudo systemctl start jupiter-webhook
            
            # Test deployment
            if [[ "$SKIP_SSL" == "false" ]]; then
                test_deployment "$DOMAIN" 443 true
                show_summary "$DOMAIN" true
            else
                test_deployment "$DOMAIN" 80 false
                show_summary "$DOMAIN" false
            fi
            ;;
    esac
    
    log "Deployment script completed!"
}

# Run main function with all arguments
main "$@"