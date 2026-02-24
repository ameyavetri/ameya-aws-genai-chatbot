import {
  ExpandableSection,
  Button,
  Link,
  Popover,
  StatusIndicator,
  Tabs,
  Textarea,
} from "@cloudscape-design/components";
import { JsonView, darkStyles } from "react-json-view-lite";
import { RagDocument } from "./types";
import styles from "../../styles/chat.module.scss";

interface ConnectorSource {
  connector_id?: string;
  connector_type?: string;
  connector_name?: string;
  citation_count?: number;
}

interface ConnectorCitation {
  title?: string;
  url?: string;
  source?: string;
}

interface ChatMessageMetadataSectionProps {
  metadata: any; // eslint-disable-line @typescript-eslint/no-explicit-any
  showMetadata: boolean;
  documentIndex: string;
  promptIndex: string;
  setDocumentIndex: (index: string) => void;
  setPromptIndex: (index: string) => void;
}

export function ChatMessageMetadata({
  metadata,
  showMetadata,
  documentIndex,
  promptIndex,
  setDocumentIndex,
  setPromptIndex,
}: ChatMessageMetadataSectionProps) {
  if (!showMetadata) return null;

  return (
    <ExpandableSection variant="footer" headerText="Metadata">
      <JsonView
        shouldInitiallyExpand={(level) => level < 2}
        data={JSON.parse(JSON.stringify(metadata).replace(/\\n/g, "\\\\n"))}
        style={{
          ...darkStyles,
          stringValue: "jsonStrings",
          numberValue: "jsonNumbers",
          booleanValue: "jsonBool",
          nullValue: "jsonNull",
          container: "jsonContainer",
        }}
      />
      {metadata.documents && metadata.documents.length > 0 && (
        <>
          <div className={styles.btn_chabot_metadata_copy}>
            <Popover
              size="medium"
              position="top"
              triggerType="custom"
              dismissButton={false}
              content={
                <StatusIndicator type="success">
                  Copied to clipboard
                </StatusIndicator>
              }
            >
              <Button
                variant="inline-icon"
                iconName="copy"
                onClick={() => {
                  navigator.clipboard.writeText(
                    (metadata.documents as RagDocument[])[
                      parseInt(documentIndex)
                    ].page_content
                  );
                }}
              />
            </Popover>
          </div>
          <Tabs
            tabs={(metadata.documents as RagDocument[]).map(
              (p: RagDocument, i) => ({
                id: `${i}`,
                label:
                  p.metadata.path?.split("/").at(-1) ??
                  p.metadata.title ??
                  p.metadata.document_id.slice(-8),
                href: p.metadata.path,
                content: (
                  <Textarea
                    key={p.metadata.chunk_id}
                    value={p.page_content}
                    readOnly={true}
                    rows={8}
                  />
                ),
              })
            )}
            activeTabId={documentIndex}
            onChange={({ detail }) => setDocumentIndex(detail.activeTabId)}
          />
        </>
      )}
      {metadata.prompts && (
        <>
          <div className={styles.btn_chabot_metadata_copy}>
            <Popover
              size="medium"
              position="top"
              triggerType="custom"
              dismissButton={false}
              content={
                <StatusIndicator type="success">
                  Copied to clipboard
                </StatusIndicator>
              }
            >
              <Button
                variant="inline-icon"
                iconName="copy"
                onClick={() => {
                  navigator.clipboard.writeText(
                    (metadata.prompts as string[][])[parseInt(promptIndex)][0]
                  );
                }}
              />
            </Popover>
          </div>
          <Tabs
            tabs={(metadata.prompts as string[][]).map((p, i) => ({
              id: `${i}`,
              label: `Prompt ${metadata.prompts.length > 1 ? i + 1 : ""}`,
              content: <Textarea value={p[0]} readOnly={true} rows={8} />,
            }))}
            activeTabId={promptIndex}
            onChange={({ detail }) => setPromptIndex(detail.activeTabId)}
          />
        </>
      )}
      {((metadata?.connector_sources as ConnectorSource[] | undefined)?.length ?? 0) >
        0 && (
        <div style={{ marginTop: 12 }}>
          <strong>Sources</strong>
          <ul style={{ marginTop: 4, paddingLeft: 20 }}>
            {(metadata?.connector_sources ?? []).map(
              (s: ConnectorSource, i: number) => (
                <li key={s.connector_id ?? i}>
                  From: {s.connector_name ?? s.connector_type ?? "Connector"}
                  {s.citation_count != null && (
                    <span> ({s.citation_count} reference(s))</span>
                  )}
                </li>
              )
            )}
          </ul>
        </div>
      )}
      {((metadata?.connector_citations as ConnectorCitation[] | undefined)
        ?.length ?? 0) > 0 && (
        <div style={{ marginTop: 12 }}>
          <strong>References</strong>
          <ol style={{ marginTop: 4, paddingLeft: 20 }}>
            {(metadata?.connector_citations ?? []).map(
              (c: ConnectorCitation, i: number) => (
                <li key={i} style={{ marginBottom: 4 }}>
                  {c.url ? (
                    <Link href={c.url} external>
                      {c.title || c.url}
                    </Link>
                  ) : (
                    <span>{c.title || "Reference"}</span>
                  )}
                  {c.source && (
                    <span style={{ color: "var(--color-text-body-secondary)" }}>
                      {" "}
                      — {c.source}
                    </span>
                  )}
                </li>
              )
            )}
          </ol>
        </div>
      )}
    </ExpandableSection>
  );
}
