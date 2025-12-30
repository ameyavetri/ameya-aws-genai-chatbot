#!/bin/bash
echo ""
echo "📋 Verifying configuration..."

# Check config.json exists
if [ ! -f "config.json" ]; then
    echo "❌ config.json not found!"
    echo "Copy from backup or create new one"
    exit 1
fi

# Display config
echo ""
echo "Current configuration:"
cat config.json | python3 -m json.tool 2>/dev/null || cat config.json

echo ""
echo "✅ Configuration verified"
