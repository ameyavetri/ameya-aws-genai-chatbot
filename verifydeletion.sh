#!/bin/bash
# Verify stack is gone
aws cloudformation describe-stacks --stack-name GenAIChatBotStack 2>&1

# Should return: "Stack with id GenAIChatBotStack does not exist"