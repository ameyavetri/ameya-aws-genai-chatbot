#!/bin/bash
echo ""
echo "🔍 Checking for orphaned resources..."

# Check for S3 buckets
echo ""
echo "S3 Buckets:"
aws s3 ls | grep -i genai || echo "None found"

# Check for CloudFront distributions
echo ""
echo "CloudFront Distributions:"
aws cloudfront list-distributions \
    --query "DistributionList.Items[?Comment=='GenAIChatBotStack'].[Id,DomainName]" \
    --output table 2>/dev/null || echo "None found"

# Check for Lambda functions
echo ""
echo "Lambda Functions:"
aws lambda list-functions \
    --query "Functions[?starts_with(FunctionName, 'GenAI')].[FunctionName]" \
    --output table 2>/dev/null || echo "None found"

# Check for DynamoDB tables
echo ""
echo "DynamoDB Tables:"
aws dynamodb list-tables --output table | grep -i genai || echo "None found"

# Check for Cognito User Pools
echo ""
echo "Cognito User Pools:"
aws cognito-idp list-user-pools --max-results 10 \
    --query "UserPools[?contains(Name, 'GenAI')].[Id,Name]" \
    --output table 2>/dev/null || echo "None found"

# If you find orphaned S3 buckets:
# aws s3 rb s3://bucket-name --force

# If you find orphaned Lambda functions:
# aws lambda delete-function --function-name function-name

# If you find orphaned DynamoDB tables:
# aws dynamodb delete-table --table-name table-name