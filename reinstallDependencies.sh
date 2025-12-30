#!/bin/bash
# Reinstall Dependencies Script
# Must be run from project root: /c/vetri/cookbook/ameyaChatbot/aws-genai-llm-chatbot

echo ""
echo "📦 Installing dependencies..."

# Ensure we're in project root
if [ ! -f "package.json" ]; then
    echo "❌ Error: package.json not found!"
    echo "Please run this script from project root:"
    echo "  cd /c/vetri/cookbook/ameyaChatbot/aws-genai-llm-chatbot"
    echo "  ./reinstallDependencies.sh"
    exit 1
fi

# Install root dependencies
npm install

if [ $? -ne 0 ]; then
    echo "❌ Root dependencies installation failed!"
    exit 1
fi

echo "✅ Root dependencies installed"

# Install React app dependencies
cd lib/user-interface/react-app

if [ ! -f "package.json" ]; then
    echo "❌ Error: React app package.json not found!"
    exit 1
fi

npm install

if [ $? -ne 0 ]; then
    echo "❌ React dependencies installation failed!"
    exit 1
fi

# Return to project root (3 levels up)
cd ../../../

echo "✅ React app dependencies installed"
echo ""
echo "🔨 Building TypeScript..."

npm run build

if [ $? -ne 0 ]; then
    echo "❌ Build failed!"
    exit 1
fi

echo "✅ TypeScript build complete"
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
if command -v jq &> /dev/null; then
    cat config.json | jq .
elif command -v python3 &> /dev/null; then
    cat config.json | python3 -m json.tool 2>/dev/null || cat config.json
else
    cat config.json
fi

echo ""
echo "✅ Configuration verified"
echo "✅ All done! Ready to deploy."