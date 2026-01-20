#!/bin/bash
echo "Testing AWS Permissions..."

# Test CloudFormation
aws cloudformation list-stacks --max-results 1 &>/dev/null && echo "✅ CloudFormation: OK" || echo "❌ CloudFormation: FAILED"

# Test IAM
aws iam list-roles --max-items 1 &>/dev/null && echo "✅ IAM List: OK" || echo "❌ IAM List: FAILED"
aws iam create-role --role-name test-cdk-permissions --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}' &>/dev/null && \
aws iam delete-role --role-name test-cdk-permissions &>/dev/null && echo "✅ IAM Create: OK" || echo "❌ IAM Create: FAILED"

# Test S3
aws s3 ls &>/dev/null && echo "✅ S3: OK" || echo "❌ S3: FAILED"

# Test Lambda
aws lambda list-functions --max-items 1 &>/dev/null && echo "✅ Lambda: OK" || echo "❌ Lambda: FAILED"

# Test Cognito
aws cognito-idp list-user-pools --max-results 1 &>/dev/null && echo "✅ Cognito: OK" || echo "❌ Cognito: FAILED"

# Test API Gateway
aws apigatewayv2 get-apis --max-results 1 &>/dev/null && echo "✅ API Gateway: OK" || echo "❌ API Gateway: FAILED"

echo ""
echo "If any show ❌, you may encounter deployment failures."
