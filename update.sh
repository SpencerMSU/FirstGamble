#!/bin/bash
# Script to update the FirstGamble API service

# Ensure we are in the project root
cd "$(dirname "$0")"

echo "Starting update..."

# 1. Pull latest changes
echo "Pulling latest changes from git..."
git pull

# 2. Activate virtual environment and install dependencies
echo "Installing dependencies..."
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
else
    echo "Virtual environment not found! Attempting to create one..."
    python3 -m venv venv
    source venv/bin/activate
fi

pip install -r requirements.txt

# 3. Restart the service
echo "Restarting service..."
sudo systemctl restart firstgamble-api.service

echo "Update complete! Checking service status..."
sudo systemctl status firstgamble-api.service --no-pager
