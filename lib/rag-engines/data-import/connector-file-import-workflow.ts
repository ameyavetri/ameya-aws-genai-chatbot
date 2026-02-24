import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import { SystemConfig } from "../../shared/types";
import { FileImportBatchJob } from "./file-import-batch-job";
import { RagDynamoDBTables } from "../rag-dynamodb-tables";
import * as sfn from "aws-cdk-lib/aws-stepfunctions";
import * as tasks from "aws-cdk-lib/aws-stepfunctions-tasks";
import * as logs from "aws-cdk-lib/aws-logs";
import * as iam from "aws-cdk-lib/aws-iam";

export interface ConnectorFileImportWorkflowProps {
  readonly config: SystemConfig;
  readonly fileImportBatchJob: FileImportBatchJob;
  readonly ragDynamoDBTables: RagDynamoDBTables;
}

/**
 * Step Function that imports a single file from a connector (Dropbox/SharePoint).
 * Sets document status to processing, runs the same Batch job with CONNECTOR_ID and FILE_PATH,
 * then sets status to processed. The batch job fetches content from the connector and
 * runs the same extract → chunk → embed → RAG pipeline.
 */
export class ConnectorFileImportWorkflow extends Construct {
  public readonly stateMachine: sfn.StateMachine;

  constructor(
    scope: Construct,
    id: string,
    props: ConnectorFileImportWorkflowProps
  ) {
    super(scope, id);

    const setProcessing = new tasks.DynamoUpdateItem(this, "SetProcessing", {
      table: props.ragDynamoDBTables.documentsTable,
      key: {
        workspace_id: tasks.DynamoAttributeValue.fromString(
          sfn.JsonPath.stringAt("$.workspace_id")
        ),
        document_id: tasks.DynamoAttributeValue.fromString(
          sfn.JsonPath.stringAt("$.document_id")
        ),
      },
      updateExpression: "set #status=:statusValue",
      expressionAttributeNames: {
        "#status": "status",
      },
      expressionAttributeValues: {
        ":statusValue": tasks.DynamoAttributeValue.fromString("processing"),
      },
      resultPath: sfn.JsonPath.DISCARD,
    });

    const setProcessed = new tasks.DynamoUpdateItem(this, "SetProcessed", {
      table: props.ragDynamoDBTables.documentsTable,
      key: {
        workspace_id: tasks.DynamoAttributeValue.fromString(
          sfn.JsonPath.stringAt("$.workspace_id")
        ),
        document_id: tasks.DynamoAttributeValue.fromString(
          sfn.JsonPath.stringAt("$.document_id")
        ),
      },
      updateExpression: "set #status=:statusValue",
      expressionAttributeNames: {
        "#status": "status",
      },
      expressionAttributeValues: {
        ":statusValue": tasks.DynamoAttributeValue.fromString("processed"),
      },
      resultPath: sfn.JsonPath.DISCARD,
    }).next(new sfn.Succeed(this, "Success"));

    const connectorImportJob = new sfn.CustomState(this, "ConnectorImportJob", {
      stateJson: {
        Type: "Task",
        Resource: `arn:${cdk.Aws.PARTITION}:states:::batch:submitJob.sync`,
        Parameters: {
          JobDefinition:
            props.fileImportBatchJob.fileImportJob.jobDefinitionArn,
          "JobName.$":
            "States.Format('ConnectorImport-{}-{}', $.workspace_id, $.document_id)",
          JobQueue: props.fileImportBatchJob.jobQueue.jobQueueArn,
          ContainerOverrides: {
            Environment: [
              {
                Name: "WORKSPACE_ID",
                "Value.$": "$.workspace_id",
              },
              {
                Name: "DOCUMENT_ID",
                "Value.$": "$.document_id",
              },
              {
                Name: "CONNECTOR_ID",
                "Value.$": "$.connector_id",
              },
              {
                Name: "FILE_PATH",
                "Value.$": "$.file_path",
              },
              {
                Name: "PROCESSING_BUCKET_NAME",
                "Value.$": "$.processing_bucket_name",
              },
              {
                Name: "PROCESSING_OBJECT_KEY",
                "Value.$": "$.processing_object_key",
              },
            ],
          },
        },
        ResultPath: "$.job",
      },
    });

    const logGroup = new logs.LogGroup(this, "ConnectorImportSMLogGroup", {
      removalPolicy:
        props.config.retainOnDelete === true
          ? cdk.RemovalPolicy.RETAIN_ON_UPDATE_OR_DELETE
          : cdk.RemovalPolicy.DESTROY,
      retention: props.config.logRetention,
      logGroupName: `/aws/vendedlogs/states/ConnectorFileImportStateMachine-${this.node.addr}`,
    });

    const workflow = setProcessing.next(connectorImportJob).next(setProcessed);
    const stateMachine = new sfn.StateMachine(
      this,
      "ConnectorFileImportStateMachine",
      {
        definitionBody: sfn.DefinitionBody.fromChainable(workflow),
        timeout: cdk.Duration.hours(12),
        comment: "Connector file import (Dropbox/SharePoint) workflow",
        tracingEnabled: true,
        logs: {
          destination: logGroup,
          level: sfn.LogLevel.ALL,
        },
      }
    );

    stateMachine.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ["events:CreateRule", "events:PutRule", "events:PutTargets"],
        resources: ["*"],
      })
    );
    stateMachine.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ["batch:SubmitJob"],
        resources: [
          props.fileImportBatchJob.jobQueue.jobQueueArn,
          props.fileImportBatchJob.fileImportJob.jobDefinitionArn,
        ],
      })
    );
    props.ragDynamoDBTables.documentsTable.grantReadWriteData(
      stateMachine.role
    );

    this.stateMachine = stateMachine;
  }
}
