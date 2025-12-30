#!/bin/bash
# Force delete stack (bypass CDK synthesis)
# Save as: force-delete-stack.sh

echo "🗑️  Force deleting GenAIChatBotStack (bypassing CDK)..."

# Delete directly via CloudFormation
aws cloudformation delete-stack --stack-name GenAIChatBotStack

if [ $? -eq 0 ]; then
    echo "✅ Deletion initiated"
    echo ""
    echo "⏳ Monitoring deletion progress..."
    echo "This will take 10-15 minutes"
    echo ""
    
    # Monitor deletion
    while true; do
        STATUS=$(aws cloudformation describe-stacks \
            --stack-name GenAIChatBotStack \
            --query 'Stacks[0].StackStatus' \
            --output text 2>&1)
        
        if echo "$STATUS" | grep -q "does not exist"; then
            echo "✅ Stack deleted successfully!"
            break
        elif echo "$STATUS" | grep -q "DELETE_IN_PROGRESS"; then
            echo "⏳ Deleting... ($(date +%H:%M:%S))"
            sleep 15
        elif echo "$STATUS" | grep -q "DELETE_COMPLETE"; then
            echo "✅ Stack deleted successfully!"
            break
        elif echo "$STATUS" | grep -q "DELETE_FAILED"; then
            echo "❌ Deletion failed. Check AWS Console:"
            echo "https://console.aws.amazon.com/cloudformation/home?region=us-east-1"
            break
        else
            echo "Status: $STATUS"
            sleep 15
        fi
    done
else
    echo "❌ Failed to initiate deletion"
fi
