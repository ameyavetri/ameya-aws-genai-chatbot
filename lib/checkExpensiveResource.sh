
#!/bin/bash

echo "💰 Checking for expensive resources..."

# Check for NAT Gateways (~$32/month each)
echo ""
echo "NAT Gateways:"
aws ec2 describe-nat-gateways --filter "Name=state,Values=available" --output table

# Check for running EC2 instances
echo ""
echo "Running EC2 Instances:"
aws ec2 describe-instances --filters "Name=instance-state-name,Values=running" --output table

# Check for Elastic IPs (charged if not attached)
echo ""
echo "Elastic IPs:"
aws ec2 describe-addresses --output table

# Check for Load Balancers (~$16/month each)
echo ""
echo "Load Balancers:"
aws elbv2 describe-load-balancers --output table