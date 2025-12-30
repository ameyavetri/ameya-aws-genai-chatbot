#!/bin/bash
# Create a helper script for creating users
cat > create-user.sh << 'EOF'
#!/bin/bash

echo "👤 Create New Chatbot User"
echo "=========================="

# Get User Pool ID
USER_POOL_ID=$(aws cloudformation describe-stacks \
    --stack-name GenAIChatBotStack \
    --query 'Stacks[0].Outputs[?contains(OutputKey, `UserPoolId`)].OutputValue' \
    --output text)

if [ -z "$USER_POOL_ID" ]; then
    echo "❌ Could not find User Pool ID"
    exit 1
fi

echo "User Pool ID: $USER_POOL_ID"
echo ""

# Prompt for user details
read -p "Enter email address: " USER_EMAIL
read -sp "Enter temporary password: " TEMP_PASSWORD
echo ""

# Create user
echo ""
echo "⏳ Creating user..."

aws cognito-idp admin-create-user \
    --user-pool-id "$USER_POOL_ID" \
    --username "$USER_EMAIL" \
    --user-attributes \
        Name=email,Value="$USER_EMAIL" \
        Name=email_verified,Value=true \
    --temporary-password "$TEMP_PASSWORD" \
    --message-action SUPPRESS

if [ $? -eq 0 ]; then
    echo "✅ User created successfully!"
    
    # Check for groups and add user
    echo ""
    echo "📋 Available groups:"
    GROUPS=$(aws cognito-idp list-groups --user-pool-id "$USER_POOL_ID" --query 'Groups[].GroupName' --output text)
    
    if [ -z "$GROUPS" ]; then
        echo "⚠️  No groups found. Creating 'Users' group..."
        aws cognito-idp create-group \
            --user-pool-id "$USER_POOL_ID" \
            --group-name "Users" \
            --description "Default users group"
        GROUPS="Users"
    fi
    
    echo "$GROUPS"
    
    # Add user to first group
    FIRST_GROUP=$(echo "$GROUPS" | awk '{print $1}')
    echo ""
    echo "⏳ Adding user to group: $FIRST_GROUP"
    
    aws cognito-idp admin-add-user-to-group \
        --user-pool-id "$USER_POOL_ID" \
        --username "$USER_EMAIL" \
        --group-name "$FIRST_GROUP"
    
    if [ $? -eq 0 ]; then
        echo "✅ User added to group successfully!"
        echo ""
        echo "📧 Login credentials:"
        echo "   Email: $USER_EMAIL"
        echo "   Temporary Password: $TEMP_PASSWORD"
        echo "   (You'll be asked to change this on first login)"
    else
        echo "❌ Failed to add user to group"
        echo "Add manually via AWS Console"
    fi
else
    echo "❌ Failed to create user"
fi
EOF

chmod +x create-user.sh
echo "✅ Created create-user.sh script"