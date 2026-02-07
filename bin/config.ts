import { SupportedRegion, SystemConfig } from "../lib/shared/types";
import { existsSync, readFileSync } from "fs";

/** Default connectors (all disabled). Used when section is missing or for normalization. */
const DEFAULT_CONNECTORS: NonNullable<SystemConfig["connectors"]> = {
  enabled: false,
  vpcId: "",
  azureSql: { enabled: false },
  sharepoint: { enabled: false },
  dropbox: { enabled: false },
};

/** Normalize connectors so missing section is treated as disabled. */
function normalizeConnectors(
  config: SystemConfig
): SystemConfig["connectors"] {
  const c = config.connectors;
  if (!c) return { ...DEFAULT_CONNECTORS };
  return {
    enabled: c.enabled === true,
    vpcId: c.vpcId ?? "",
    azureSql: { enabled: c.azureSql?.enabled === true },
    sharepoint: { enabled: c.sharepoint?.enabled === true },
    dropbox: { enabled: c.dropbox?.enabled === true },
  };
}

const BIN_CONFIG_PATH = "./bin/config.json";
const ROOT_CONFIG_PATH = "./config.json";

export function getConfig(): SystemConfig {
  const configPath = existsSync(BIN_CONFIG_PATH)
    ? BIN_CONFIG_PATH
    : existsSync(ROOT_CONFIG_PATH)
      ? ROOT_CONFIG_PATH
      : null;
  if (configPath) {
    const config = JSON.parse(
      readFileSync(configPath).toString("utf8")
    ) as SystemConfig;
    const connectors = normalizeConnectors(config);
    return { ...config, connectors };
  }
  // Default config
  return {
    prefix: "",
    /* vpc: {
       vpcId: "vpc-00000000000000000",
       createVpcEndpoints: true,
       vpcDefaultSecurityGroup: "sg-00000000000"
    },*/
    privateWebsite: false,
    certificate: "",
    cfGeoRestrictEnable: false,
    cfGeoRestrictList: [],
    bedrock: {
      enabled: true,
      region: SupportedRegion.US_EAST_1,
    },
    llms: {
      // sagemaker: [SupportedSageMakerModels.FalconLite]
      sagemaker: [],
    },
    rag: {
      enabled: false,
      engines: {
        aurora: {
          enabled: false,
        },
        opensearch: {
          enabled: false,
        },
        kendra: {
          enabled: false,
          createIndex: false,
          enterprise: false,
        },
        knowledgeBase: {
          enabled: false,
        },
      },
      embeddingsModels: [
        {
          provider: "sagemaker",
          name: "intfloat/multilingual-e5-large",
          dimensions: 1024,
          default: false,
        },
        {
          provider: "sagemaker",
          name: "sentence-transformers/all-MiniLM-L6-v2",
          dimensions: 384,
          default: false,
        },
        {
          provider: "bedrock",
          name: "amazon.titan-embed-text-v1",
          dimensions: 1536,
        },
        {
          provider: "bedrock",
          name: "amazon.titan-embed-image-v1",
          dimensions: 1024,
        },
        {
          provider: "bedrock",
          name: "cohere.embed-english-v3",
          dimensions: 1024,
        },
        {
          provider: "bedrock",
          name: "cohere.embed-multilingual-v3",
          dimensions: 1024,
          default: true,
        },
        {
          provider: "openai",
          name: "text-embedding-ada-002",
          dimensions: 1536,
          default: false,
        },
      ],
      crossEncodingEnabled: false,
      crossEncoderModels: [
        {
          provider: "sagemaker",
          name: "cross-encoder/ms-marco-MiniLM-L-12-v2",
          default: true,
        },
      ],
    },
    connectors: {
      enabled: false,
      vpcId: "",
      azureSql: { enabled: false },
      sharepoint: { enabled: false },
      dropbox: { enabled: false },
    },
  };
}

export const config: SystemConfig = getConfig();
