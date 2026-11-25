#!/bin/bash
# Space Exploration Channel - VPS Deployment Script
# Run on fresh Ubuntu 22.04+ server

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
REPO_URL="${REPO_URL:-https://github.com/yourusername/space-exploration-channel.git}"
BRANCH="${BRANCH:-main}"
INSTALL_DIR="${INSTALL_DIR:-/opt/space-exploration}"
SERVICE_USER="${SERVICE_USER:-spacebot}"
PYTHON_VERSION="${PYTHON_VERSION:-3.11}"

log() { echo -e "${GREEN}[$(date '+%H:%M:%S')] $*${NC}"; }
warn() { echo -e "${YELLOW}[$(date '+%H:%M:%S')] WARNING: $*${NC}"; }
error() { echo -e "${RED}[$(date '+%H:%M:%S')] ERROR: $*${NC}"; exit 1; }
info() { echo -e "${BLUE}[$(date '+%H:%M:%S')] INFO: $*${NC}"; }

# Check root
if [[ $EUID -ne 0 ]]; then
   error "This script must be run as root"
fi

log "Starting Space Exploration Channel deployment..."

# Update system
log "Updating system packages..."
apt-get update && apt-get upgrade -y

# Install dependencies
log "Installing system dependencies..."
apt-get install -y \
    python3 python3-pip python3-venv python3-dev \
    git curl wget unzip \
    ffmpeg \
    blender \
    nvidia-driver-535 nvidia-cuda-toolkit \
    redis-server \
    nginx \
    certbot python3-certbot-nginx \
    supervisor \
    htop iotop nethogs \
    build-essential \
    libgl1-mesa-glx libglib2.0-0

# Install DaVinci Resolve (requires manual download)
warn "DaVinci Resolve Studio must be installed manually from Blackmagic Design"
warn "Download from: https://www.blackmagicdesign.com/products/davinciresolve"
info "After download, run: ./DaVinci_Resolve_Studio_18.x.x_Linux.run -i"

# Create service user
log "Creating service user: $SERVICE_USER"
id -u "$SERVICE_USER" &>/dev/null || useradd -m -s /bin/bash "$SERVICE_USER"
usermod -aG video,render "$SERVICE_USER"

# Create directories
log "Creating directory structure..."
mkdir -p "$INSTALL_DIR"/{assets,output,cache,logs,scripts,templates,config,state,models}
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

# Clone repository
log "Cloning repository..."
cd /tmp
sudo -u "$SERVICE_USER" git clone -b "$BRANCH" "$REPO_URL" "$INSTALL_DIR/app"
cd "$INSTALL_DIR/app"

# Python environment
log "Setting up Python environment..."
sudo -u "$SERVICE_USER" python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip setuptools wheel
"$INSTALL_DIR/venv/bin/pip" install -r requirements.txt

# Install RIFE model
log "Setting up RIFE interpolation model..."
RIFE_DIR="$INSTALL_DIR/models/rife"
mkdir -p "$RIFE_DIR"
if [[ ! -f "$RIFE_DIR/rife-v4.6.pth" ]]; then
    wget -q "https://github.com/hzwer/arXiv2020-RIFE/releases/download/v4.6/rife-v4.6.pth" -O "$RIFE_DIR/rife-v4.6.pth"
    chown "$SERVICE_USER:$SERVICE_USER" "$RIFE_DIR/rife-v4.6.pth"
fi

# Install rife-ncnn-vulkan
log "Installing rife-ncnn-vulkan..."
RIFE_NCNN_VERSION="20231029-ubuntu"
wget -q "https://github.com/nihui/rife-ncnn-vulkan/releases/download/$RIFE_NCNN_VERSION/rife-ncnn-vulkan-$RIFE_NCNN_VERSION.zip" -O /tmp/rife.zip
unzip -q /tmp/rife.zip -d "$INSTALL_DIR/bin"
chmod +x "$INSTALL_DIR/bin/rife-ncnn-vulkan"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR/bin"

# Copy config template
log "Setting up configuration..."
if [[ ! -f "$INSTALL_DIR/config/orchestrator.yaml" ]]; then
    sudo -u "$SERVICE_USER" cp "$INSTALL_DIR/app/config/orchestrator.yaml.example" "$INSTALL_DIR/config/orchestrator.yaml"
    warn "Edit $INSTALL_DIR/config/orchestrator.yaml with your API keys!"
fi

# Create systemd service
log "Creating systemd service..."
cat > /etc/systemd/system/space-exploration.service << EOF
[Unit]
Description=Space Exploration Channel Automation
After=network.target redis.service
Wants=redis.service

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR/app
Environment=PYTHONPATH=$INSTALL_DIR/app
Environment=PATH=$INSTALL_DIR/venv/bin:$INSTALL_DIR/bin:/usr/local/bin:/usr/bin:/bin
Environment=CONFIG_PATH=$INSTALL_DIR/config/orchestrator.yaml
ExecStart=$INSTALL_DIR/venv/bin/python -m skills.orchestrator continuous
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal
SyslogIdentifier=space-exploration

# Resource limits
MemoryMax=16G
CPUQuota=800%

# GPU access
SupplementaryGroups=video render

[Install]
WantedBy=multi-user.target
EOF

# Create management script
log "Creating management script..."
cat > "$INSTALL_DIR/manage.sh" << 'MANAGE_EOF'
#!/bin/bash
# Space Exploration Channel - Management Script

SERVICE="space-exploration"
INSTALL_DIR="/opt/space-exploration"
APP_DIR="$INSTALL_DIR/app"
VENV="$INSTALL_DIR/venv/bin/python"

case "${1:-help}" in
    start)
        systemctl start $SERVICE
        systemctl status $SERVICE --no-pager
        ;;
    stop)
        systemctl stop $SERVICE
        ;;
    restart)
        systemctl restart $SERVICE
        systemctl status $SERVICE --no-pager
        ;;
    status)
        systemctl status $SERVICE --no-pager
        ;;
    logs)
        journalctl -u $SERVICE -f ${2:--n 100}
        ;;
    update)
        cd $APP_DIR
        git pull
        $VENV -m pip install -r requirements.txt
        systemctl restart $SERVICE
        ;;
    run)
        shift
        cd $APP_DIR
        $VENV -m skills.orchestrator "$@"
        ;;
    shell)
        cd $APP_DIR
        $VENV -m skills.orchestrator
        ;;
    backup)
        DATE=$(date +%Y%m%d_%H%M%S)
        tar -czf "/tmp/space-backup-$DATE.tar.gz" -C $INSTALL_DIR config state assets output
        echo "Backup saved to /tmp/space-backup-$DATE.tar.gz"
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|logs|update|run|shell|backup}"
        echo ""
        echo "Commands:"
        echo "  start     - Start the service"
        echo "  stop      - Stop the service"
        echo "  restart   - Restart the service"
        echo "  status    - Show service status"
        echo "  logs      - Follow service logs"
        echo "  update    - Pull latest code and restart"
        echo "  run       - Run orchestrator command (e.g., run daily)"
        echo "  shell     - Interactive orchestrator"
        echo "  backup    - Backup config, state, assets, output"
        ;;
esac
MANAGE_EOF

chmod +x "$INSTALL_DIR/manage.sh"
ln -sf "$INSTALL_DIR/manage.sh" /usr/local/bin/space-manage

# Setup nginx reverse proxy (for web dashboard if needed)
log "Configuring nginx..."
cat > /etc/nginx/sites-available/space-exploration << 'NGINX_EOF'
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
NGINX_EOF

ln -sf /etc/nginx/sites-available/space-exploration /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

# Setup logrotate
log "Configuring log rotation..."
cat > /etc/logrotate.d/space-exploration << 'LOGROTATE_EOF'
/opt/space-exploration/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 640 spacebot spacebot
}
LOGROTATE_EOF

# Enable and start services
log "Enabling services..."
systemctl daemon-reload
systemctl enable redis-server
systemctl start redis-server
systemctl enable space-exploration

log "Deployment complete!"
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Space Exploration Channel Deployed!  ${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Next steps:"
echo "1. Edit config: $INSTALL_DIR/config/orchestrator.yaml"
echo "   - Add your API keys (OpenAI, ElevenLabs, YouTube, etc.)"
echo "2. Install DaVinci Resolve Studio manually"
echo "3. Start service: space-manage start"
echo "4. Check logs: space-manage logs"
echo "5. Run manual test: space-manage run daily"
echo ""
echo "Management commands:"
echo "  space-manage start|stop|restart|status|logs|update|run|shell|backup"
echo ""
warn "Don't forget to configure your API keys in $INSTALL_DIR/config/orchestrator.yaml"