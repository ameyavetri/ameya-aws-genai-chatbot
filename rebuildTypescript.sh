#!/bin/bash
echo ""
echo "🔨 Building TypeScript..."

npm run build

if [ $? -ne 0 ]; then
    echo "❌ Build failed!"
    exit 1
fi

echo "✅ TypeScript build complete"
