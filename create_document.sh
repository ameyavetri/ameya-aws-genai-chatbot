# Generate handoff document
cat > CUSTOMER_HANDOFF.md << EOF
# GenAI Chatbot - Deployment Complete

**Deployment Date:** $(date)
**AWS Account:** $(aws sts get-caller-identity --query Account --output text)
**Deployed By:** [Your Name]

## Access Information

**Chatbot URL:** $(aws cloudformation describe-stacks --stack-name GenAIChatBotStack --query 'Stacks[0].Outputs[?OutputKey==`UserInterfaceURL`].OutputValue' --output text)

**Admin User:**
- Email: admin@customer-domain.com
- Temporary Password: ChangeMe123!
- Must change password on first login

## AWS Resources Created

- CloudFormation Stack: GenAIChatBotStack
- Cognito User Pool: $(aws cloudformation describe-stacks --stack-name GenAIChatBotStack --query 'Stacks[0].Outputs[?OutputKey==`CognitoUserPoolId`].OutputValue' --output text)
- Region: us-east-1
- ~200-300 AWS resources (Lambda, S3, DynamoDB, etc.)

## Estimated Monthly Costs

**Base Infrastructure:** \$50-150/month
- VPC/NAT Gateway: ~\$30-50
- CloudFront: ~\$10-20
- Lambda/API Gateway: ~\$10-20
- S3/DynamoDB/Cognito: ~\$10-20

**Usage-Based Costs:**
- Bedrock (Claude API): \$0.003-0.015 per 1K tokens
- Estimate: \$50-300/month depending on usage

**Total Estimate:** \$100-500/month

## How to Add Users

1. Go to AWS Console → Cognito
2. Select User Pool (ID above)
3. Click "Users" → "Create user"
4. Assign to groups: Admin, WorkspaceManager, or User

## Support Contacts

- Technical Support: [your-email@company.com]
- AWS Account Admin: [customer-contact]

## Next Steps

1. ✅ Test chatbot functionality
2. ✅ Add additional users as needed
3. ✅ Set up billing alerts (recommended: \$200/month)
4. ✅ Schedule training session
5. ✅ Review security best practices

EOF
