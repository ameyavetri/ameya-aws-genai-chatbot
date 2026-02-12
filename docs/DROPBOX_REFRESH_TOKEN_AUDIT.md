# Dropbox Connector — Refresh Token Migration Audit

## Task 1: Audit the Current Dropbox Connector Implementation

### 1.1 Credential Schema

**Where is the Dropbox credential JSON schema defined or validated?**
- **`lib/shared/layers/python-sdk/python/genai_core/connectors/connector_files.py`** (lines 64–68, 189–193): Implicit validation via `creds.get("access_token")` — raises `CommonError` if missing.
- **`lib/user-interface/react-app/src/pages/admin/connectors/create-connector-modal.tsx`** (lines 19–25, 305–311): UI hint text and placeholder define expected format.
- **`docs/guide/connector-deploy-and-config.md`** (lines 142–145, 214–224): Docs describe secret shape.
- **`docs/MCP_CONNECTOR_IMPLEMENTATION_PLAN.md`** (line 317): Mentions both formats.

**Current fields expected:**
- `access_token` (required) — short-lived token from Dropbox App Console
- `access_token_v2` — alternate key (used in dropbox-mcp-server only; connector_files uses only `access_token`)

**No formal schema** — validation is ad-hoc in `_list_folder_dropbox` and `_fetch_file_dropbox`.

---

### 1.2 Dropbox Client Initialization

**Where is the Dropbox client instantiated?**
- The codebase does **NOT** use `dropbox.Dropbox()` or the Dropbox Python SDK.
- Raw HTTP via `requests` is used:
  - **`lib/shared/layers/python-sdk/python/genai_core/connectors/connector_files.py`**
    - Line 72: `https://api.dropboxapi.com/2/files/list_folder` (POST)
    - Line 196: `https://content.dropboxapi.com/2/files/download` (POST)
  - Lines 73–74: `headers = {"Authorization": f"Bearer {token}", ...}` — uses `oauth2_access_token` equivalent (Bearer token).
  - No `oauth2_refresh_token=` or `app_key=` — only static `access_token` in header.

---

### 1.3 Connector Registration and Configuration

**Where is the Dropbox connector type registered?**
- **`lib/user-interface/react-app/src/pages/admin/connectors/create-connector-modal.tsx`** (lines 13–17): `CONNECTOR_TYPE_OPTIONS` includes `{ value: "dropbox", label: "Dropbox" }`.
- **`lib/user-interface/react-app/src/pages/rag/add-data/add-connector-files.tsx`** (line 29): `FILE_SOURCE_TYPES = ["dropbox", "sharepoint"]`.
- **`lib/shared/layers/python-sdk/python/genai_core/connectors/connector_files.py`** (lines 57–58, 182–183): Branch on `conn_type == "dropbox"`.
- No connector factory or enum — type is a string in DynamoDB `connector_type` field.

**Where are connector credentials stored?**
- **AWS Secrets Manager**: Credential values (JSON) stored in secrets with prefix `genai-connector-{connector_id}`.
- **DynamoDB** (connectors table): Only `credentials_secret_arn` is stored — references the Secrets Manager secret.
- **`lib/chatbot-api/functions/api-handler/routes/connectors.py`** (lines 60–68, 298–312): `_create_connector_secret` creates secret; connector record stores ARN.

---

### 1.4 Frontend — Connector Creation UI

**Where does the UI collect Dropbox credentials?**
- **`lib/user-interface/react-app/src/pages/admin/connectors/create-connector-modal.tsx`**
  - Line 303: Single `FormField` with `Textarea` for credentials (line 304–313).
  - Line 309: `credentialsJson` state — single JSON string input.
  - Lines 19–25: `CREDENTIALS_HINT["dropbox"]` — describes `access_token` format.
  - Lines 305–311: Placeholder `'{"access_token": "YOUR_DROPBOX_ACCESS_TOKEN"}'` when type is dropbox.
  - Line 56: `buildInput` — passes `credentials` or `credentialsSecretArn` (if ARN) to API.

**Input fields:** One textarea for JSON; no separate fields for `app_key`, `app_secret`, `refresh_token`.

---

### 1.5 API Layer — Connector CRUD

**Where does the API handle connector creation/update?**
- **`lib/chatbot-api/functions/api-handler/routes/connectors.py`**
  - Lines 276–334: `create_connector` resolver
  - Lines 295–306: If `req.credentials` → `_create_connector_secret(connector_id, req.credentials)` → stores ARN in connector.
  - Lines 336–388: `update_connector` — can update via `credentialsSecretArn` or `req.credentials` (calls `_update_connector_secret`).
  - No credential format validation — JSON is stored as-is in Secrets Manager.

**Flow:** Frontend → GraphQL `createConnector` mutation → `connectors.py` → `_create_connector_secret` (boto3 Secrets Manager) → DynamoDB `credentials_secret_arn`.

---

### 1.6 File Listing and Download

**Where is the `list_folder` call made?**
- **`lib/chatbot-api/functions/api-handler/routes/connectors.py`** (lines 482–507): `list_connector_folder` resolver → `connector_files.list_folder()`.
- **`lib/shared/layers/python-sdk/python/genai_core/connectors/connector_files.py`** (lines 40–96): `list_folder` → `_list_folder_dropbox(creds, path)`.
  - Line 66: `token = creds.get("access_token")`
  - Line 76: `resp = requests.post(url, headers=headers, json=body, timeout=30)`
  - Line 80: `requests.RequestException` caught → `CommonError` with message.

**Where is `files_download` called?**
- **`lib/shared/file-import-batch-job/main.py`** (lines 48–53): `connector_files.fetch_file_content()` when `is_connector_import`.
- **`lib/shared/layers/python-sdk/python/genai_core/connectors/connector_files.py`** (lines 165–206): `fetch_file_content` → `_fetch_file_dropbox(creds, file_path)`.
  - Line 191: `token = creds.get("access_token")`
  - Line 204: `requests.RequestException` caught.

**Error handling:** Generic `CommonError`; no specific handling for 401 or `AuthError`.

---

### 1.7 Documentation

**`docs/guide/connector-deploy-and-config.md`**
- Lines 142–145: "Secret shape (JSON): `{ "access_token": "YOUR_DROPBOX_ACCESS_TOKEN" }` or `{ "access_token_v2": "..." }`"
- Lines 214–224: Same; MCP server looks for `access_token` or `access_token_v2`.
- No mention of `app_key`, `app_secret`, `refresh_token`.

**`docs/MCP_CONNECTOR_IMPLEMENTATION_PLAN.md`**
- Line 317: "**Dropbox:** `{\"access_token\": \"...\"}` or `{\"app_key\": \"...\", \"app_secret\": \"...\", \"refresh_token\": \"...\"}` per Dropbox API." — Already mentions new format but not implemented.

**No Dropbox-specific credential setup doc** beyond the above.

---

## Task 2: Proposed Changes for Refresh Token Migration

### Summary

The codebase uses **raw HTTP** (`requests`) to Dropbox API, not the Dropbox SDK. Token refresh must be implemented manually via:
- **Endpoint:** `POST https://api.dropbox.com/oauth2/token`
- **Body (form):** `grant_type=refresh_token`, `refresh_token=...`, `client_id=...` (app_key), `client_secret=...` (app_secret)
- **Response:** `access_token`, `expires_in`, `token_type`

Add a helper `_get_dropbox_access_token(creds)` that:
1. If `refresh_token` + `app_key` + `app_secret` present → call token endpoint, return fresh `access_token`.
2. Else if `access_token` present → return it (log deprecation warning).
3. Else → raise clear error.

Use this token in `_list_folder_dropbox` and `_fetch_file_dropbox`. No new dependencies.

---

## Task 3: Implementation Summary

### Files Changed

| File | Changes |
|------|---------|
| `lib/shared/layers/python-sdk/python/genai_core/connectors/connector_files.py` | Added `_get_dropbox_access_token()`, updated `_list_folder_dropbox` and `_fetch_file_dropbox` to use it; added 401-specific error handling |
| `lib/user-interface/react-app/src/pages/admin/connectors/create-connector-modal.tsx` | Updated `CREDENTIALS_HINT["dropbox"]` and placeholder to show refresh_token format |
| `docs/guide/connector-deploy-and-config.md` | Updated Dropbox credential documentation for both formats |

### Backward Compatibility

- **Existing connectors** using `{"access_token": "..."}` continue to work until the token expires.
- **New connectors** can use `{"app_key": "...", "app_secret": "...", "refresh_token": "..."}` for auto-refresh.
- No API or schema changes; credentials remain stored as JSON in Secrets Manager.

### Dropbox MCP Server (`lib/connectors/dropbox-mcp-server/connector.py`)

The ECS-based MCP server currently has TODO stubs for `list_files` and `get_file_content`. When those are implemented, they should use the same `_get_dropbox_access_token` pattern (or import the helper from genai_core) to support refresh token credentials.

---

## Task 4: Validation Checklist

- [ ] Existing connectors using `access_token` still work (until token expires)
- [ ] New connectors using `refresh_token` format work and auto-refresh
- [ ] `list_folder` call succeeds with new credentials
- [ ] `files_download` (fetch_file_content) succeeds with new credentials
- [ ] Frontend UI accepts both credential formats (JSON paste)
- [ ] Credential validation catches missing fields (e.g., `refresh_token` without `app_key`)
- [ ] Error messages are clear when authentication fails (401)
- [ ] No secrets are logged in plaintext
- [ ] Documentation is updated
