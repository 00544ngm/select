export interface StructuredDirection {
  name: string;
  score: number;
  type: string;
  motivation: string;
  motivation_evidence?: string;
  evidence_level: string;
  cost: string;
  strategy: string;
  stickiness: string;
  keywords?: Record<string, string>;
  deep_arguments?: Record<string, unknown>;
  delivery_checklist?: Record<string, unknown>;
  model_version?: string;
  canonical_name?: string;
  primary_relation?: string;
  secondary_relations?: string[];
  purchase_chain?: Record<string, string>;
  lifecycle_stage?: string;
  consistency?: Record<string, { score: number; reason: string }>;
  consumer_simulation?: "A" | "B" | "C" | "D" | string;
  consumer_simulation_reason?: string;
  score_breakdown?: ScoreBreakdown;
  score_inputs?: Record<string, number>;
  raw_score?: number;
  score_cap?: number;
  final_score?: number;
  recommendation_level?: RecommendationLevel | string;
  evidence?: Record<string, unknown>;
  rejected?: boolean;
  rejection_codes?: string[];
  source_fact_ids?: string[];
  invalid_source_fact_ids?: string[];
  incompatibility_reason?: string;
  duplicate_function_reason?: string;
  safety_risk?: string;
  risk_analysis?: string;
  missing_evidence?: string[];
  food_filter_status?: FoodFilterStatus;
  food_filter_reason?: string;
  relation_reasons?: RelationReasons | string[];
  extended_scenarios?: ExtendedScenario[];
  assumptions?: string[];
  confidence_level?: "high" | "medium" | "low" | string;
  stickiness_score?: number;
  market_evidence_status?: MarketEvidenceStatus | string;
  rejection_reason?: string;
  purchase_direction?: "forward_dependency" | "bidirectional" | "reverse_dependency" | "none";
  direction_reason?: string;
  product_type_status?: "food" | "ingestible" | "non_food" | "unknown";
  compatibility_status?: "clear" | "needs_verification" | "blocked";
  duplication_status?: "clear" | "needs_verification" | "blocked";
  safety_status?: "clear" | "needs_verification" | "blocked";
  execution_status?: "pass" | "hold" | "reject";
  hold_reasons?: string[];
  decision_action?: "not_recommended" | "observe" | "needs_evidence" | "small_batch_test" | "priority_test" | "focus_development";
  evidence_records?: Array<Record<string, unknown>>;
  product_type_review?: ProductTypeReview;
}

export type ProductTypeReviewStatus = "confirmed_non_food" | "confirmed_food" | "likely_non_food" | "needs_review";
export interface ProductTypeReviewEvidence { source_field: string; verbatim_quote: string; }
export interface ProductTypeReview {
  status: ProductTypeReviewStatus;
  source?: "rule" | "model" | "fallback";
  confidence?: number;
  role?: string;
  reason?: string;
  reason_zh?: string | null;
  reason_original?: string | null;
  evidence?: ProductTypeReviewEvidence[];
  action?: "continue" | "continue_with_review" | "block";
}

export interface JudgmentBProductMetadata {
  title: string;
  product_id?: string | null;
  product_url?: string | null;
  product_image?: string | null;
}
export interface RejectedBProduct {
  url?: string;
  title?: string;
  review?: ProductTypeReview;
  action?: string;
}

export type EvidenceLevel = "E0" | "E1" | "E2" | "E3" | "E4";
export type RecommendationLevel = "focus" | "test_pool" | "observe" | "not_recommended";
export interface ScoreBreakdown {
  function_necessity?: number;
  usage_continuity?: number;
  purchase_direction?: number;
  scene_fit?: number;
  enhancement_maintenance?: number;
  natural_copurchase?: number;
  relation_strength?: number;
  lifecycle_connection?: number;
  repeat_value?: number;
  function_gain?: number;
  mental_copurchase?: number;
  market_evidence?: number;
  user_scene?: number;
}

export type FoodFilterStatus = "food" | "allowed" | "needs_verification";
export type MarketEvidenceStatus = "已验证" | "部分验证" | "待验证" | string;
export interface RelationReasons {
  function?: string;
  usage?: string;
  scene?: string;
  maintenance?: string;
  mental?: string;
  [key: string]: string | undefined;
}
export interface ExtendedScenario {
  name: string;
  assumption?: string;
  reason?: string;
}

export type ComplementEvidenceStatus =
  | "verified"
  | "signal"
  | "not_found"
  | "insufficient"
  | "analysis_failed";

export interface ComplementEvidenceHit {
  review_index: number;
  original_text: string;
  translation_zh: string;
  keywords: string[];
  reason: string;
  strength: string;
  source_url: string;
}

export interface ComplementEvidenceRecord {
  product_title: string;
  product_url: string;
  platform: string;
  verified_at: string;
  status: ComplementEvidenceStatus;
  analysis_state: "completed" | "failed";
  valid_review_count: number;
  relevant_review_count: number;
  hit_rate: number;
  evidence: ComplementEvidenceHit[];
  failure_reason: string;
}

export interface ComplementEvidencePayload {
  per_b_product: Record<string, ComplementEvidenceRecord>;
}

export type JobMode = "hypothesis" | "judgment" | "batch";
export type JobStatus = "queued" | "running" | "completed" | "failed" | "interrupted";

export type ResultStatus =
  | "completed_with_qualified_candidates"
  | "completed_needs_evidence"
  | "completed_no_qualified_candidates";

export interface ResultReliabilityFields {
  result_status?: ResultStatus;
  result_message?: string;
  raw_direction_count?: number;
  qualified_direction_count?: number;
  hold_direction_count?: number;
  rejected_direction_count?: number;
  rejection_summary?: Record<string, number>;
  audit_performed?: boolean;
  audit_reason?: string;
  initial_raw_direction_count?: number;
  audit_raw_direction_count?: number;
  audit_outcome?: "recovered_candidates" | "confirmed_no_candidates" | string;
  provider?: string;
  provider_model?: string;
}

export interface JobSummary {
  id: string;
  name: string | null;
  mode: JobMode;
  status: JobStatus;
  progress: number;
  error_code: string | null;
  error_message: string | null;
  retry_of_id: string | null;
  created_at: string;
  updated_at: string;
  grade?: string | null;
  score?: number | null;
  product_title?: string | null;
  product_title_zh?: string | null;
  product_id?: string | null;
  product_image?: string | null;
  top_direction_name?: string | null;
  top_direction_keywords?: Record<string, string>;
  top_direction_score?: number | null;
  top_direction_type?: string | null;
  provider?: string | null;
  provider_model?: string | null;
  rotation_enabled?: boolean;
  attempt_count?: number;
  successful_model?: string | null;
}

export interface RotationCandidate {
  provider: ProviderSlug;
  model: string;
  api_protocol: ProviderApiProtocol;
  connection_revision: number;
}

export interface JobAttempt {
  id: string;
  ordinal: number;
  provider: string;
  api_protocol: ProviderApiProtocol;
  model: string;
  status: "running" | "succeeded" | "failed";
  stage: string | null;
  error_code: string | null;
  error_message: string | null;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
}

export interface ModelResult extends ResultReliabilityFields {
  grade?: string;
  grade_reason?: string;
  score?: number;
  score_reason?: string;
  product_title?: string;
  product_title_zh?: string;
  product_id?: string;
  product_url?: string;
  product_images?: string[];
  product_price?: string;
  product_rating?: string;
  product_review_count?: string;
  keyword_pack?: string[];
  mode?: string;
  sections?: Array<{
    title: string;
    content?: string;
    children?: Array<{
      title: string;
      content?: string;
      children?: Array<{ title: string; content: string }>;
    }>;
  }>;
  directions?: string;
  directions_count?: number;
  structured_directions?: StructuredDirection[];
  complement_evidence?: ComplementEvidencePayload;
  model_version?: string;
  product_profile?: Record<string, unknown>;
  product_type_review?: ProductTypeReview;
  rejected_b_products?: RejectedBProduct[];
  b_products?: JudgmentBProductMetadata[];
}

export interface CrossReviewEntry {
  raw?: string;
  error?: string;
}

export interface CrossReviewState {
  status?: "queued" | "running" | "completed" | "failed" | "skipped";
  reviewers?: Array<{ provider: string; display_name?: string; api_protocol?: string; model: string }>;
  results?: Record<string, CrossReviewEntry>;
  error?: string;
}

export interface JobResultPayload extends ResultReliabilityFields {
  mode?: string;
  grade?: string;
  grade_reason?: string;
  score?: number;
  score_reason?: string;
  product_title?: string;
  product_title_zh?: string;
  product_id?: string;
  product_url?: string;
  product_images?: string[];
  product_price?: string;
  product_rating?: string;
  product_review_count?: string;
  keyword_pack?: string[];
  sections?: ModelResult["sections"];
  directions?: string;
  directions_count?: number;
  models?: Record<string, ModelResult>;
  cross_review?: Record<string, CrossReviewEntry> | CrossReviewState;
  structured_directions?: StructuredDirection[];
  complement_evidence?: ComplementEvidencePayload;
  model_version?: string;
  product_profile?: Record<string, unknown>;
  product_type_review?: ProductTypeReview;
  rejected_b_products?: RejectedBProduct[];
  b_products?: JudgmentBProductMetadata[];
}

export interface JobDetail extends JobSummary {
  request_payload: Record<string, unknown>;
  result_payload: JobResultPayload | null;
  rotation?: {
    enabled: boolean;
    candidates: RotationCandidate[];
    snapshot_version?: number;
  } | null;
  attempts?: JobAttempt[];
}

export interface JobListResponse {
  items: JobSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface HypothesisJobCreate {
  name?: string;
  url: string;
  model?: string;
  provider?: string;
  rotation_enabled?: boolean;
  rotation_candidates?: RotationCandidate[];
}

export interface JudgmentJobCreate {
  name?: string;
  a_url: string;
  b_urls: string[];
  model?: string;
  provider?: string;
  rotation_enabled?: boolean;
  rotation_candidates?: RotationCandidate[];
}

export interface BatchJobCreate {
  name?: string;
  urls: string[];
  model?: string;
  provider?: string;
  rotation_enabled?: boolean;
  rotation_candidates?: RotationCandidate[];
}

export interface ApiError {
  code: string;
  message: string;
  retryable: boolean;
}

export interface SearchProduct {
  title: string;
  url: string;
  price: string;
  rating: string;
  review_count: string;
  image: string;
}

export interface SearchResponse {
  results: SearchProduct[];
}

export type ProviderSlug = "openai" | "deepseek" | "custom" | "claude";
export type ProviderRole = "primary" | "secondary";
export type ProviderApiProtocol = "openai" | "anthropic";
export type ProviderModelTestStatus =
  | "discovered"
  | "verified"
  | "unavailable"
  | "temporary_error"
  | "expired";
export type OpenAITransportMode = "chat_completions" | "responses";
export type OpenAIStructuredOutputMode =
  | "json_schema"
  | "json_object"
  | "prompt_json";

export interface ProviderConfiguration {
  slug: ProviderSlug;
  api_protocol: ProviderApiProtocol;
  display_name: string;
  role: ProviderRole;
  base_url: string | null;
  default_model: string;
  supported_models?: string[];
  model_options?: ProviderModelOption[];
  is_enabled: boolean;
  configured: boolean;
  masked_api_key: string | null;
  last_test_status: "untested" | "success" | "failed";
  last_tested_at: string | null;
  last_test_message: string | null;
  updated_at: string | null;
  validation_revision?: number;
}

export interface ProviderModelOption {
  provider: ProviderSlug;
  provider_display_name: string;
  api_protocol: ProviderApiProtocol;
  model: string;
  is_default: boolean;
  is_selected?: boolean;
  is_enabled: boolean;
  test_status: ProviderModelTestStatus;
  tested_at: string | null;
  test_message: string | null;
  error_code?: string | null;
  connection_revision?: number;
  current_connection_revision?: number;
  is_current_connection?: boolean;
  last_used_at?: string | null;
  use_count?: number;
  last_auto_tested_at?: string | null;
  last_acted_by?: string | null;
  last_acted_at?: string | null;
  transport_mode?: OpenAITransportMode | null;
  structured_output_mode?: OpenAIStructuredOutputMode | null;
}

export interface ProviderDraftPayload {
  api_protocol: ProviderApiProtocol;
  display_name?: string;
  base_url?: string;
  default_model: string;
  api_key?: string;
}

export interface ProviderUpdatePayload extends ProviderDraftPayload {
  is_enabled: boolean;
  clear_api_key?: boolean;
}

export interface ProviderTestResult {
  status: "success";
  message: string;
  models: string[];
}

export interface ProviderModelVerifyResult {
  provider: ProviderSlug;
  model: string;
  test_status: ProviderModelTestStatus;
  tested_at: string;
  test_message: string;
  error_code: string | null;
  is_default: boolean;
  transport_mode?: OpenAITransportMode | null;
  structured_output_mode?: OpenAIStructuredOutputMode | null;
}

export interface ProviderModelSelectionResult {
  provider: ProviderSlug;
  model: string;
  is_selected: boolean;
}
