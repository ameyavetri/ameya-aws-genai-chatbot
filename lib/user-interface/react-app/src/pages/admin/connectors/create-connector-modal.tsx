import {
  Button,
  FormField,
  Input,
  Modal,
  Select,
  SpaceBetween,
  Textarea,
} from "@cloudscape-design/components";
import { useEffect, useState } from "react";
import type { CreateConnectorInput } from "../../../common/api-client/connectors-client";

const CONNECTOR_TYPE_OPTIONS = [
  { value: "azure_sql", label: "Azure SQL" },
  { value: "dropbox", label: "Dropbox" },
  { value: "sharepoint", label: "SharePoint" },
];

const CREDENTIALS_HINT: Record<string, string> = {
  azure_sql:
    'JSON object: {"server": "...", "database": "...", "username": "...", "password": "..."} or a Secrets Manager ARN.',
  dropbox:
    'Dropbox credentials (JSON). Recommended: {"app_key": "...", "app_secret": "...", "refresh_token": "..."} for auto-refresh. Legacy: {"access_token": "..."} (expires ~4h). Create app at https://www.dropbox.com/developers/apps, use OAuth2 with offline access for refresh_token. Or use a Secrets Manager ARN.',
  sharepoint:
    'SharePoint/Entra app credentials (JSON) or Secrets Manager ARN. Example: {"clientId": "...", "clientSecret": "...", "tenantId": "..."}.',
};

const ENDPOINT_HINT: Record<string, string> = {
  azure_sql: "Optional. Leave empty to use built-in connector.",
  dropbox:
    "Leave empty when using only an access token (recommended). Do not use the Dropbox API URL (dropboxapi.com)—that is not an MCP server. Only add a URL if you have a Connector Gateway MCP server for Dropbox.",
  sharepoint:
    "Optional. MCP server URL (e.g. from Connector Gateway) for SharePoint.",
};

export interface CreateConnectorModalProps {
  visible: boolean;
  workspaceId: string;
  workspaceOptions: { value: string; label: string }[];
  onDismiss: () => void;
  onSubmit: (input: CreateConnectorInput) => Promise<void>;
  onTestConnection?: (
    input: CreateConnectorInput
  ) => Promise<{ status: string; details?: string | null }>;
}

function buildInput(
  workspaceId: string,
  name: string,
  typeValue: string,
  endpointUrl: string,
  credentialsJson: string
): CreateConnectorInput | null {
  if (!name.trim() || !typeValue || !credentialsJson.trim()) return null;
  const trimmed = credentialsJson.trim();
  const isArn = trimmed.startsWith("arn:aws:secretsmanager:");
  return {
    workspaceId,
    name: name.trim(),
    type: typeValue,
    endpoint:
      endpointUrl.trim()
        ? { type: "mcp_server", url: endpointUrl.trim() }
        : undefined,
    ...(isArn ? { credentialsSecretArn: trimmed } : { credentials: trimmed }),
  };
}

export default function CreateConnectorModal({
  visible,
  workspaceId,
  workspaceOptions,
  onDismiss,
  onSubmit,
  onTestConnection,
}: CreateConnectorModalProps) {
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState(workspaceId);
  const [name, setName] = useState("");
  const [type, setType] = useState<{ value: string; label: string } | null>(
    null
  );
  const [endpointUrl, setEndpointUrl] = useState("");
  const [credentialsJson, setCredentialsJson] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{
    status: string;
    details?: string | null;
  } | null>(null);

  useEffect(() => {
    if (visible) {
      setSelectedWorkspaceId(workspaceId);
      setTestResult(null);
    }
  }, [visible, workspaceId]);

  const handleSubmit = async () => {
    setError(null);
    setTestResult(null);
    if (!name.trim()) {
      setError("Name is required.");
      return;
    }
    if (!type?.value) {
      setError("Connector type is required.");
      return;
    }
    if (!credentialsJson.trim()) {
      setError("Credentials are required.");
      return;
    }
    const input = buildInput(
      selectedWorkspaceId,
      name,
      type.value,
      endpointUrl,
      credentialsJson
    );
    if (!input) return;
    setSubmitting(true);
    try {
      await onSubmit(input);
      setName("");
      setType(null);
      setEndpointUrl("");
      setCredentialsJson("");
      onDismiss();
    } catch (e: unknown) {
      const message =
        e && typeof e === "object" && "errors" in e
          ? (e as { errors: { message?: string }[] }).errors
              ?.map((x) => x.message)
              .join(", ")
          : String(e);
      setError(message || "Failed to create connector.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleTestConnection = async () => {
    setError(null);
    setTestResult(null);
    if (!type?.value) {
      setError("Select a connector type first.");
      return;
    }
    if (!credentialsJson.trim()) {
      setError("Enter credentials to test.");
      return;
    }
    const input = buildInput(
      selectedWorkspaceId,
      `_test_${Date.now()}`,
      type.value,
      endpointUrl,
      credentialsJson
    );
    if (!input || !onTestConnection) return;
    setTesting(true);
    try {
      const result = await onTestConnection(input);
      setTestResult(result);
    } catch (e: unknown) {
      const message =
        e && typeof e === "object" && "errors" in e
          ? (e as { errors: { message?: string }[] }).errors
              ?.map((x) => x.message)
              .join(", ")
          : String(e);
      setError(message || "Test failed.");
    } finally {
      setTesting(false);
    }
  };

  const handleDismiss = () => {
    if (!submitting && !testing) {
      setError(null);
      setTestResult(null);
      onDismiss();
    }
  };

  const credentialsHint = type?.value
    ? CREDENTIALS_HINT[type.value] ?? CREDENTIALS_HINT.azure_sql
    : CREDENTIALS_HINT.azure_sql;
  const endpointHint = type?.value
    ? ENDPOINT_HINT[type.value] ?? ENDPOINT_HINT.azure_sql
    : ENDPOINT_HINT.azure_sql;

  return (
    <Modal
      visible={visible}
      onDismiss={handleDismiss}
      header="Create connector"
      footer={
        <SpaceBetween direction="horizontal" size="xs">
          <Button variant="link" onClick={handleDismiss} disabled={submitting || testing}>
            Cancel
          </Button>
          {onTestConnection && (
            <Button
              variant="normal"
              onClick={handleTestConnection}
              loading={testing}
              disabled={submitting || testing || !type?.value || !credentialsJson.trim()}
            >
              Test connection
            </Button>
          )}
          <Button
            variant="primary"
            onClick={handleSubmit}
            loading={submitting}
            disabled={submitting || testing}
          >
            Create connector
          </Button>
        </SpaceBetween>
      }
    >
      <SpaceBetween size="m">
        {error && (
          <div style={{ color: "var(--color-text-error)" }}>{error}</div>
        )}
        {testResult && (
          <div
            style={{
              padding: 8,
              background:
                testResult.status === "healthy"
                  ? "var(--color-background-success)"
                  : "var(--color-background-error)",
              borderRadius: 4,
            }}
          >
            <strong>Test result:</strong> {testResult.status}
            {testResult.details && (
              <pre style={{ marginTop: 4, whiteSpace: "pre-wrap", fontSize: 12 }}>
                {testResult.details}
              </pre>
            )}
          </div>
        )}
        <FormField
          label="Workspace"
          description="Connector will be created in this workspace."
        >
          <Select
            selectedOption={
              workspaceOptions.find((o) => o.value === selectedWorkspaceId) ?? null
            }
            onChange={({ detail }) =>
              setSelectedWorkspaceId(detail.selectedOption?.value ?? workspaceId)
            }
            options={workspaceOptions}
            placeholder="Select workspace"
            disabled={workspaceOptions.length === 0}
          />
        </FormField>
        <FormField label="Name" constraintText="Required.">
          <Input
            value={name}
            onChange={({ detail }) => setName(detail.value)}
            placeholder="e.g. Production SQL"
          />
        </FormField>
        <FormField label="Connector type" constraintText="Required.">
          <Select
            selectedOption={type}
            onChange={({ detail }) =>
              setType(
                detail.selectedOption
                  ? {
                      value: detail.selectedOption.value ?? "",
                      label:
                        detail.selectedOption.label ??
                        detail.selectedOption.value ??
                        "",
                    }
                  : null
              )
            }
            options={CONNECTOR_TYPE_OPTIONS}
            placeholder="Select type"
          />
        </FormField>
        <FormField
          label="Endpoint URL"
          description={endpointHint}
        >
          <Input
            value={endpointUrl}
            onChange={({ detail }) => setEndpointUrl(detail.value)}
            placeholder="https://..."
          />
        </FormField>
        <FormField
          label="Credentials"
          constraintText={credentialsHint}
          description="Stored securely in AWS Secrets Manager. Never share credentials."
        >
          <Textarea
            value={credentialsJson}
            onChange={({ detail }) => setCredentialsJson(detail.value)}
            placeholder={
              type?.value === "dropbox"
                ? '{"app_key": "...", "app_secret": "...", "refresh_token": "..."}'
                : type?.value === "sharepoint"
                  ? '{"clientId": "...", "clientSecret": "...", "tenantId": "..."}'
                  : '{"server": "...", "database": "...", "username": "...", "password": "..."}'
            }
            rows={4}
          />
        </FormField>
      </SpaceBetween>
    </Modal>
  );
}
