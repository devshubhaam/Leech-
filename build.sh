#!/usr/bin/env bash
# build.sh — installs system-level dependencies on Render
# Render free tier runs on Ubuntu — apt-get works during build phase

set -e

echo "==> Installing system dependencies..."

# aria2c — multi-protocol downloader
apt-get install -y aria2

# ffmpeg — needed by yt-dlp to merge video+audio streams
apt-get install -y ffmpeg

echo "==> System deps installed."
echo "aria2c: $(aria2c --version | head -1)"
echo "ffmpeg: $(ffmpeg -version 2>&1 | head -1)"

echo "==> Installing Python deps..."
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Build complete."
