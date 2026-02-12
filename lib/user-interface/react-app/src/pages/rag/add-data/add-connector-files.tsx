import {
  Alert,
  Button,
  Container,
  Flashbar,
  FormField,
  Header,
  SpaceBetween,
  Table,
  TableProps,
} from "@cloudscape-design/components";
import { Utils } from "../../../common/utils";
import { useContext, useEffect, useState } from "react";
import { AddDataData } from "./types";
import { AppContext } from "../../../common/app-context";
import { ApiClient } from "../../../common/api-client/api-client";
import {
  Connector,
  ListConnectorFolderItem,
} from "../../../common/api-client/connectors-client";
import { Workspace } from "../../../API";

export interface AddConnectorFilesProps {
  data: AddDataData;
  validate: () => boolean;
  selectedWorkspace?: Workspace;
}

const FILE_SOURCE_TYPES = ["dropbox", "sharepoint"];

export default function AddConnectorFiles(props: AddConnectorFilesProps) {
  const appContext = useContext(AppContext);
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [connectorsLoading, setConnectorsLoading] = useState(false);
  const [selectedConnector, setSelectedConnector] = useState<Connector | null>(
    null
  );
  const [pathStack, setPathStack] = useState<string[]>([]);
  const [items, setItems] = useState<ListConnectorFolderItem[]>([]);
  const [itemsLoading, setItemsLoading] = useState(false);
  const [selectedPaths, setSelectedPaths] = useState<string[]>([]);
  const [ingesting, setIngesting] = useState(false);
  const [ingestResult, setIngestResult] = useState<{
    documentIds: string[];
    errors?: string[];
  } | null>(null);
  const [listError, setListError] = useState<string | null>(null);

  const workspaceId = props.data.workspace?.value ?? "";
  const currentPath = pathStack.length > 0 ? pathStack[pathStack.length - 1] : "";

  useEffect(() => {
    if (!appContext || !workspaceId) return;
    setConnectorsLoading(true);
    (async () => {
      const apiClient = new ApiClient(appContext);
      try {
        const result = await apiClient.connectors.listConnectors(workspaceId);
        const list = result.data?.listConnectors ?? [];
        const fileSource = list.filter((c) =>
          FILE_SOURCE_TYPES.includes((c.type || "").toLowerCase())
        );
        setConnectors(fileSource);
        setSelectedConnector((prev) => {
          if (fileSource.length === 0) return null;
          if (prev && fileSource.some((c) => c.id === prev.id)) return prev;
          return fileSource[0];
        });
      } finally {
        setConnectorsLoading(false);
      }
    })();
  }, [appContext, workspaceId]);

  useEffect(() => {
    if (!appContext || !selectedConnector || !workspaceId) {
      setItems([]);
      setListError(null);
      return;
    }
    setItemsLoading(true);
    setItems([]);
    setListError(null);
    (async () => {
      const apiClient = new ApiClient(appContext);
      try {
        const result = await apiClient.connectors.listConnectorFolder(
          workspaceId,
          selectedConnector.id,
          currentPath || undefined
        );
        const gqlResult = result as {
          data?: { listConnectorFolder?: ListConnectorFolderItem[] };
          errors?: { message?: string }[];
        };
        if (gqlResult.errors?.length) {
          const msg =
            gqlResult.errors[0]?.message ?? "Failed to list folder contents.";
          setListError(msg);
          setItems([]);
          return;
        }
        const list = gqlResult.data?.listConnectorFolder ?? [];
        setItems(list);
      } catch (e) {
        setListError(Utils.getErrorMessage(e));
        setItems([]);
      } finally {
        setItemsLoading(false);
      }
    })();
  }, [appContext, workspaceId, selectedConnector?.id, currentPath]);

  const onConnectorChange = (connector: Connector) => {
    setSelectedConnector(connector);
    setPathStack([]);
    setSelectedPaths([]);
    setIngestResult(null);
    setListError(null);
  };

  const navigateToFolder = (path: string) => {
    setPathStack((prev) => [...prev, path]);
    setSelectedPaths([]);
  };

  const goUp = () => {
    setPathStack((prev) => prev.slice(0, -1));
    setSelectedPaths([]);
  };

  const onIngest = async () => {
    if (!props.validate() || !selectedConnector || selectedPaths.length === 0)
      return;
    if (!appContext) return;
    setIngesting(true);
    setIngestResult(null);
    try {
      const apiClient = new ApiClient(appContext);
      const result = await apiClient.connectors.ingestFromConnector(
        workspaceId,
        selectedConnector.id,
        selectedPaths
      );
      const data = result.data?.ingestFromConnector;
      if (data) {
        setIngestResult({
          documentIds: data.documentIds ?? [],
          errors: (data.errors ?? []).filter(Boolean) as string[],
        });
        if ((data.documentIds?.length ?? 0) > 0) {
          setSelectedPaths([]);
        }
      }
    } catch (e) {
      setIngestResult({
        documentIds: [],
        errors: [e instanceof Error ? e.message : "Ingest failed"],
      });
    } finally {
      setIngesting(false);
    }
  };

  const tableColumnDefinitions: TableProps.ColumnDefinition<ListConnectorFolderItem>[] = [
    {
      id: "name",
      header: "Name",
      cell: (item) =>
        item.type === "folder" ? (
          <Button
            variant="link"
            onClick={() => navigateToFolder(item.path)}
          >
            {item.name}
          </Button>
        ) : (
          item.name
        ),
    },
    {
      id: "type",
      header: "Type",
      cell: (item) => (item.type === "folder" ? "Folder" : "File"),
      width: 100,
    },
    {
      id: "size",
      header: "Size",
      cell: (item) =>
        item.size != null ? `${(item.size / 1024).toFixed(1)} KB` : "—",
      width: 100,
    },
  ];

  const breadcrumbParts = pathStack.length === 0 ? ["Root"] : ["Root", ...pathStack];

  return (
    <Container
      header={
        <Header variant="h2" description="Browse and ingest files from Dropbox or SharePoint.">
          From Dropbox or SharePoint
        </Header>
      }
    >
      <SpaceBetween size="l">
        <FormField label="Connector">
          <select
            className="awsui-select awsui-input awsui-input-type-select"
            value={selectedConnector?.id ?? ""}
            onChange={(e) => {
              const c = connectors.find((x) => x.id === e.target.value);
              if (c) onConnectorChange(c);
            }}
            disabled={connectorsLoading || connectors.length === 0}
          >
            <option value="">
              {connectorsLoading
                ? "Loading…"
                : connectors.length === 0
                  ? "No Dropbox/SharePoint connectors"
                  : "Select a connector"}
            </option>
            {connectors.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.type})
              </option>
            ))}
          </select>
        </FormField>

        {selectedConnector && (
          <>
            <FormField label="Location">
              <SpaceBetween size="xs" direction="horizontal">
                {breadcrumbParts.map((part, i) => (
                  <span key={i}>
                    {i > 0 && " / "}
                    {i === 0 ? (
                      <span>{part}</span>
                    ) : i === breadcrumbParts.length - 1 ? (
                      <span>{part}</span>
                    ) : (
                      <Button
                        variant="link"
                        onClick={() =>
                          setPathStack((prev) => prev.slice(0, i))
                        }
                      >
                        {part}
                      </Button>
                    )}
                  </span>
                ))}
                {pathStack.length > 0 && (
                  <Button onClick={goUp}>Up</Button>
                )}
              </SpaceBetween>
            </FormField>

            {listError && (
              <Alert
                type="error"
                header="Could not list folder"
                dismissible
                onDismiss={() => setListError(null)}
              >
                {listError}
              </Alert>
            )}

            <Table
              columnDefinitions={tableColumnDefinitions}
              items={items}
              loading={itemsLoading}
              loadingText="Loading folder…"
              selectionType="multi"
              selectedItems={items.filter((i) => selectedPaths.includes(i.path))}
              onSelectionChange={({ detail }) => {
                const selected = detail.selectedItems.filter(
                  (i) => i.type === "file"
                );
                setSelectedPaths(selected.map((i) => i.path));
              }}
              trackBy="path"
              empty={listError ? " " : "No items in this folder."}
            />

            <SpaceBetween size="s" direction="horizontal">
              <Button
                variant="primary"
                disabled={
                  selectedPaths.length === 0 || ingesting
                }
                loading={ingesting}
                onClick={onIngest}
              >
                Ingest {selectedPaths.length > 0 ? `(${selectedPaths.length})` : ""} selected
              </Button>
            </SpaceBetween>

            {ingestResult && (
              <Flashbar
                items={[
                  ...(ingestResult.documentIds.length > 0
                    ? [
                        {
                          type: "success" as const,
                          content: `Ingested ${ingestResult.documentIds.length} file(s). Document IDs: ${ingestResult.documentIds.join(", ")}`,
                        },
                      ]
                    : []),
                  ...(ingestResult.errors && ingestResult.errors.length > 0
                    ? [
                        {
                          type: "error" as const,
                          content: ingestResult.errors.join("; "),
                        },
                      ]
                    : []),
                ]}
              />
            )}
          </>
        )}
      </SpaceBetween>
    </Container>
  );
}
