#!/bin/bash

# Ensure Homebrew exists
if ! command -v brew &> /dev/null; then
    echo "Homebrew not found — installing Homebrew."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
else
    echo "Homebrew installed — skipping."
fi

echo "Updating Homebrew..."
brew update

# Install Python if needed
if ! command -v python3 &> /dev/null; then
    echo "Python3 not found — installing..."
    brew install python
else
    echo "Python3 already installed — skipping."
fi

# Install pip packages (fixed for your script)
echo "Installing required Python packages..."
pip3 install --user \
    pillow \
    pypdf

echo "All required packages have been installed successfully!"