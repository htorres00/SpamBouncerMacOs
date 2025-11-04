#!/bin/bash
# Setup script for Spam Bouncer

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "======================================"
echo "  Spam Bouncer Setup"
echo "======================================"
echo ""

# Check if config.json exists
if [ ! -f "config.json" ]; then
    echo "⚠️  config.json not found. Creating from template..."
    cp config.json.template config.json
    echo "✅ Created config.json"
    echo ""
    echo "📝 Please edit config.json with your credentials:"
    echo "   1. Your iCloud email"
    echo "   2. Your app-specific password from appleid.apple.com"
    echo ""
    echo "   Then run this script again."
    exit 0
fi

# Verify config has been edited
if grep -q "your-email@icloud.com" config.json; then
    echo "⚠️  Please edit config.json with your actual credentials first."
    echo "   Open config.json and replace the placeholder values."
    exit 1
fi

echo "✅ Configuration file found"

# Create logs directory
mkdir -p logs
echo "✅ Created logs directory"

# Make script executable
chmod +x spam_bouncer.py
echo "✅ Made spam_bouncer.py executable"

# Test Python availability
if ! command -v python3 &> /dev/null; then
    echo "❌ python3 not found. Please install Python 3."
    exit 1
fi
echo "✅ Python 3 is installed"

# Offer to run a test
echo ""
read -p "Would you like to run a test now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "Running test (checking for spam once)..."
    python3 spam_bouncer.py --once
fi

echo ""
echo "======================================"
echo "  Setup Complete!"
echo "======================================"
echo ""
echo "Next steps:"
echo ""
echo "1. Test manually:"
echo "   python3 spam_bouncer.py --once"
echo ""
echo "2. Install as auto-start service:"
echo "   cp com.spambouncer.plist ~/Library/LaunchAgents/"
echo "   launchctl load ~/Library/LaunchAgents/com.spambouncer.plist"
echo "   launchctl start com.spambouncer"
echo ""
echo "3. View logs:"
echo "   tail -f logs/spam_bouncer_*.log"
echo ""
echo "For more information, see README.md"
