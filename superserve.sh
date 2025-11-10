#!/bin/bash

# Superserve script - automatically updates and restarts server when main branch changes
# This script monitors the main branch and restarts the server when updates are detected

# Don't use set -e - we want to handle errors gracefully

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored messages
info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if we're on main branch
check_branch() {
    current_branch=$(git rev-parse --abbrev-ref HEAD)
    if [ "$current_branch" != "main" ]; then
        error "Not on main branch. Current branch: $current_branch"
        error "Please switch to main branch before running superserve."
        exit 1
    fi
    info "On main branch ✓"
}

# Function to pull latest changes
# Returns 0 if updates were pulled, 1 if no updates or error
pull_latest() {
    # Store current HEAD before pulling
    local_before=$(git rev-parse HEAD 2>/dev/null)
    
    info "Pulling latest changes from origin/main..."
    if ! git pull origin main; then
        error "Failed to pull latest changes. Continuing with current code..."
        return 1
    fi
    
    # Check if HEAD changed (meaning updates were pulled)
    local_after=$(git rev-parse HEAD 2>/dev/null)
    if [ "$local_before" != "$local_after" ]; then
        info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        info "✓ GIT PULL UPDATE: Changes pulled successfully (${local_before:0:7} → ${local_after:0:7})"
        info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        return 0
    else
        return 2  # No updates (different from error)
    fi
}

# Function to start the server
start_server() {
    info "Starting server (building if necessary)..."
    docker-compose up --build -d
    info "Server started in background"
}

# Function to stop the server
stop_server() {
    info "Stopping server..."
    docker-compose down
    info "Server stopped"
}

# Function to check for updates
check_for_updates() {
    # Fetch latest from origin without merging
    if ! git fetch origin main > /dev/null 2>&1; then
        # If fetch fails (network issue, etc.), assume no updates
        return 1
    fi
    
    # Check if local and remote are different
    local_commit=$(git rev-parse HEAD 2>/dev/null)
    remote_commit=$(git rev-parse origin/main 2>/dev/null)
    
    if [ -z "$local_commit" ] || [ -z "$remote_commit" ]; then
        # If we can't get commits, assume no updates
        return 1
    fi
    
    if [ "$local_commit" != "$remote_commit" ]; then
        return 0  # Updates available
    else
        return 1  # No updates
    fi
}

# Main execution
main() {
    info "Starting superserve mode..."
    
    # Step 1: Confirm we're on main branch
    check_branch
    
    # Initial pull to ensure we're up to date
    pull_latest
    pull_result=$?
    if [ "$pull_result" = "1" ]; then
        warn "Initial pull failed, but continuing with current code..."
    elif [ "$pull_result" = "0" ]; then
        info "Initial update pulled successfully"
    fi
    
    # Step 2: Start server initially
    start_server
    
    # Step 3: Monitor for updates
    info "Monitoring for updates (checking every 61 seconds)..."
    info "Press Ctrl+C to stop"
    
    while true; do
        sleep 61  # Wait 61 seconds (staggered from minute boundary)
        
        if check_for_updates; then
            warn "Updates detected on origin/main!"
            info "Stopping server to apply updates..."
            stop_server
            
            info "Pulling latest changes..."
            pull_latest
            pull_result=$?
            if [ "$pull_result" = "0" ]; then
                # Updates were pulled
                info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                info "🔄 SERVER RESTART: Restarting server after git pull update..."
                start_server
                info "✓ SERVER RESTART: Server restarted successfully after update"
                info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                info "Continuing to monitor for updates..."
            elif [ "$pull_result" = "2" ]; then
                # No updates (shouldn't happen if check_for_updates worked, but handle it)
                warn "No updates found after pull. Restarting server with current code..."
                start_server
            else
                # Pull failed
                warn "Pull failed. Restarting server with current code..."
                start_server
            fi
        else
            # Silent check - no updates
            :
        fi
    done
}

# Handle Ctrl+C gracefully
trap 'echo ""; warn "Stopping superserve..."; stop_server; info "Superserve stopped."; exit 0' INT TERM

# Run main function
main

