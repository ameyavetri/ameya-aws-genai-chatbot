#!/bin/bash
# List all resources in the stack
echo "📋 Resources to be deleted:"
aws cloudformation list-stack-resources \
    --stack-name GenAIChatBotStack \
    --output table

# Count resources
RESOURCE_COUNT=$(aws cloudformation list-stack-resources \
    --stack-name GenAIChatBotStack \
    --query 'length(StackResourceSummaries)' \
    --output text 2>/dev/null)

echo ""
echo "⚠️  This will delete $RESOURCE_COUNT resources"
echo "Including: S3 buckets, DynamoDB tables, Lambda functions, etc."
echo ""
echo "🗑️  Destroying GenAIChatBotStack..."
echo "This will take 10-15 minutes..."

# Destroy the stack
cdk destroy GenAIChatBotStack --force

# Wait for deletion to complete
echo ""
echo "Waiting for stack deletion to complete..."

while true; do
    STACK_STATUS=$(aws cloudformation describe-stacks \
        --stack-name GenAIChatBotStack \
        --query 'Stacks[0].StackStatus' \
        --output text 2>&1)
    
    if echo "$STACK_STATUS" | grep -q "does not exist"; then
        echo "✅ Stack deleted successfully"
        break
    elif echo "$STACK_STATUS" | grep -q "DELETE_IN_PROGRESS"; then
        echo "⏳ Still deleting... ($(date +%H:%M:%S))"
        sleep 10
    else
        echo "⚠️  Unexpected status: $STACK_STATUS"
        break
    fi
done