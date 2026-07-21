export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };

export type StageRunStatus = "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "WAITING_USER";

export type StageName =
  | "INTAKE"
  | "DIRECTIONS"
  | "LOGO"
  | "IP";

export type AnswerType = "TEXT" | "TEXT_LIST" | "SINGLE_CHOICE" | "MULTI_CHOICE";

export type StructuredFields = {
  industry?: string;
  brand_background?: string;
  target_audiences?: string[];
  price_positioning?: string;
  brand_personality?: string[];
  style_keywords?: string[];
  required_elements?: string[];
  prohibited_elements?: string[];
  competitor_notes?: string;
  slogan?: string;
  language?: string;
};

export type ProjectCreateRequest = {
  name: string;
  requirement_text: string | null;
  structured_fields: StructuredFields;
  reference_artifact_ids: string[];
};

export type ProjectResponse = {
  id: string;
  workspace_id: string;
  name: string;
  current_stage: StageName | string;
  status: string;
  version: number;
  created_at: string;
  updated_at: string;
};

export type StageRunResponse = {
  id: string;
  project_id: string;
  stage: StageName | string;
  status: StageRunStatus;
  attempt: number;
  error_code: string | null;
  result_version_id: string | null;
};

export type ProjectCreateResponse = {
  project: ProjectResponse;
  stage_run: StageRunResponse;
};

export type ProjectDetailResponse = ProjectResponse & {
  brand_spec: Record<string, JsonValue>;
  stage_runs: StageRunResponse[];
};

export type StageRunStateResponse = StageRunResponse & {
  parent_stage_run_id: string | null;
  workflow_thread_id: string;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type StageVersionStateResponse = {
  id: string;
  project_id: string;
  stage_run_id: string;
  stage: StageName | string;
  version_no: number;
  schema_version: number;
  input_refs: Record<string, JsonValue>;
  output: Record<string, JsonValue>;
  status: "GENERATED" | "STALE" | string;
  created_at: string;
};

export type DecisionStateResponse = {
  id: string;
  project_id: string;
  stage: StageName | string;
  action: string;
  source_version_id: string;
  selected_item_id: string | null;
  resulting_stage_run_id: string;
  created_by: string;
  payload: Record<string, JsonValue>;
  created_at: string;
};

export type ProjectStateResponse = {
  project: ProjectResponse;
  brand_spec: Record<string, JsonValue>;
  current_stage: StageName | string;
  stage_runs: Record<string, StageRunStateResponse>;
  versions: Record<string, StageVersionStateResponse>;
  decisions: DecisionStateResponse[];
};

export type IntakeQuestion = {
  id: string;
  field_path: string;
  prompt: string;
  reason: string;
  required: boolean;
  answer_type: AnswerType;
  options: string[];
};

export type IntakeSuggestion = {
  field_path: string;
  value: JsonValue;
  reason: string;
};

export type IntakeConflict = {
  code: string;
  field_paths: string[];
  message: string;
};

export type IntakeResult = {
  schema_version: number;
  ready: boolean;
  questions: IntakeQuestion[];
  brand_spec_patch: Record<string, JsonValue>;
  suggestions: IntakeSuggestion[];
  conflicts: IntakeConflict[];
};

export type DirectionBrief = {
  positioning: string;
  audience_insight: string;
  brand_promise: string;
  tone: string;
};

export type DirectionsResult = {
  schema_version: number;
  brief: DirectionBrief;
  directions: Array<{
    id: string;
    name: string;
    concept: string;
    preview_asset_id: string;
  }>;
};

export type StageRunDetailResponse = StageRunResponse & {
  error_message: string | null;
  result: IntakeResult | DirectionsResult | Record<string, JsonValue> | null;
};

export type IntakeAnswer = {
  field_path: string;
  value: JsonValue;
};

export type IntakeAnswersRequest = {
  answers: IntakeAnswer[];
};

export type ResumeStageRunResponse = {
  id: string;
  parent_stage_run_id: string | null;
  workflow_thread_id: string;
  project_id: string;
  stage: StageName | string;
  status: StageRunStatus;
};

export type StageDecisionRequest =
  | {
      action: "SELECT_VERSION";
      version_id: string;
      selected_item_id: string;
    }
  | {
      action: "CONFIRM_VERSION";
      version_id: string;
      confirmed: true;
    };

export type StageDecisionResponse = {
  decision: DecisionStateResponse;
  stage_run: StageRunStateResponse;
};

export type StageControlResponse = {
  project_id: string;
  stage: StageName | string;
  action: "REDO" | "SKIP" | "GENERATE";
  status: string;
};

export type ApiProblem = {
  detail?: JsonValue;
};
