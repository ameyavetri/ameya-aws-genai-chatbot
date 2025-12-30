#!/bin/bash
echo ""
echo "🧹 Cleaning local build artifacts..."
# Remove CDK output
if [ -d "cdk.out" ]; then
    rm -rf cdk.out
    echo "✅ Removed cdk.out"
fi

# Remove node_modules (optional but recommended for clean rebuild)
if [ -d "node_modules" ]; then
    echo "⏳ Removing node_modules (this may take a minute)..."
    rm -rf node_modules
    echo "✅ Removed node_modules"
fi

# Remove React app build
if [ -d "lib/user-interface/react-app/build" ]; then
    rm -rf lib/user-interface/react-app/build
    echo "✅ Removed React build"
fi

# Remove React app node_modules
if [ -d "lib/user-interface/react-app/node_modules" ]; then
    echo "⏳ Removing React node_modules..."
    rm -rf lib/user-interface/react-app/node_modules
    echo "✅ Removed React node_modules"
fi

# Remove package-lock files
rm -f package-lock.json
rm -f lib/user-interface/react-app/package-lock.json

echo "✅ Local cleanup complete"