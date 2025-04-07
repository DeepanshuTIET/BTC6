#!/bin/bash

# Print Python version
python --version

# Install dependencies
pip install -r requirements.txt

# Create necessary directories if they don't exist
mkdir -p static
mkdir -p templates

# Copy template files if they exist in source but not in destination
if [ -d "templates" ]; then
  cp -r templates/* templates/ 2>/dev/null || :
fi

# Copy static files if they exist in source but not in destination
if [ -d "static" ]; then
  cp -r static/* static/ 2>/dev/null || :
fi

echo "Build completed successfully"
