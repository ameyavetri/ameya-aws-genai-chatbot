#!/bin/bash
# Properly fix lib/models/index.ts

echo "🔧 Fixing lib/models/index.ts..."

# Backup
cp lib/models/index.ts lib/models/index.ts.backup

# Create a temporary file with the fixed content
cat > lib/models/index.ts.tmp << 'ENDOFFILE'
import * as cdk from "aws-cdk-lib";
import * as path from "path";
import * as ssm from "aws-cdk-lib/aws-ssm";
import { Construct } from "constructs";
import * as iam from "aws-cdk-lib/aws-iam";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import { Shared } from "../shared";
import {
  Modality,
  ModelInterface,
  SageMakerModelEndpoint,
  SupportedSageMakerModels,
  SystemConfig,
} from "../shared/types";
// Commented out deprecated SageMaker imports
// import {
//   HuggingFaceSageMakerEndpoint,
//   JumpStartSageMakerEndpoint,
//   SageMakerInstanceType,
//   DeepLearningContainerImage,
//   JumpStartModel,
// } from "@cdklabs/generative-ai-cdk-constructs";
import { NagSuppressions } from "cdk-nag";
import { createStartSchedule, createStopSchedule } from "./sagemaker-schedule";

export interface ModelsProps {
  readonly config: SystemConfig;
  readonly shared: Shared;
}

export class Models extends Construct {
  public readonly models: ModelInterface[];

  constructor(scope: Construct, id: string, props: ModelsProps) {
    super(scope, id);

    const models: ModelInterface[] = [];
    const config = props.config;

    // SageMaker models section commented out - only using Bedrock
    // if (config.llms?.sagemaker && config.llms.sagemaker.length > 0) {
    //   ... all SageMaker model code removed ...
    // }

    const modelsParameter = new ssm.StringParameter(this, "ModelsParameter", {
      stringValue: JSON.stringify(models),
    });

    this.models = models;
  }
}
ENDOFFILE

# Replace the file
mv lib/models/index.ts.tmp lib/models/index.ts

echo "✅ Fixed lib/models/index.ts"
echo ""
echo "🔨 Rebuilding..."
npm run build