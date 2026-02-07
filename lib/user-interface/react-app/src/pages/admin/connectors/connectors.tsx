import {
  Alert,
  BreadcrumbGroup,
  Button,
  Header,
  SpaceBetween,
  Table,
  Select,
  StatusIndicator,
  Modal,
} from "@cloudscape-design/components";
import { useCallback, useContext, useEffect, useState } from "react";
import useOnFollow from "../../../common/hooks/use-on-follow";
import BaseAppLayout from "../../../components/base-app-layout";
import { CHATBOT_NAME } from "../../../common/constants";
import { AppContext } from "../../../common/app-context";
import { ApiClient } from "../../../common/api-client/api-client";
import { Utils } from "../../../common/utils";
import type {
  Connector,
  CreateConnectorInput,
} from "../../../common/api-client/connectors-client";
import CreateConnectorModal from "./create-connector-modal";
import { Workspace } from "../../../API";

export default function Connectors() {
  const onFollow = useOnFollow();
  const appContext = useContext(AppContext);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceOptions, setWorkspaceOptions] = useState<
    { value: string; label: string }[]
  >([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState<string | null>(
    null
  );
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [loading, setLoading] = useState(true);
  const [globalError, setGlobalError] = useState<string | undefined>(undefined);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [testResult, setTestResult] = useState<{
    connectorId: string;
    status: string;
    details?: string | null;
  } | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const connectorsEnabled = appContext?.config.connectors_enabled === true;

  const loadWorkspaces = useCallback(async () => {
    if (!appContext || !connectorsEnabled) return;
    const apiClient = new ApiClient(appContext);
    try {
      const result = await apiClient.workspaces.getWorkspaces();
      const list = (result.data as { listWorkspaces?: Workspace[] })
        ?.listWorkspaces ?? [];
      setWorkspaces(list);
      setWorkspaceOptions(
        list.map((w) => ({ value: w.id, label: w.name || w.id }))
      );
      if (list.length > 0 && !selectedWorkspaceId) {
        setSelectedWorkspaceId(list[0].id);
      }
    } catch (error) {
      setGlobalError(Utils.getErrorMessage(error));
    }
  }, [appContext, connectorsEnabled, selectedWorkspaceId]);

  const loadConnectors = useCallback(async () => {
    if (!appContext || !connectorsEnabled || !selectedWorkspaceId) {
      setConnectors([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setGlobalError(undefined);
    const apiClient = new ApiClient(appContext);
    try {
      const result = await apiClient.connectors.listConnectors(
        selectedWorkspaceId
      );
      const data = (result as { data?: { listConnectors?: Connector[] } })
        .data;
      setConnectors(data?.listConnectors ?? []);
    } catch (error) {
      setGlobalError(Utils.getErrorMessage(error));
      setConnectors([]);
    } finally {
      setLoading(false);
    }
  }, [appContext, connectorsEnabled, selectedWorkspaceId]);

  useEffect(() => {
    loadWorkspaces();
  }, [loadWorkspaces]);

  useEffect(() => {
    loadConnectors();
  }, [loadConnectors]);

  const handleCreateSubmit = async (input: CreateConnectorInput) => {
    if (!appContext) return;
    const apiClient = new ApiClient(appContext);
    await apiClient.connectors.createConnector(input);
    await loadConnectors();
  };

  const handleTest = async (connector: Connector) => {
    if (!appContext || !selectedWorkspaceId) return;
    const apiClient = new ApiClient(appContext);
    try {
      const result = await apiClient.connectors.testConnector(
        connector.id,
        selectedWorkspaceId
      );
      const data = (result as { data?: { testConnector?: { status: string; details?: string | null } } })
        .data;
      const health = data?.testConnector;
      setTestResult({
        connectorId: connector.id,
        status: health?.status ?? "unknown",
        details: health?.details ?? null,
      });
    } catch (error) {
      setTestResult({
        connectorId: connector.id,
        status: "error",
        details: Utils.getErrorMessage(error),
      });
    }
  };

  const handleDelete = async (connector: Connector) => {
    if (!appContext || !selectedWorkspaceId) return;
    setDeletingId(connector.id);
    const apiClient = new ApiClient(appContext);
    try {
      await apiClient.connectors.deleteConnector(
        connector.id,
        selectedWorkspaceId
      );
      await loadConnectors();
    } catch (error) {
      setGlobalError(Utils.getErrorMessage(error));
    } finally {
      setDeletingId(null);
    }
  };

  const columnDefinitions = [
    {
      id: "name",
      header: "Name",
      cell: (item: Connector) => item.name,
      sortingField: "name",
    },
    {
      id: "type",
      header: "Type",
      cell: (item: Connector) => item.type,
      sortingField: "type",
    },
    {
      id: "status",
      header: "Status",
      cell: (item: Connector) => (
        <StatusIndicator
          type={
            item.status === "active"
              ? "success"
              : item.status === "inactive"
                ? "stopped"
                : "pending"
          }
        >
          {item.status ?? "—"}
        </StatusIndicator>
      ),
    },
    {
      id: "updatedAt",
      header: "Last updated",
      cell: (item: Connector) =>
        item.updatedAt
          ? new Date(item.updatedAt).toLocaleString()
          : "—",
      sortingField: "updatedAt",
    },
    {
      id: "actions",
      header: "Actions",
      cell: (item: Connector) => (
        <SpaceBetween direction="horizontal" size="xs">
          <Button
            small
            onClick={() => handleTest(item)}
            disabled={deletingId === item.id}
          >
            Test
          </Button>
          <Button
            small
            onClick={() => handleDelete(item)}
            disabled={deletingId === item.id}
            loading={deletingId === item.id}
          >
            Delete
          </Button>
        </SpaceBetween>
      ),
    },
  ];

  return (
    <BaseAppLayout
      contentType="table"
      breadcrumbs={
        <BreadcrumbGroup
          onFollow={onFollow}
          items={[
            { text: CHATBOT_NAME, href: "/" },
            { text: "Admin", href: "/admin/applications" },
            { text: "Connectors", href: "/admin/connectors" },
          ]}
        />
      }
      content={
        <>
          {!connectorsEnabled && (
            <Alert type="warning" header="Connectors not enabled">
              Connectors are not enabled for this deployment. Enable them in the
              deployment configuration to manage data source connectors.
            </Alert>
          )}
          {globalError && (
            <Alert
              type="error"
              header="Error"
              dismissible
              onDismiss={() => setGlobalError(undefined)}
            >
              {globalError}
            </Alert>
          )}

          <CreateConnectorModal
            visible={showCreateModal}
            workspaceId={selectedWorkspaceId ?? ""}
            workspaceOptions={workspaceOptions}
            onDismiss={() => setShowCreateModal(false)}
            onSubmit={handleCreateSubmit}
          />

          {testResult && (
            <Modal
              visible={true}
              onDismiss={() => setTestResult(null)}
              header={`Test result: ${testResult.status}`}
              footer={
                <Button variant="primary" onClick={() => setTestResult(null)}>
                  Close
                </Button>
              }
            >
              <SpaceBetween size="m">
                <div>
                  <strong>Status:</strong> {testResult.status}
                </div>
                {testResult.details && (
                  <div>
                    <strong>Details:</strong>
                    <pre
                      style={{
                        marginTop: 4,
                        padding: 8,
                        background: "var(--color-background-container-content)",
                        borderRadius: 4,
                        overflow: "auto",
                        maxHeight: 200,
                      }}
                    >
                      {testResult.details}
                    </pre>
                  </div>
                )}
              </SpaceBetween>
            </Modal>
          )}

          <Table
            variant="full-page"
            stickyHeader
            columnDefinitions={columnDefinitions}
            items={connectors}
            loading={loading}
            loadingText="Loading connectors"
            header={
              <Header
                variant="awsui-h1-sticky"
                actions={
                  <SpaceBetween size="xs" direction="horizontal">
                    <Select
                      selectedOption={
                        workspaceOptions.find(
                          (o) => o.value === selectedWorkspaceId
                        ) ?? null
                      }
                      onChange={({ detail }) =>
                        setSelectedWorkspaceId(detail.selectedOption?.value ?? null)
                      }
                      options={workspaceOptions}
                      placeholder="Select workspace"
                      empty="No workspaces"
                      disabled={workspaceOptions.length === 0}
                    />
                    <Button
                      iconName="refresh"
                      onClick={loadConnectors}
                      disabled={!selectedWorkspaceId}
                    />
                    <Button
                      variant="primary"
                      onClick={() => setShowCreateModal(true)}
                      disabled={!selectedWorkspaceId}
                    >
                      Create connector
                    </Button>
                  </SpaceBetween>
                }
              >
                Connectors
              </Header>
            }
            empty={
              !selectedWorkspaceId ? (
                "Select a workspace to list connectors."
              ) : (
                "No connectors in this workspace. Create one to connect to external data sources (e.g. Azure SQL, Dropbox)."
              )
            }
          />
        </>
      }
    />
  );
}
