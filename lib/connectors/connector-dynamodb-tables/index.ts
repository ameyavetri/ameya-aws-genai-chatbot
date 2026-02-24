import * as cdk from "aws-cdk-lib";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as kms from "aws-cdk-lib/aws-kms";
import { Construct } from "constructs";

export interface ConnectorDynamoDBTablesProps {
  readonly prefix: string;
  readonly retainOnDelete?: boolean;
  readonly deletionProtection?: boolean;
  readonly kmsKey?: kms.Key;
}

export class ConnectorDynamoDBTables extends Construct {
  public readonly connectorsTable: dynamodb.Table;
  public readonly byWorkspaceIndexName: string = "by_workspace";

  constructor(
    scope: Construct,
    id: string,
    props: ConnectorDynamoDBTablesProps
  ) {
    super(scope, id);

    const connectorsTable = new dynamodb.Table(this, "ConnectorsTable", {
      tableName: `${props.prefix}-connectors`,
      partitionKey: {
        name: "connector_id",
        type: dynamodb.AttributeType.STRING,
      },
      sortKey: {
        name: "workspace_id",
        type: dynamodb.AttributeType.STRING,
      },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      encryption: props.kmsKey
        ? dynamodb.TableEncryption.CUSTOMER_MANAGED
        : dynamodb.TableEncryption.AWS_MANAGED,
      encryptionKey: props.kmsKey,
      pointInTimeRecoverySpecification: {
        pointInTimeRecoveryEnabled: true,
      },
      removalPolicy:
        props.retainOnDelete === true
          ? cdk.RemovalPolicy.RETAIN_ON_UPDATE_OR_DELETE
          : cdk.RemovalPolicy.DESTROY,
      deletionProtection: props.deletionProtection,
    });

    connectorsTable.addGlobalSecondaryIndex({
      indexName: this.byWorkspaceIndexName,
      partitionKey: {
        name: "workspace_id",
        type: dynamodb.AttributeType.STRING,
      },
      sortKey: {
        name: "connector_type",
        type: dynamodb.AttributeType.STRING,
      },
    });

    this.connectorsTable = connectorsTable;
  }
}
