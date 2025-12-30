#!/bin/bash
# Get website URL
aws cloudformation describe-stacks \
    --stack-name GenAIChatBotStack \
    --query 'Stacks[0].Outputs[?contains(OutputKey, `Website`)].OutputValue' \
    --output text

# Get User Pool ID
aws cloudformation describe-stacks \
    --stack-name GenAIChatBotStack \
    --query 'Stacks[0].Outputs[?contains(OutputKey, `UserPoolId`)].OutputValue' \
    --output text

# List all users
USER_POOL_ID=$(aws cloudformation describe-stacks --stack-name GenAIChatBotStack --query 'Stacks[0].Outputs[?contains(OutputKey, `UserPoolId`)].OutputValue' --output text)
aws cognito-idp list-users --user-pool-id "$USER_POOL_ID"

# Delete a user
aws cognito-idp admin-delete-user --user-pool-id "$USER_POOL_ID" --username user@example.com

# Reset user password
aws cognito-idp admin-set-user-password \
    --user-pool-id "$USER_POOL_ID" \
    --username user@example.com \
    --password NewPassword123! \
    --permanent