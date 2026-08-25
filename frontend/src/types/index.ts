export interface User {
  id: string;
  email: string;
  display_name?: string | null;
  plan: string;
  max_concurrent_tasks: number;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user_id: string;
}

export interface Session {
  id: string;
  title: string | null;
  status: string;
  message_count: number;
  created_at: string;
}

export interface Message {
  id: string;
  role: "USER" | "AGENT" | "SYSTEM";
  content_type: string;
  content: {
    text?: string;
    task_id?: string;
    task_status?: "PENDING" | "RUNNING" | "WAITING_HUMAN" | "PAUSED" | "COMPLETED" | "FAILED" | "CANCELLED";
    summary?: string;
    hitl_question?: string;
    error?: string;
    [key: string]: any;
  };
  task_id: string | null;
  status: "done" | "streaming" | "failed";
  seq: number;
  created_at: string;
}

export interface TaskStep {
  step_index: number;
  type: "THINKING" | "TOOL_CALL" | "TOOL_RESULT" | "HITL_REQUEST" | "FINAL" | "PLAN_GENERATED" | "PLAN_UPDATED";
  content: {
    text?: string;
    tool_name?: string;
    arguments?: Record<string, any>;
    idempotency_key?: string;
    output?: any;
    duration_ms?: number;
    question?: string;
    options?: Array<{ value: string; label: string }>;
    [key: string]: any;
  };
  created_at: string;
}

export interface TaskInfo {
  id: string;
  status: "PENDING" | "RUNNING" | "WAITING_HUMAN" | "PAUSED" | "COMPLETED" | "FAILED" | "CANCELLED";
  title: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  result: Record<string, any> | null;
  error: string | null;
}

export interface HitlRequest {
  id: string;
  task_id: string;
  step_index: number;
  type: string;
  question: string;
  options: Array<{ value: string; label: string }> | null;
  status: string;
  expires_at: string;
}
