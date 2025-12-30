#!/bin/bash
echo ""
echo "🔨 Synthesizing CDK stacks..."

cdk synth --quiet

if [ $? -ne 0 ]; then
    echo "❌ Synthesis failed!"
    exit 1
fi

echo "✅ Synthesis complete"
