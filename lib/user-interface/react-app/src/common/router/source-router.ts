// lib/user-interface/react-app/src/common/router/source-router.ts

export type DataSourceMode = "internal" | "web" | "hybrid";

export interface SourceRoutingInput {
  query: string;
  sourceMode: DataSourceMode;
  workspaceId?: string | null;
  userRequestedWeb?: boolean; // optional: if you add a UI toggle like "Allow Internet"
}

export interface SourceRoutingDecision {
  useInternalRag: boolean;
  useWebSearch: boolean;
  reason: string;
}


/**
 * UI-side router (lightweight):
 * - Decides which sources should be used based on user selection
 * - Backend remains source-of-truth for actual retrieval execution
 */
export function decideSources(input: SourceRoutingInput): SourceRoutingDecision {
  const { sourceMode, userRequestedWeb } = input;

  if (sourceMode === "internal") {
    return {
      useInternalRag: true,
      useWebSearch: false,
      reason: "User selected Internal knowledge base",
    };
  }

  if (sourceMode === "web") {
    return {
      useInternalRag: false,
      useWebSearch: true,
      reason: "User selected Internet only",
    };
  }

  // hybrid
  // Optionally respect a “Allow Internet” toggle if you add later.
  const webAllowed = userRequestedWeb ?? true;

  return {
    useInternalRag: true,
    useWebSearch: webAllowed,
    reason: webAllowed
      ? "User selected Hybrid (Internal + Internet)"
      : "User selected Hybrid but web is disabled by user preference",
  };
}

export async function resolveSourceContext({
    sourceMode,
    prompt,
    workspaceId,
  }: {
    sourceMode: "internal" | "web" | "hybrid";
    prompt: string;
    workspaceId?: string;
  }): Promise<string> {
  
    if (sourceMode === "internal") {
      // TODO: Call internal RAG (existing vector DB)
      return await fetchInternalContext(prompt, workspaceId);
    }
  
    if (sourceMode === "web") {
      // TODO: Call web search (future)
      return await fetchWebContext(prompt);
    }
  
    if (sourceMode === "hybrid") {
      const internal = await fetchInternalContext(prompt, workspaceId);
      const web = await fetchWebContext(prompt);
      return `${internal}\n\n${web}`;
    }
  
    return "";
  }  

// --------------------------------------------
// TEMP STUBS — to be replaced with real backend calls
// --------------------------------------------

async function fetchInternalContext(
    prompt: string,
    workspaceId?: string
  ): Promise<string> {
    // TODO: Replace with API call to backend RAG service
    return "";
  }
  
  async function fetchWebContext(
    prompt: string
  ): Promise<string> {
    // TODO: Replace with API call to Web Search service
    return "";
  }
  
