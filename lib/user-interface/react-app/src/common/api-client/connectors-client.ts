import { API } from "aws-amplify";
import { GraphQLQuery, GraphQLResult } from "@aws-amplify/api";

/**
 * Connector types matching the GraphQL schema (Part 4 API client).
 * credentialsSecretArn is masked (null) in API responses.
 */
export interface ConnectorEndpoint {
  type?: string | null;
  url?: string | null;
}

export interface ConnectorRateLimits {
  maxRowsPerQuery?: number | null;
}

export interface ConnectorAllowedResources {
  schemas?: (string | null)[] | null;
  tables?: (string | null)[] | null;
  views?: (string | null)[] | null;
  rateLimits?: ConnectorRateLimits | null;
}

export interface Connector {
  __typename?: "Connector";
  id: string;
  workspaceId: string;
  name: string;
  type: string;
  status?: string | null;
  endpoint?: ConnectorEndpoint | null;
  credentialsSecretArn?: string | null;
  applicationIds?: (string | null)[] | null;
  allowedResources?: ConnectorAllowedResources | null;
  createdAt?: string | null;
  updatedAt?: string | null;
}

export interface ConnectorHealth {
  __typename?: "ConnectorHealth";
  status: string;
  details?: string | null;
  timestamp?: string | null;
}

export interface CreateConnectorInput {
  workspaceId: string;
  name: string;
  type: string;
  endpoint?: { type?: string; url?: string } | null;
  credentialsSecretArn?: string | null;
  credentials?: string | null;
  applicationIds?: (string | null)[] | null;
  allowedResources?: {
    schemas?: (string | null)[] | null;
    tables?: (string | null)[] | null;
    views?: (string | null)[] | null;
    rateLimits?: { maxRowsPerQuery?: number | null } | null;
  } | null;
}

export interface UpdateConnectorInput {
  connectorId: string;
  workspaceId: string;
  name?: string | null;
  type?: string | null;
  endpoint?: { type?: string; url?: string } | null;
  credentialsSecretArn?: string | null;
  credentials?: string | null;
  applicationIds?: (string | null)[] | null;
  allowedResources?: CreateConnectorInput["allowedResources"];
  status?: string | null;
}

const listConnectorsQuery = /* GraphQL */ `
  query ListConnectors($workspaceId: String!, $connectorType: String) {
    listConnectors(workspaceId: $workspaceId, connectorType: $connectorType) {
      id
      workspaceId
      name
      type
      status
      endpoint { type url }
      applicationIds
      allowedResources { schemas tables views rateLimits { maxRowsPerQuery } }
      createdAt
      updatedAt
      __typename
    }
  }
`;

const getConnectorQuery = /* GraphQL */ `
  query GetConnector($connectorId: String!, $workspaceId: String!) {
    getConnector(connectorId: $connectorId, workspaceId: $workspaceId) {
      id
      workspaceId
      name
      type
      status
      endpoint { type url }
      applicationIds
      allowedResources { schemas tables views rateLimits { maxRowsPerQuery } }
      createdAt
      updatedAt
      __typename
    }
  }
`;

const createConnectorMutation = /* GraphQL */ `
  mutation CreateConnector($input: CreateConnectorInput!) {
    createConnector(input: $input) {
      id
      workspaceId
      name
      type
      status
      endpoint { type url }
      applicationIds
      allowedResources { schemas tables views rateLimits { maxRowsPerQuery } }
      createdAt
      updatedAt
      __typename
    }
  }
`;

const updateConnectorMutation = /* GraphQL */ `
  mutation UpdateConnector($input: UpdateConnectorInput!) {
    updateConnector(input: $input) {
      id
      workspaceId
      name
      type
      status
      endpoint { type url }
      applicationIds
      allowedResources { schemas tables views rateLimits { maxRowsPerQuery } }
      createdAt
      updatedAt
      __typename
    }
  }
`;

const deleteConnectorMutation = /* GraphQL */ `
  mutation DeleteConnector($connectorId: String!, $workspaceId: String!) {
    deleteConnector(connectorId: $connectorId, workspaceId: $workspaceId)
  }
`;

const testConnectorQuery = /* GraphQL */ `
  query TestConnector($input: TestConnectorInput!) {
    testConnector(input: $input) {
      status
      details
      timestamp
      __typename
    }
  }
`;

export interface ListConnectorsResult {
  data?: { listConnectors: Connector[] };
  errors?: unknown[];
}

export interface GetConnectorResult {
  data?: { getConnector: Connector | null };
  errors?: unknown[];
}

export interface CreateConnectorResult {
  data?: { createConnector: Connector };
  errors?: unknown[];
}

export interface UpdateConnectorResult {
  data?: { updateConnector: Connector };
  errors?: unknown[];
}

export interface DeleteConnectorResult {
  data?: { deleteConnector: boolean };
  errors?: unknown[];
}

export interface TestConnectorResult {
  data?: { testConnector: ConnectorHealth };
  errors?: unknown[];
}

export class ConnectorsClient {
  async listConnectors(
    workspaceId: string,
    connectorType?: string | null
  ): Promise<GraphQLResult<ListConnectorsResult["data"]>> {
    return API.graphql({
      query: listConnectorsQuery,
      variables: { workspaceId, connectorType: connectorType ?? null },
    }) as Promise<GraphQLResult<ListConnectorsResult["data"]>>;
  }

  async getConnector(
    connectorId: string,
    workspaceId: string
  ): Promise<GraphQLResult<GetConnectorResult["data"]>> {
    return API.graphql({
      query: getConnectorQuery,
      variables: { connectorId, workspaceId },
    }) as Promise<GraphQLResult<GetConnectorResult["data"]>>;
  }

  async createConnector(
    input: CreateConnectorInput
  ): Promise<GraphQLResult<CreateConnectorResult["data"]>> {
    return API.graphql({
      query: createConnectorMutation,
      variables: { input },
    }) as Promise<GraphQLResult<CreateConnectorResult["data"]>>;
  }

  async updateConnector(
    input: UpdateConnectorInput
  ): Promise<GraphQLResult<UpdateConnectorResult["data"]>> {
    return API.graphql({
      query: updateConnectorMutation,
      variables: { input },
    }) as Promise<GraphQLResult<UpdateConnectorResult["data"]>>;
  }

  async deleteConnector(
    connectorId: string,
    workspaceId: string
  ): Promise<GraphQLResult<DeleteConnectorResult["data"]>> {
    return API.graphql({
      query: deleteConnectorMutation,
      variables: { connectorId, workspaceId },
    }) as Promise<GraphQLResult<DeleteConnectorResult["data"]>>;
  }

  async testConnector(
    connectorId: string,
    workspaceId: string
  ): Promise<GraphQLResult<TestConnectorResult["data"]>> {
    return API.graphql({
      query: testConnectorQuery,
      variables: {
        input: { connectorId, workspaceId },
      },
    }) as Promise<GraphQLResult<TestConnectorResult["data"]>>;
  }
}
