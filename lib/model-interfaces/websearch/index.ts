import * as cdk from "aws-cdk-lib";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as iam from "aws-cdk-lib/aws-iam";
import * as sqs from "aws-cdk-lib/aws-sqs";
import * as lambdaEventSources from "aws-cdk-lib/aws-lambda-event-sources";
import * as path from "path";
import { Construct } from "constructs";
import { Shared } from "../../shared";

export interface WebSearchProps {
  shared: Shared;
}

export class WebSearchInterface extends Construct {
  public readonly ingestionQueue: sqs.Queue;
  public readonly webSearchLambda: lambda.Function;

  constructor(scope: Construct, id: string, props: WebSearchProps) {
    super(scope, id);

    this.webSearchLambda = new lambda.Function(this, "WebSearchHandler", {
      runtime: props.shared.pythonRuntime,
      handler: "index.handler",
      code: props.shared.sharedCode.bundleWithLambdaAsset(
        path.join(__dirname, "functions", "websearch-handler")
      ),
      timeout: cdk.Duration.seconds(30),
      memorySize: 512,
      environment: {
        BING_API_KEY_SECRET: "WEB_SEARCH_BING_API_KEY",
      },
    });
    this.ingestionQueue = new sqs.Queue(this, "WebSearchQueue", {
        visibilityTimeout: cdk.Duration.seconds(300),
      });
      this.ingestionQueue.grantConsumeMessages(this.webSearchLambda);
      this.webSearchLambda.addEventSource(new lambdaEventSources.SqsEventSource(this.ingestionQueue));

    // Allow HTTPS access
    this.webSearchLambda.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ["secretsmanager:GetSecretValue"],
        resources: ["*"],
      })
    );
  }
}
