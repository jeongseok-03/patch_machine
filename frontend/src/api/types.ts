// All API payload/response types, shared by the domain modules in this directory.

export type OperationsMemory = {
  company_name: string;
  office_project: string;
  active_plan: string;
  organization: string;
  departments: string;
  roles: string;
  key_workflows: string;
  office_tools: string;
  sensitive_policy: string;
};

export type ApiStatus = {
  ok: boolean;
  queue_size: number;
  queue_capacity: number;
  metrics: Record<string, unknown>;
  operations_memory_configured: boolean;
};

export type LlmProviderName = 'vllm' | 'solar' | 'openai' | 'anthropic' | 'gemini' | 'together' | 'fake';

export type LlmRuntimeRoute = 'local' | 'api';

export type LlmTaskRoute = {
  route: LlmRuntimeRoute;
  provider: LlmProviderName;
  model: string;
};

export type LlmRuntime = {
  local_enabled: boolean;
  api_enabled: boolean;
  default_route: LlmRuntimeRoute;
  default_provider: LlmProviderName;
  local_model: string;
  vllm_base_url: string;
  openai_model: string;
  anthropic_model: string;
  gemini_model: string;
  together_model: string;
  solar_model: string;
  task_routes: Record<string, LlmTaskRoute>;
};

export type ChatResponse = {
  answer: string;
  route: LlmRuntimeRoute;
  provider: LlmProviderName;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  ai_job?: AiJobStatus;
  skill_id?: string;
  skill_result?: Record<string, unknown>;
  attachment_notes?: string[];
  used_history?: number;
};

export type LocalLlmStatus = {
  enabled: boolean;
  mode: string;
  state: 'disabled' | 'offline' | 'loading' | 'running' | 'error' | 'unavailable' | string;
  model: string;
  loaded: boolean;
  message: string;
  error: string;
  started_at: string;
  ready_at: string;
};

export type ProgressLog = {
  path: string;
  title: string;
  repo: string;
  source: string;
  external_id: string;
  status: string;
  created: string;
  llm_route: string;
  kind?: string;
  summary?: string;
  id?: string;
  stage_state?: string;
  runnable?: boolean;
  queue_order?: number;
  source_architecture_id?: string;
  notes?: string;
  owner_id?: string;
  owner_name?: string;
  assignee_kind?: string;
  signed_off_by?: string;
  signed_off_at?: string;
  completion_record?: string;
  priority?: string;
};

export type ProgressPayload = {
  current_status_md: string;
  queue_size: number;
  queue_capacity: number;
  recent_logs: ProgressLog[];
};

export type WorkItemsPayload = {
  items: ProgressLog[];
  bottleneck_summary: string;
};

export type WorkMemory = {
  goals: string;
  active_projects: string;
  current_focus: string;
  blockers: string;
  decisions: string;
  risks: string;
  next_actions: string;
  updated_at: string;
};

export type WorkScheduleItem = {
  id: string;
  title: string;
  owner_id: string;
  owner_name: string;
  status: string;
  priority: string;
  start_date: string;
  due_date: string;
  dependencies: string[];
  notes: string;
  source_architecture_id: string;
  queue_order?: number;
  assignee_kind?: string;
  signed_off_by?: string;
  signed_off_at?: string;
  completion_record?: string;
  created_at?: string;
  updated_at?: string;
};

export type ProcessPlanStep = {
  id: string;
  path: string;
  title: string;
  summary?: string;
  status: string;
  stage_state?: string;
  runnable?: boolean;
  queue_order?: number;
  source_architecture_id?: string;
  notes?: string;
  owner_id?: string;
  owner_name?: string;
  assignee_kind?: string;
  signed_off_by?: string;
  signed_off_at?: string;
  priority?: string;
};

export type ProcessPlan = {
  id: string;
  objective: string;
  architecture_path: string;
  status: 'draft' | 'approved' | 'running' | 'paused' | 'completed' | 'cancelled' | string;
  mode: 'manual' | 'auto' | string;
  approved_by: string;
  approved_at: string;
  created_at: string;
  updated_at: string;
  step_total: number;
  step_done: number;
  steps: ProcessPlanStep[];
  plan_markdown: string;
};

export type WorkArchitecture = {
  title: string;
  markdown: string;
  path: string;
  architecture: Record<string, unknown>;
  queue?: WorkScheduleItem[];
  plan?: ProcessPlan;
  ai_job?: AiJobStatus;
};

export type PermanentMemorySource = {
  id: string;
  kind: string;
  path: string;
  title: string;
  excerpt: string;
  updated_at: string;
};

export type ReadableContextSource = PermanentMemorySource & {
  content: string;
  selected: boolean;
  order: number;
  sensitivity: string;
  origin: string;
};

export type ReadableContextBundle = {
  query: string;
  used_sources: ReadableContextSource[];
  volatile_memories: VolatileMemory[];
  estimated_tokens: number;
  warnings: string[];
  markdown: string;
};

export type AiJobStatus = {
  job_id: string;
  task: string;
  status: 'queued' | 'running' | 'succeeded' | 'failed';
  actor: string;
  input_summary: string;
  used_sources: string[];
  result_path: string;
  error: string;
  created_at: string;
  updated_at: string;
};

export type VolatileMemory = {
  scope: 'global' | 'user' | 'session';
  key: string;
  summary: string;
  current_intent: string;
  active_context: string;
  preferences: string;
  open_questions: string[];
  next_actions: string[];
  relevant_sources: string[];
  expires_at: string;
  updated_at: string;
};

export type ConversationRecord = {
  id: string;
  user_id: string;
  role: string;
  content: string;
  provider: string;
  model: string;
  route: string;
  created_at: string;
};

export type DeletionRequest = {
  id: string;
  requester: string;
  target_type: string;
  target_id: string;
  summary: string;
  source_path: string;
  sensitivity: string;
  reason: string;
  status: string;
};

export type AgentPlan = {
  id: string;
  title: string;
  objective: string;
  mode: string;
  status: string;
  steps: Array<Record<string, unknown>>;
  memory_refs: string[];
  schedule_refs: string[];
  plan_markdown_path?: string;
};

export type PatchRun = {
  id: string;
  repo_id: string;
  request: string;
  autonomy_level: string;
  privacy_mode: string;
  target_branch: string;
  status: string;
  risk_level: string;
  created_by: string;
  approved_by: string;
  plan: Record<string, unknown>;
  questions: Array<Record<string, unknown>>;
  artifacts: Record<string, unknown>;
  context: Record<string, unknown>;
  constraints: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type PatchEvent = {
  id: string;
  patch_run_id: string;
  type: string;
  summary: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type PatchArtifactFile = {
  path: string;
  name: string;
  kind: string;
  title: string;
  bytes: number;
  updated_at: string;
  content?: string;
};

export type IssueCluster = {
  id: string;
  title: string;
  summary: string;
  status: string;
  severity: string;
  canonical_issue_ids: string[];
  source_refs: Array<Record<string, unknown>>;
  affected_repos: string[];
  affected_features: string[];
  confidence: number;
  patch_candidates?: PatchCandidate[];
  test_requirements?: TestRequirement[];
};

export type PatchCandidate = {
  id: string;
  cluster_id: string;
  target_repo: string;
  title: string;
  summary: string;
  risk_level: string;
  status: string;
};

export type TestRequirement = {
  id: string;
  patch_candidate_id: string;
  title: string;
  requirement_type: string;
  given: string;
  when: string;
  then: string;
  priority: string;
  status: string;
  source_refs: string[];
};

export type McpToolDescriptor = {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  inputSchema?: Record<string, unknown>;
  required_permission: string;
  server?: string;
};

export type McpResourceDescriptor = {
  uri: string;
  name: string;
  description: string;
  mimeType: string;
};

export type McpPromptDescriptor = {
  name: string;
  description: string;
  arguments: Array<Record<string, unknown>>;
};

export type McpAuditRecord = {
  id: string;
  actor: string;
  mcp_server: string;
  tool_name: string;
  arguments_redacted: Record<string, unknown>;
  result_summary: Record<string, unknown>;
  risk_level: string;
  policy?: Record<string, unknown>;
  guard_findings?: string[];
  approved_by: string;
  created_at: string;
};

export type ContextFirewallDecision = {
  decision: string;
  highest_sensitivity: string;
  sanitized: unknown;
  removed_counts: Record<string, number>;
  blocked_items: string[];
  detectors_triggered: string[];
  audit_id: string;
  redacted_context_hash: string;
  raw_content_stored: boolean;
};

export type ContextFirewallAuditRecord = {
  id: string;
  actor: string;
  agent_run_id: string;
  destination: string;
  task_type: string;
  decision: string;
  highest_sensitivity: string;
  detectors_triggered: string[];
  removed_counts: Record<string, number>;
  blocked_items: string[];
  raw_content_stored: boolean;
  redacted_context_hash: string;
  created_at: string;
};

export type IntegrationStatus = {
  ok: boolean;
  configured: boolean;
  reason: string;
  items: Array<Record<string, unknown>>;
};

export type GitHubConnectorConfig = {
  enabled: boolean;
  allowed_repos: string[];
  trigger_label: string;
  webhook_secret: string;
  app_token: string;
  webhook_secret_present: boolean;
  app_token_present: boolean;
  event_forms: string[];
};

export type DiscordChannelBinding = {
  guild_id: string;
  channel_id: string;
  channel_name: string;
  repo: string;
};

export type DiscordConnectorConfig = {
  enabled: boolean;
  bot_token: string;
  bot_token_present: boolean;
  guild_allowlist: string[];
  channel_bindings: DiscordChannelBinding[];
  command_forms: string[];
};

export type IntegrationConfig = {
  github: GitHubConnectorConfig;
  discord: DiscordConnectorConfig;
};

export type DocumentRead = {
  path: string;
  markdown: string;
  bytes: number;
  modified_at: string;
};

export type ArchiveDocumentListItem = {
  path: string;
  title: string;
  kind: string;
  excerpt: string;
  bytes: number;
  modified_at: string;
};

export type TokenLimit = {
  enforcement_enabled: boolean;
  per_request_max_tokens: number;
  daily_total_tokens: number;
  monthly_total_tokens: number;
};

export type TokenUsageEntry = {
  provider: string;
  model: string;
  task: string;
  actor: string;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  occurred_at: string;
};

export type TokenUsageSummary = {
  daily_total: number;
  monthly_total: number;
  by_provider: Record<string, number>;
  by_task: Record<string, number>;
  by_actor: Record<string, number>;
  recent: TokenUsageEntry[];
};

export type TokenLimitStatus = {
  limits: TokenLimit;
  usage: TokenUsageSummary;
};

export type HiringRequest = {
  role_title: string;
  business_need: string;
  priority: string;
  department_id?: string;
  position_id?: string;
  candidate_name?: string;
  candidate_profile?: string;
  interview_stage?: string;
  include_workload?: boolean;
};

export type GeneratedDocument = {
  title: string;
  markdown: string;
  path: string;
  ai_job?: AiJobStatus;
  output_format?: string;
  attachment_notes?: string[];
};

export type HandoverRequest = {
  work_title: string;
  outgoing_owner: string;
  incoming_owner: string;
  notes: string;
  generate_tasks?: boolean;
};

export type OfficeDocumentOutputFormat = 'auto' | 'markdown' | 'html' | 'csv' | 'json' | 'text';

export type OfficeDocumentRequest = {
  document_type: 'meeting_minutes' | 'report_draft' | 'work_request' | 'ppt_outline';
  title: string;
  source_text: string;
  audience: string;
  source_ids?: string[];
  query?: string;
  source_limit?: number;
  include_volatile?: boolean;
  token_budget?: number;
  attachment_ids?: string[];
  output_format?: OfficeDocumentOutputFormat;
};

export type ApiKeyInfo = {
  provider: string;
  label?: string;
  configured: boolean;
  masked_value: string;
  model: string;
  base_url: string;
  base_url_source?: string;
};

export type ProviderModelPayload = {
  provider: string;
  models: string[];
  source: string;
  refreshed_at: string;
  reason: string;
  configured: boolean;
  requires_api_key: boolean;
};

export type HuggingFaceModelItem = {
  id: string;
  downloads: number;
  likes: number;
  tags: string[];
  pipeline_tag: string;
};

export type HuggingFaceModelSearchResult = {
  query: string;
  models: HuggingFaceModelItem[];
};

export type AuthUser = {
  id: string;
  display_name: string;
  title?: string;
  role_id?: string;
  permissions?: string[];
};

export type AuthSession = {
  token: string;
  user: AuthUser;
};

export type CurrentUser = {
  authenticated: boolean;
  user: AuthUser | null;
};

export type AccountRequest = {
  id: string;
  user_id: string;
  display_name: string;
  title: string;
  status: 'pending' | 'approved' | 'rejected';
  created_at: string;
  decided_at: string;
  decided_by: string;
};

export type RoleRecord = {
  id: string;
  name: string;
  level: number;
  permissions: string[];
};

export type UserRecord = {
  id: string;
  display_name: string;
  title: string;
  role_id: string;
  active: boolean;
  department?: string;
  position_id?: string;
};

export type DepartmentRecord = {
  id: string;
  name: string;
  description?: string;
  lead_user_id?: string;
  parent_id?: string;
};

export type PositionRecord = {
  id: string;
  name: string;
  level: number;
  permissions?: string[];
  display_order?: number;
  restrict_title_assignment?: boolean;
  description?: string;
};

export type DepartmentPermissionRecord = {
  department_id: string;
  position_id: string;
  permissions: string[];
};

export type CompanyProfile = {
  organization_size: string;
  industries: string[];
  departments: string[];
  primary_goals: string[];
  data_sensitivity: string[];
  deployment_preference: string;
  company_name: string;
  office_project: string;
  work_summary: string;
  current_tools: string;
  recurring_workflows: string;
  change_management_needs: string;
  automation_priorities: string;
};

export type PatchNoteRecommendationItem = {
  id?: string;
  name?: string;
  description?: string;
  reason?: string;
  priority?: string;
  enabled?: boolean;
};

export type AccessControlPayload = {
  roles: RoleRecord[];
  users: UserRecord[];
  departments: DepartmentRecord[];
  positions: PositionRecord[];
  department_permissions: DepartmentPermissionRecord[];
  permissions: string[];
};

export type InitialOfficeSetupResult = {
  operations_memory: Record<string, unknown>;
  work_memory: Record<string, unknown>;
  workspace_profile: Record<string, unknown>;
  recommended_package: string;
  agent_packs: PatchNoteRecommendationItem[];
  templates: PatchNoteRecommendationItem[];
  workflows: PatchNoteRecommendationItem[];
  security_defaults: PatchNoteRecommendationItem[];
  integration_priorities: PatchNoteRecommendationItem[];
  llm_task_routes: Record<string, LlmTaskRoute>;
  first_14_days: string[];
  human_review_required: string[];
  roles: RoleRecord[];
  users: UserRecord[];
  notes: string[];
  warnings: string[];
  questions: string[];
  sensitive_hint: boolean;
  ai_job?: AiJobStatus;
};

export type UploadRecord = {
  id: string;
  filename: string;
  path: string;
  description: string;
  tags: string;
  work_title: string;
  uploaded_at: string;
};

export type ChatSendOptions = {
  task?: string;
  attachmentIds?: string[];
  historyLimit?: number;
};

export type ChatStreamHandlers = {
  onMeta?: (meta: { route: string; provider: string; model: string; skill_id: string }) => void;
  onDelta?: (text: string) => void;
  onDone?: (response: ChatResponse) => void;
  onError?: (detail: string) => void;
};

/**
 * Stream a chat completion over SSE. Returns the final ChatResponse (also
 * delivered via onDone). Falls back gracefully if the stream errors.
 */

export type AssignmentScope = {
  can_assign: boolean;
  scope: 'all' | 'department' | 'none';
  level: number;
  department_ids: string[];
  departments: DepartmentRecord[];
  assignable_users: UserRecord[];
};

export type OrgRoster = {
  users: UserRecord[];
  departments: DepartmentRecord[];
  positions: PositionRecord[];
};

export type HrEvaluationRecord = {
  id: string;
  user_id: string;
  period: string;
  work_item_ids: string[];
  draft: string;
  final_text: string;
  evidence: string;
  created_by: string;
  created_at: string;
  document_path?: string;
  source_refs: string[];
};

export type SkillInputSchema = {
  name: string;
  type: string;
  required: boolean;
  description: string;
};

export type SkillDescriptor = {
  id: string;
  name: string;
  description: string;
  category: string;
  executor: 'prompt' | 'tool' | 'cli';
  required_permission: string;
  risk: string;
  tool: string;
  output_format: string;
  inputs: SkillInputSchema[];
};

export type SkillRunResult = {
  skill_id: string;
  executor: string;
  status: string;
  output_text: string;
  output_path: string;
  output_format: string;
  tool_result: Record<string, unknown>;
  notes: string[];
};

export type SkillCreateInput = {
  id: string;
  name: string;
  description?: string;
  instructions?: string;
  category?: string;
  executor?: 'prompt' | 'tool' | 'cli';
  required_permission?: string;
  risk?: string;
  output_format?: string;
  output_folder?: string;
  tool?: string;
  inputs?: SkillInputSchema[];
};
