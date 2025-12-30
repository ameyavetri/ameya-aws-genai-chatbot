#!/bin/bash
echo ""
echo "🚀 Starting fresh deployment..."
echo "This will take 25-35 minutes..."
echo "Start time: $(date '+%Y-%m-%d %H:%M:%S')"

# Deploy with outputs saved to file
cdk deploy --all \
    --require-approval never \
    --progress events \
    --outputs-file deployment-outputs.json

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Deployment successful!"
    echo "End time: $(date '+%Y-%m-%d %H:%M:%S')"
else
    echo ""
    echo "❌ Deployment failed!"
    echo "Check the error messages above"
    exit 1
fi