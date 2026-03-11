import * as cdk from "aws-cdk-lib";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as ecs from "aws-cdk-lib/aws-ecs";
import * as elbv2 from "aws-cdk-lib/aws-elasticloadbalancingv2";
import * as iam from "aws-cdk-lib/aws-iam";
import * as logs from "aws-cdk-lib/aws-logs";
import * as ecr_assets from "aws-cdk-lib/aws-ecr-assets";
import { Construct } from "constructs";
import * as path from "path";

export interface ConnectorGatewayProps {
  readonly vpc: ec2.Vpc;
  readonly prefix: string;
  readonly sharepointEnabled?: boolean;
  readonly dropboxEnabled?: boolean;
}

export class ConnectorGateway extends Construct {
  public readonly cluster: ecs.Cluster;
  public readonly loadBalancer: elbv2.ApplicationLoadBalancer;
  public readonly listener: elbv2.ApplicationListener;
  public readonly securityGroup: ec2.SecurityGroup;
  public readonly albSecurityGroup: ec2.SecurityGroup;

  constructor(scope: Construct, id: string, props: ConnectorGatewayProps) {
    super(scope, id);

    // ECS Cluster
    const cluster = new ecs.Cluster(this, "ConnectorCluster", {
      vpc: props.vpc,
      containerInsights: true,
    });

    // Security Group for ALB
    const albSecurityGroup = new ec2.SecurityGroup(
      this,
      "ConnectorALBSecurityGroup",
      {
        vpc: props.vpc,
        allowAllOutbound: true,
        description: "Security group for Connector Gateway ALB",
      }
    );

    // Security Group for ECS Tasks
    const taskSecurityGroup = new ec2.SecurityGroup(
      this,
      "ConnectorTaskSecurityGroup",
      {
        vpc: props.vpc,
        allowAllOutbound: true,
        description: "Security group for Connector Gateway ECS tasks",
      }
    );

    // Allow ALB to reach tasks
    taskSecurityGroup.addIngressRule(
      albSecurityGroup,
      ec2.Port.tcp(8080),
      "Allow traffic from ALB"
    );

    // Allow Lambda (or VPC endpoint) to reach ALB
    // Note: This will be refined when Lambda VPC configuration is known
    // For now, allow from VPC CIDR - this should be restricted further in production
    albSecurityGroup.addIngressRule(
      ec2.Peer.ipv4(props.vpc.vpcCidrBlock),
      ec2.Port.tcp(80),
      "Allow traffic from VPC (Lambda/VPC endpoints)"
    );

    // Internal Application Load Balancer
    const loadBalancer = new elbv2.ApplicationLoadBalancer(
      this,
      "ConnectorALB",
      {
        vpc: props.vpc,
        internetFacing: false,
        securityGroup: albSecurityGroup,
        vpcSubnets: props.vpc.selectSubnets({
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
        }),
      }
    );

    // HTTP Listener (MCP servers will handle HTTPS internally if needed).
    // ALB requires at least one default action; path-based rules are added per connector type below.
    const listener = loadBalancer.addListener("ConnectorListener", {
      port: 80,
      protocol: elbv2.ApplicationProtocol.HTTP,
      defaultAction: elbv2.ListenerAction.fixedResponse(404, {
        contentType: "application/json",
        messageBody: '{"error":"Not Found","message":"No connector route matched"}',
      }),
    });

    // Create ECS services for each enabled connector type
    // Note: Container images will be implemented in Phase 6
    // For now, we create the infrastructure structure

    if (props.sharepointEnabled) {
      this.createConnectorService(
        cluster,
        listener,
        taskSecurityGroup,
        "sharepoint",
        "/sharepoint",
        props.prefix
      );
    }

    if (props.dropboxEnabled) {
      this.createConnectorService(
        cluster,
        listener,
        taskSecurityGroup,
        "dropbox",
        "/dropbox",
        props.prefix
      );
    }

    this.cluster = cluster;
    this.loadBalancer = loadBalancer;
    this.listener = listener;
    this.securityGroup = taskSecurityGroup;
    this.albSecurityGroup = albSecurityGroup;
  }

  private createConnectorService(
    cluster: ecs.Cluster,
    listener: elbv2.ApplicationListener,
    securityGroup: ec2.SecurityGroup,
    connectorType: string,
    routePath: string,
    prefix: string
  ): void {
    // Task Execution Role (for pulling images, CloudWatch logs, etc.)
    const executionRole = new iam.Role(
      this,
      `${connectorType}ExecutionRole`,
      {
        assumedBy: new iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        managedPolicies: [
          iam.ManagedPolicy.fromAwsManagedPolicyName(
            "service-role/AmazonECSTaskExecutionRolePolicy"
          ),
        ],
      }
    );

    // Task Role (for application permissions - Secrets Manager access)
    const taskRole = new iam.Role(this, `${connectorType}TaskRole`, {
      assumedBy: new iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
      description: `Task role for ${connectorType} connector MCP server`,
    });

    // Grant Secrets Manager read access
    // Note: In production, this should be scoped to specific secret ARNs per connector instance
    // For Phase 6, we grant GetSecretValue on all secrets; this will be refined when
    // connector registration is implemented to grant per-secret ARN access
    taskRole.addToPolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: [
          "secretsmanager:DescribeSecret",
          "secretsmanager:GetSecretValue",
          "secretsmanager:GetResourcePolicy",
        ],
        resources: ["*"],
      })
    );

    // Log Group
    const logGroup = new logs.LogGroup(
      this,
      `${connectorType}LogGroup`,
      {
        logGroupName: `/ecs/${prefix}-connector-${connectorType}`,
        retention: logs.RetentionDays.ONE_WEEK,
        removalPolicy: cdk.RemovalPolicy.DESTROY,
      }
    );

    // Task Definition
    const taskDefinition = new ecs.FargateTaskDefinition(
      this,
      `${connectorType}TaskDefinition`,
      {
        executionRole,
        taskRole,
        memoryLimitMiB: 512,
        cpu: 256,
      }
    );

    // Build Docker image per connector type
    let containerImage: ecs.ContainerImage;
    if (connectorType === "dropbox") {
      const dockerImage = new ecr_assets.DockerImageAsset(
        this,
        `${connectorType}DockerImage`,
        {
          directory: path.join(__dirname, "..", "dropbox-mcp-server"),
          platform: ecr_assets.Platform.LINUX_AMD64,
        }
      );
      containerImage = ecs.ContainerImage.fromDockerImageAsset(dockerImage);
    } else {
      // Placeholder for other connector types (e.g. sharepoint)
      containerImage = ecs.ContainerImage.fromRegistry(
        "public.ecr.aws/docker/library/python:3.11-slim"
      );
    }

    // Container
    const container = taskDefinition.addContainer(
      `${connectorType}Container`,
      {
        image: containerImage,
        logging: ecs.LogDrivers.awsLogs({
          streamPrefix: connectorType,
          logGroup,
        }),
        environment: {
          CONNECTOR_TYPE: connectorType,
          AWS_DEFAULT_REGION: cdk.Stack.of(this).region,
          PORT: "8080",
          // ALLOWED_RESOURCES and CREDENTIALS_SECRET_ARN will be set per connector instance
          // via task definition overrides or environment variable injection
          // For now, these are placeholders that will be configured when connectors are registered
        },
        healthCheck: {
          command: [
            "CMD-SHELL",
            "curl -f http://localhost:8080/health || exit 1",
          ],
          interval: cdk.Duration.seconds(30),
          timeout: cdk.Duration.seconds(5),
          retries: 3,
          startPeriod: cdk.Duration.seconds(60),
        },
      }
    );

    container.addPortMappings({
      containerPort: 8080,
      protocol: ecs.Protocol.TCP,
    });

    // ECS Service
    const service = new ecs.FargateService(
      this,
      `${connectorType}Service`,
      {
        cluster,
        taskDefinition,
        desiredCount: 1,
        securityGroups: [securityGroup],
        vpcSubnets: cluster.vpc.selectSubnets({
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
        }),
      }
    );

    // Target Group (port must match container port 8080)
    const targetGroup = new elbv2.ApplicationTargetGroup(
      this,
      `${connectorType}TargetGroup`,
      {
        vpc: cluster.vpc,
        port: 8080,
        protocol: elbv2.ApplicationProtocol.HTTP,
        targets: [service],
        healthCheck: {
          path: "/health",
          interval: cdk.Duration.seconds(30),
          timeout: cdk.Duration.seconds(5),
          healthyThresholdCount: 2,
          unhealthyThresholdCount: 3,
        },
      }
    );

    // Listener Rule
    listener.addTargetGroups(`${connectorType}Rule`, {
      targetGroups: [targetGroup],
      priority: this.getPriorityForConnector(connectorType),
      conditions: [elbv2.ListenerCondition.pathPatterns([`${routePath}/*`])],
    });
  }

  private getPriorityForConnector(connectorType: string): number {
    // Assign priorities to avoid conflicts
    const priorities: Record<string, number> = {
      sharepoint: 200,
      dropbox: 300,
    };
    return priorities[connectorType] ?? 400;
  }
}
