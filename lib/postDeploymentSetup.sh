#!/bin/bash
echo ""
echo "📋 Saving stack outputs..."

# Get stack outputs
WEBSITE_URL=$(aws cloudformation describe-stacks \
    --stack-name GenAIChatBotStack \
    --query 'Stacks[0].Outputs[?contains(OutputKey, `Website`)].OutputValue' \
    --output text)

USER_POOL_ID=$(aws cloudformation describe-stacks \
    --stack-name GenAIChatBotStack \
    --query 'Stacks[0].Outputs[?contains(OutputKey, `UserPoolId`)].OutputValue' \
    --output text)

API_URL=$(aws cloudformation describe-stacks \
    --stack-name GenAIChatBotStack \
    --query 'Stacks[0].Outputs[?contains(OutputKey, `GraphQL`)].OutputValue' \
    --output text)

echo ""
echo "✅ Deployment Complete!"
echo ""
echo "🌐 Important URLs:"
echo "Website URL: $WEBSITE_URL"
echo "GraphQL API: $API_URL"
echo "User Pool ID: $USER_POOL_ID"

# Save to file
cat > deployment-info.txt << EOF
Deployment Information
=====================
Date: $(date '+%Y-%m-%d %H:%M:%S')
Website URL: $WEBSITE_URL
GraphQL API: $API_URL
User Pool ID: $USER_POOL_ID
EOF

echo ""
echo "✅ Deployment info saved to deployment-info.txt"