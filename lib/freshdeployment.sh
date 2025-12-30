#!/bin/bash
echo ""
echo "🥾 Checking CDK bootstrap..."

# Check if CDKToolkit exists
BOOTSTRAP_STATUS=$(aws cloudformation describe-stacks \
    --stack-name CDKToolkit \
    --query 'Stacks[0].StackStatus' \
    --output text 2>/dev/null)

if [ "$BOOTSTRAP_STATUS" = "CREATE_COMPLETE" ] || [ "$BOOTSTRAP_STATUS" = "UPDATE_COMPLETE" ]; then
    echo "✅ CDK Bootstrap exists: $BOOTSTRAP_STATUS"
else
    echo "⚠️  Bootstrap required. Running bootstrap..."
    ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    cdk bootstrap aws://$ACCOUNT_ID/us-east-1
fi
echo ""
echo "🔨 Synthesizing CDK stacks..."

cdk synth --quiet

if [ $? -ne 0 ]; then
    echo "❌ Synthesis failed!"
    exit 1
fi

echo "✅ Synthesis complete"
echo ""
echo "📊 Preview of resources to be created:"

cdk diff GenAIChatBotStack