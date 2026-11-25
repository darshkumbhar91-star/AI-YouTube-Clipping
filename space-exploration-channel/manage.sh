#!/bin/bash
# Space Exploration Channel - Local Management Script
# Usage: ./manage.sh {command}

set -euo pipefail

# Configuration
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"
PYTHON="$VENV_DIR/bin/python"
CONFIG_FILE="$PROJECT_DIR/config/orchestrator.yaml"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${GREEN}[$(date '+%H:%M:%S')] $*${NC}"; }
warn() { echo -e "${YELLOW}[$(date '+%H:%M:%S')] WARNING: $*${NC}"; }
error() { echo -e "${RED}[$(date '+%H:%M:%S')] ERROR: $*${NC}"; exit 1; }
info() { echo -e "${BLUE}[$(date '+%H:%M:%S')] INFO: $*${NC}"; }

# Check virtual environment
check_venv() {
    if [[ ! -f "$PYTHON" ]]; then
        error "Virtual environment not found. Run: ./manage.sh setup"
    fi
}

# Setup virtual environment and dependencies
cmd_setup() {
    log "Setting up Python virtual environment..."
    python3 -m venv "$VENV_DIR"
    "$PYTHON" -m pip install --upgrade pip setuptools wheel
    "$PYTHON" -m pip install -r "$PROJECT_DIR/requirements.txt"
    
    # Create directories
    mkdir -p "$PROJECT_DIR"/{assets/nasa,assets/branding,output,logs,cache,scripts,templates/blender,templates/davinci,config,state,models/rife}
    
    # Copy config if not exists
    if [[ ! -f "$CONFIG_FILE" ]]; then
        cp "$PROJECT_DIR/config/orchestrator.yaml.example" "$CONFIG_FILE"
        warn "Created config file at $CONFIG_FILE - EDIT IT WITH YOUR API KEYS!"
    fi
    
    # Download RIFE model
    if [[ ! -f "$PROJECT_DIR/models/rife/rife-v4.6.pth" ]]; then
        log "Downloading RIFE model..."
        wget -q "https://github.com/hzwer/arXiv2020-RIFE/releases/download/v4.6/rife-v4.6.pth" \
            -O "$PROJECT_DIR/models/rife/rife-v4.6.pth"
    fi
    
    # Install rife-ncnn-vulkan
    if [[ ! -f "$PROJECT_DIR/bin/rife-ncnn-vulkan" ]]; then
        log "Installing rife-ncnn-vulkan..."
        mkdir -p "$PROJECT_DIR/bin"
        RIFE_VERSION="20231029-ubuntu"
        wget -q "https://github.com/nihui/rife-ncnn-vulkan/releases/download/$RIFE_VERSION/rife-ncnn-vulkan-$RIFE_VERSION.zip" -O /tmp/rife.zip
        unzip -q /tmp/rife.zip -d "$PROJECT_DIR/bin"
        chmod +x "$PROJECT_DIR/bin/rife-ncnn-vulkan"
    fi
    
    log "Setup complete!"
}

# Run orchestrator commands
cmd_run() {
    check_venv
    cd "$PROJECT_DIR"
    export PYTHONPATH="$PROJECT_DIR"
    export CONFIG_PATH="$CONFIG_FILE"
    export PATH="$PROJECT_DIR/bin:$PATH"
    
    "$PYTHON" -m skills.orchestrator "$@"
}

# Run daily production batch
cmd_daily() {
    check_venv
    log "Running daily production batch..."
    cmd_run daily
}

# Run continuous mode
cmd_continuous() {
    check_venv
    log "Starting continuous automation (Ctrl+C to stop)..."
    cmd_run continuous
}

# Show status
cmd_status() {
    check_venv
    cmd_run status
}

# Show topic queue
cmd_queue() {
    check_venv
    cmd_run queue
}

# Add topic to queue
cmd_add_topic() {
    check_venv
    if [[ $# -lt 2 ]]; then
        error "Usage: ./manage.sh add-topic <title> <pillar> [priority]"
    fi
    TITLE="$1"
    PILLAR="$2"
    PRIORITY="${3:-5}"
    
    cmd_run add-topic "$TITLE" "$PILLAR" "$PRIORITY"
}

# Run analytics optimization
cmd_analytics() {
    check_venv
    log "Running analytics optimization..."
    cmd_run analytics
}

# Run Phase 1 setup
cmd_phase1() {
    check_venv
    log "Running Phase 1: Channel Setup..."
    cmd_run phase1
}

# Run Phase 2 pipeline
cmd_phase2() {
    check_venv
    log "Running Phase 2: Content Pipeline..."
    cmd_run phase2
}

# Run Phase 3 optimization
cmd_phase3() {
    check_venv
    log "Running Phase 3: Optimization..."
    cmd_run phase3
}

# Run Phase 4 scaling
cmd_phase4() {
    check_venv
    log "Running Phase 4: Scaling..."
    cmd_run phase4
}

# Test individual skills
cmd_test() {
    check_venv
    if [[ $# -lt 1 ]]; then
        error "Usage: ./manage.sh test <skill_name>"
    fi
    SKILL="$1"
    shift
    cmd_run test "$SKILL" "$@"
}

# Backup state and assets
cmd_backup() {
    DATE=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="$PROJECT_DIR/backups/space-backup-$DATE.tar.gz"
    mkdir -p "$PROJECT_DIR/backups"
    
    log "Creating backup: $BACKUP_FILE"
    tar -czf "$BACKUP_FILE" -C "$PROJECT_DIR" \
        config/orchestrator.yaml \
        state/ \
        assets/ \
        output/ \
        2>/dev/null || true
    
    log "Backup complete: $BACKUP_FILE"
    
    # Keep only last 10 backups
    ls -t "$PROJECT_DIR/backups"/space-backup-*.tar.gz 2>/dev/null | tail -n +11 | xargs -r rm
}

# Restore from backup
cmd_restore() {
    if [[ $# -lt 1 ]]; then
        error "Usage: ./manage.sh restore <backup_file>"
    fi
    BACKUP="$1"
    
    if [[ ! -f "$BACKUP" ]]; then
        error "Backup file not found: $BACKUP"
    fi
    
    warn "This will overwrite current config, state, assets, and output!"
    read -p "Continue? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log "Restore cancelled"
        return
    fi
    
    log "Restoring from $BACKUP..."
    tar -xzf "$BACKUP" -C "$PROJECT_DIR"
    log "Restore complete"
}

# View logs
cmd_logs() {
    local lines="${1:-100}"
    if [[ -f "$PROJECT_DIR/logs/pipeline.log" ]]; then
        tail -n "$lines" -f "$PROJECT_DIR/logs/pipeline.log"
    else
        warn "No log file found at $PROJECT_DIR/logs/pipeline.log"
    fi
}

# Clean temporary files
cmd_clean() {
    log "Cleaning temporary files..."
    rm -rf "$PROJECT_DIR/cache"/*
    rm -rf "$PROJECT_DIR/tmp"/* 2>/dev/null || true
    rm -rf "$PROJECT_DIR/scripts/davinci_scripts"/* 2>/dev/null || true
    rm -rf "$PROJECT_DIR/output/davinci_scripts"/* 2>/dev/null || true
    log "Clean complete"
}

# Update dependencies
cmd_update() {
    log "Updating dependencies..."
    "$PYTHON" -m pip install --upgrade pip
    "$PYTHON" -m pip install -r "$PROJECT_DIR/requirements.txt" --upgrade
    log "Update complete"
}

# Show help
cmd_help() {
    cat << EOF
Space Exploration Channel - Management Script

Usage: ./manage.sh <command> [args]

Setup Commands:
  setup              - Initial setup (venv, deps, dirs, config)
  update             - Update Python dependencies

Production Commands:
  daily              - Run daily production batch (3 videos)
  continuous         - Run continuous automation loop
  phase1             - Run Phase 1: Channel Setup
  phase2             - Run Phase 2: Content Pipeline  
  phase3             - Run Phase 3: Optimization
  phase4             - Run Phase 4: Scaling
  analytics          - Run analytics optimization

Queue Management:
  status             - Show orchestrator status
  queue              - Show topic queue
  add-topic <title> <pillar> [priority] - Add topic to queue

Testing:
  test <skill> [args] - Test individual skill
  
Maintenance:
  logs [lines]       - View pipeline logs (default 100 lines)
  clean              - Clean temporary files
  backup             - Backup config, state, assets, output
  restore <file>     - Restore from backup

Examples:
  ./manage.sh setup
  ./manage.sh add-topic "Artemis III Landing Sites" planetary_science 8
  ./manage.sh daily
  ./manage.sh continuous
  ./manage.sh test nasa_research --topic "Mars Sample Return"
  ./manage.sh backup

Configuration:
  Edit $CONFIG_FILE with your API keys:
  - NASA API key (DEMO_KEY works for testing)
  - OpenAI API key (required for scripts/research)
  - ElevenLabs API key (required for voice)
  - YouTube OAuth credentials (config/youtube_client_secrets.json)
EOF
}

# Main command dispatch
case "${1:-help}" in
    setup) cmd_setup ;;
    update) cmd_update ;;
    daily) cmd_daily ;;
    continuous) cmd_continuous ;;
    phase1) cmd_phase1 ;;
    phase2) cmd_phase2 ;;
    phase3) cmd_phase3 ;;
    phase4) cmd_phase4 ;;
    analytics) cmd_analytics ;;
    status) cmd_status ;;
    queue) cmd_queue ;;
    add-topic) shift; cmd_add_topic "$@" ;;
    test) shift; cmd_test "$@" ;;
    logs) shift; cmd_logs "$@" ;;
    clean) cmd_clean ;;
    backup) cmd_backup ;;
    restore) shift; cmd_restore "$@" ;;
    run) shift; cmd_run "$@" ;;
    help|*) cmd_help ;;
esac