import {
  Button,
  FormField,
  Input,
  Modal,
  Select,
  SpaceBetween,
  Textarea,
} from "@cloudscape-design/components";
import { useState } from "react";
import type { CreateConnectorInput } from "../../../common/api-client/connectors-client";

const CONNECTOR_TYPE_OPTIONS = [
  { value: "azure_sql", label: "Azure SQL" },
  { value: "dropbox", label: "Dropbox" },
  { value: "sharepoint", label: "SharePoint" },
];

export interface CreateConnectorModalProps {
  visible: boolean;
  workspaceId: string;
  workspaceOptions: { value: string; label: string }[];
  onDismiss: () => void;
  onSubmit: (input: CreateConnectorInput) => Promise<void>;
}

export default function CreateConnectorModal({
  visible,
  workspaceId,
  workspaceOptions,
  onDismiss,
  onSubmit,
}: CreateConnectorModalProps) {
  const [name, setName] = useState("");
  const [type, setType] = useState<{ value: string; label: string } | null>(
    null
  );
  const [endpointUrl, setEndpointUrl] = useState("");
  const [credentialsJson, setCredentialsJson] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    setError(null);
    if (!name.trim()) {
      setError("Name is required.");
      return;
    }
    if (!type?.value) {
      setError("Connector type is required.");
      return;
    }
    if (!credentialsJson.trim()) {
      setError(
        "Credentials are required. Provide a JSON object (e.g. server, database, username, password) or paste a Secrets Manager secret ARN."
      );
      return;
    }
    setSubmitting(true);
    try {
      const trimmed = credentialsJson.trim();
      const isArn = trimmed.startsWith("arn:aws:secretsmanager:");
      await onSubmit({
        workspaceId,
        name: name.trim(),
        type: type.value,
        endpoint:
          endpointUrl.trim()
            ? { type: "mcp_server", url: endpointUrl.trim() }
            : undefined,
        ...(isArn
          ? { credentialsSecretArn: trimmed }
          : { credentials: trimmed }),
      });
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

  const handleDismiss = () => {
    if (!submitting) {
      setError(null);
      onDismiss();
    }
  };

  return (
    <Modal
      visible={visible}
      onDismiss={handleDismiss}
      header="Create connector"
      footer={
        <SpaceBetween direction="horizontal" size="xs">
          <Button variant="link" onClick={handleDismiss} disabled={submitting}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleSubmit}
            loading={submitting}
            disabled={submitting}
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
        <FormField label="Workspace" description="Connector will be created in this workspace.">
          <Select
            selectedOption={
              workspaceOptions.find((o) => o.value === workspaceId) ?? null
            }
            options={workspaceOptions}
            disabled
            placeholder="Select workspace"
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
            onChange={({ detail }) => setType(detail.selectedOption)}
            options={CONNECTOR_TYPE_OPTIONS}
            placeholder="Select type"
          />
        </FormField>
        <FormField
          label="Endpoint URL"
          description="Optional. MCP server URL (e.g. from Connector Gateway)."
        >
          <Input
            value={endpointUrl}
            onChange={({ detail }) => setEndpointUrl(detail.value)}
            placeholder="https://..."
          />
        </FormField>
        <FormField
          label="Credentials"
          constraintText="JSON object (e.g. server, database, username, password for Azure SQL) or a Secrets Manager ARN."
          description="Stored securely in AWS Secrets Manager. Never share credentials."
        >
          <Textarea
            value={credentialsJson}
            onChange={({ detail }) => setCredentialsJson(detail.value)}
            placeholder='{"server": "...", "database": "...", "username": "...", "password": "..."}'
            rows={4}
          />
        </FormField>
      </SpaceBetween>
    </Modal>
  );
}
