# Negotium Architecture

Negotium is an AI Office BPA system that combines a React console, a FastAPI backend, local/cloud LLM routing, external ingestion, and a Markdown-first archive.

## 1. System Overview

```mermaid
flowchart TB
  User["Users: owner, manager, staff, viewer"] --> Frontend["React Frontend: localhost:5173"]

  Frontend -->|"REST API"| FastAPI["FastAPI Backend: negotium serve"]

  FastAPI --> OperationsAPI["Operations API"]
  FastAPI --> ContributorSite["Contributor Site"]
  FastAPI --> GithubWebhook["GitHub Webhook Router"]
  FastAPI --> DiscordBot["Discord Bot Adapter"]

  OperationsAPI --> AccessControl["AccessControlStore"]
  OperationsAPI --> SecretStore["SecretStore"]
  OperationsAPI --> UploadStore["UploadStore"]
  OperationsAPI --> OperationsMemory["OperationsMemoryStore"]
  OperationsAPI --> LlmRuntime["LlmRuntimeStore"]
  OperationsAPI --> LlmGateway["LLM Gateway"]

  LlmGateway --> LocalVllm["Embedded vLLM: Qwen3-4B"]
  LlmGateway --> Solar["Upstage Solar (default)"]
  LlmGateway --> OpenAI["OpenAI GPT"]
  LlmGateway --> Claude["Anthropic Claude"]
  LlmGateway --> Gemini["Google Gemini"]
  LlmGateway --> FakeLLM["Fake LLM for Tests"]

  FastAPI --> EventBus["EventBus"]
  EventBus --> Orchestrator["Orchestrator"]
  Orchestrator --> AgentGraph["Agent Graph"]
  AgentGraph --> PmAgent["PM Agent"]
  AgentGraph --> DevAgent["Developer Agent"]
  AgentGraph --> ReviewerAgent["Reviewer Agent"]

  PmAgent --> LlmGateway
  DevAgent --> LlmGateway
  ReviewerAgent --> LlmGateway

  OperationsMemory --> Archive["archive directory"]
  LlmRuntime --> Archive
  SecretStore --> Archive
  UploadStore --> Archive
  Orchestrator --> ArchiveWriter["ArchiveWriter"]
  ArchiveWriter --> Archive
```

## 2. Main Request Flow

```mermaid
sequenceDiagram
  participant User as User
  participant UI as React Frontend
  participant API as FastAPI Operations API
  participant Auth as AccessControlStore
  participant Runtime as LlmRuntimeStore
  participant Archive as Archive Memory
  participant Gateway as LlmGateway
  participant VLLM as Embedded vLLM

  User->>UI: Ask a question in LLM Chat
  UI->>API: POST /api/llm/chat with X-NG-User
  API->>Auth: Check llm:chat permission
  Auth-->>API: Allowed
  API->>Runtime: Read route and provider
  API->>Archive: Read company memory, status, recent logs
  API->>Gateway: Send contextual messages
  Gateway->>VLLM: Generate with local model
  VLLM-->>Gateway: Text and token usage
  Gateway-->>API: LlmResponse
  API-->>UI: ChatResponse
  UI-->>User: Render answer
```

## 3. Local vLLM State

```mermaid
stateDiagram-v2
  [*] --> Disabled
  Disabled --> Loading: Local ON
  Loading --> Running: Model loaded on GPU
  Loading --> Error: CUDA or model loading failure
  Running --> Disabled: Local OFF
  Error --> Loading: Local ON retry
  Running --> Running: Chat requests reuse loaded model
```

## 4. LLM Runtime Modes

```mermaid
flowchart TB
  Start["Backend startup"] --> ModeCheck{"NG_VLLM_MODE"}

  ModeCheck -->|"embedded"| HostMode["Host Python process"]
  HostMode --> Spawn["VLLM_WORKER_MULTIPROC_METHOD=spawn"]
  Spawn --> LoadModel["vllm.LLM loads Qwen3-4B on GPU"]
  LoadModel --> Ready["Local LLM running"]

  ModeCheck -->|"http"| HttpMode["External vLLM HTTP server"]
  HttpMode --> BaseURL["NG_VLLM_BASE_URL"]
  BaseURL --> HttpReady["OpenAI-compatible API"]

  Ready --> Chat["LLM Chat"]
  HttpReady --> Chat
```

Recommended local GPU mode:

```bash
NG_LLM_PROVIDER=vllm \
NG_LLM_DEFAULT_ROUTE=local \
NG_VLLM_MODE=embedded \
NG_VLLM_PRELOAD_ON_STARTUP=true \
NG_VLLM_WORKER_MULTIPROC_METHOD=spawn \
uv run negotium serve
```

Docker mode is for the frontend and non-GPU backend operation. It does not load the embedded local GPU model.

## 5. Archive and Persistence

```mermaid
flowchart LR
  Archive["archive/"] --> Memory["operations_memory.json"]
  Archive --> Runtime["llm_runtime.json"]
  Archive --> Secrets["secrets/api_keys.enc.json"]
  Archive --> ACL["access_control.json"]
  Archive --> Uploads["uploads/YYYY/MM/DD/files"]
  Archive --> UploadIndex["uploads/index.json"]
  Archive --> Logs["YYYY/MM/*.md"]
  Archive --> Status["current_status.md"]

  Memory --> Context["LLM Context"]
  Logs --> Context
  Status --> Context
  Uploads --> Context
```

## 6. Office BPA Feature Map

```mermaid
flowchart TB
  Console["AI Office BPA Console"] --> MemoryUI["Company Memory"]
  Console --> ChatUI["LLM Chat"]
  Console --> WorkUI["Work Status"]
  Console --> ProgressUI["Progress Logs"]
  Console --> HiringUI["Hiring and Interview"]
  Console --> DocsUI["Document Automation"]
  Console --> HandoverUI["Handover"]
  Console --> UploadUI["Uploads"]
  Console --> AdminUI["Admin Settings"]
  Console --> AccessUI["Access Control"]

  MemoryUI --> OperationsMemory["operations_memory.json"]
  ChatUI --> LlmGateway["LLM Gateway"]
  WorkUI --> ArchiveLogs["archive logs"]
  ProgressUI --> ArchiveLogs
  HiringUI --> GeneratedDocs["archive/hr"]
  DocsUI --> GeneratedDocs
  HandoverUI --> GeneratedDocs
  UploadUI --> UploadStore["archive/uploads"]
  AdminUI --> SecretStore["encrypted API keys"]
  AccessUI --> AccessControl["roles, users, permissions"]
```

## 7. Event Ingestion and Agent Flow

```mermaid
flowchart LR
  Github["GitHub Issue or Webhook"] --> GithubRouter["GitHubWebhookRouter"]
  Discord["Discord Message"] --> DiscordAdapter["DiscordBotAdapter"]

  GithubRouter --> EventBus["EventBus"]
  DiscordAdapter --> EventBus

  EventBus --> Orchestrator["Orchestrator"]
  Orchestrator --> Context["Repo Snapshot and Archive Context"]
  Context --> AgentGraph["AgentGraph"]

  AgentGraph --> PM["PM Agent: WorkSpec"]
  PM --> Dev["Developer Agent: PatchProposal"]
  Dev --> Reviewer["Reviewer Agent: ReviewVerdict"]
  Reviewer --> ArchiveWriter["ArchiveWriter"]
  ArchiveWriter --> Archive["archive/YYYY/MM/*.md"]
```

## 8. Access Control

```mermaid
flowchart TB
  Request["Frontend request"] --> Header["X-NG-User"]
  Header --> ACL["AccessControlStore"]
  ACL --> User["UserRecord"]
  User --> Role["RoleRecord"]
  Role --> Permission{"Required permission?"}

  Permission -->|"allowed"| Handler["API handler executes"]
  Permission -->|"denied"| Forbidden["403 Forbidden"]

  Handler --> Result["JSON response"]
```

Default roles:

- `owner`: all permissions via `*`
- `manager`: memory, LLM chat, documents, uploads, work read
- `staff`: LLM chat, uploads, work read
- `viewer`: work read only

## 9. Deployment Shape

```mermaid
flowchart TB
  subgraph HostGpu["Host GPU Mode"]
    HostBackend["uv run negotium serve"]
    HostBackend --> EmbeddedVllm["Embedded vLLM on RTX GPU"]
    HostFrontend["npm run dev --prefix frontend"] --> HostBackend
  end

  subgraph DockerMode["Docker Compose Mode"]
    DockerFrontend["frontend container"]
    DockerBackend["negotium container"]
    DockerFrontend --> DockerBackend
    DockerBackend --> CloudProviders["Solar, GPT, Claude, Gemini, or external vLLM HTTP"]
  end
```

Host GPU mode is the recommended mode for sensitive local LLM usage. Docker mode is suitable for web UI, API integration, and cloud-provider workflows.
