#!/bin/bash
# Complete Rebuild & Redeploy Script
# Save as: rebuild-and-redeploy.sh

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${GREEN}🔄 AWS GenAI Chatbot - Complete Rebuild & Redeploy${NC}"
echo "=================================================="

# Parse arguments
SKIP_BACKUP=false
SKIP_DESTROY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-backup)
            SKIP_BACKUP=true
            shift
            ;;
        --skip-destroy)
            SKIP_DESTROY=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Phase 1: Backup
if [ "$SKIP_BACKUP" = false ]; then
    echo -e "\n${YELLOW}📦 Phase 1: Creating backup...${NC}"
    
    BACKUP_DIR="backup-$(date +%Y-%m-%d-%H%M%S)"
    mkdir -p "$BACKUP_DIR"
    
    # Backup config
    if [ -f "config.json" ]; then
        cp config.json "$BACKUP_DIR/"
        echo -e "${GREEN}✅ Backed up config.json${NC}"
    fi
    
    # Backup React customizations
    if [ -d "lib/user-interface/react-app/src" ]; then
        cp -r lib/user-interface/react-app/src "$BACKUP_DIR/react-src-backup"
        echo -e "${GREEN}✅ Backed up React source${NC}"
    fi
    
    # Export users
    USER_POOL_ID=$(aws cloudformation describe-stacks \
        --stack-name GenAIChatBotStack \
        --query 'Stacks[0].Outputs[?contains(OutputKey, `UserPoolId`)].OutputValue' \
        --output text 2>/dev/null || echo "")
    
    if [ ! -z "$USER_POOL_ID" ]; then
        aws cognito-idp list-users --user-pool-id "$USER_POOL_ID" --output json > "$BACKUP_DIR/cognito-users.json"
        echo -e "${GREEN}✅ Backed up Cognito users${NC}"
    fi
    
    echo -e "${GREEN}✅ Backup complete: $BACKUP_DIR${NC}"
fi

# Phase 2: Destroy existing stack
if [ "$SKIP_DESTROY" = false ]; then
    echo -e "\n${YELLOW}🗑️  Phase 2: Destroying existing stack...${NC}"
    
    # Check if stack exists
    if aws cloudformation describe-stacks --stack-name GenAIChatBotStack &>/dev/null; then
        echo -e "${CYAN}Destroying GenAIChatBotStack...${NC}"
        cdk destroy GenAIChatBotStack --force
        
        # Wait for deletion
        echo -e "${CYAN}Waiting for deletion to complete...${NC}"
        while aws cloudformation describe-stacks --stack-name GenAIChatBotStack &>/dev/null; do
            echo -e "${YELLOW}⏳ Still deleting...${NC}"
            sleep 10
        done
        
        echo -e "${GREEN}✅ Stack destroyed${NC}"
    else
        echo -e "${YELLOW}⚠️  Stack does not exist, skipping destruction${NC}"
    fi
fi

# Phase 3: Clean local artifacts
echo -e "\n${YELLOW}🧹 Phase 3: Cleaning local artifacts...${NC}"

rm -rf cdk.out node_modules lib/user-interface/react-app/build lib/user-interface/react-app/node_modules 2>/dev/null
rm -f package-lock.json 2>/dev/null

echo -e "${GREEN}✅ Cleanup complete${NC}"

# Phase 4: Fresh installation
echo -e "\n${YELLOW}📦 Phase 4: Installing dependencies...${NC}"

npm install
if [ $? -ne 0 ]; then exit 1; fi

cd lib/user-interface/react-app
npm install
if [ $? -ne 0 ]; then exit 1; fi
cd ../../..

echo -e "${GREEN}✅ Dependencies installed${NC}"

# Phase 5: Build
echo -e "\n${YELLOW}🔨 Phase 5: Building project...${NC}"

npm run build
if [ $? -ne 0 ]; then
    echo -e "${RED}❌ Build failed!${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Build complete${NC}"

# Phase 6: Deploy
echo -e "\n${YELLOW}🚀 Phase 6: Deploying to AWS...${NC}"
echo -e "${CYAN}This will take 25-35 minutes...${NC}"
echo -e "${CYAN}Start time: $(date '+%H:%M:%S')${NC}"

cdk deploy --all --require-approval never --progress events --outputs-file deployment-outputs.json

if [ $? -eq 0 ]; then
    echo -e "\n${GREEN}✅ Deployment successful!${NC}"
    echo -e "${CYAN}End time: $(date '+%H:%M:%S')${NC}"
    
    # Get outputs
    WEBSITE_URL=$(aws cloudformation describe-stacks \
        --stack-name GenAIChatBotStack \
        --query 'Stacks[0].Outputs[?contains(OutputKey, `Website`)].OutputValue' \
        --output text)
    
    echo -e "\n${CYAN}🌐 Website URL: $WEBSITE_URL${NC}"
    echo -e "\n${YELLOW}📋 Next steps:${NC}"
    echo "1. Create users (run: ./create-user.sh)"
    echo "2. Open website: $WEBSITE_URL"
    echo "3. Login and test"
    
else
    echo -e "\n${RED}❌ Deployment failed!${NC}"
    exit 1
fi
# How to run the script
# Make it executable
#chmod +x rebuild-and-redeploy.sh

# Full rebuild with backup
# ./rebuild-and-redeploy.sh

# Skip backup if you already have one
# ./rebuild-and-redeploy.sh --skip-backup

# Skip destroy if stack doesn't exist
# ./rebuild-and-redeploy.sh --skip-destroy