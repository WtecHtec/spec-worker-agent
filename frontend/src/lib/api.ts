const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface RequestOptions extends RequestInit {
  token?: string | null;
}

export class ApiError extends Error {
  code: string;
  status: number;
  details?: any;

  constructor(message: string, code: string = "API_ERROR", status: number = 500, details?: any) {
    super(message);
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

export async function apiRequest<T = any>(
  endpoint: string,
  options: RequestOptions = {}
): Promise<T> {
  const { token, headers = {}, ...rest } = options;

  const requestHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    ...(headers as Record<string, string>),
  };

  if (token) {
    requestHeaders["Authorization"] = `Bearer ${token}`;
  }

  const url = endpoint.startsWith("http") ? endpoint : `${API_BASE}${endpoint}`;

  const response = await fetch(url, {
    headers: requestHeaders,
    ...rest,
  });

  const contentType = response.headers.get("content-type");
  let data: any = null;

  if (contentType && contentType.includes("application/json")) {
    data = await response.json();
  } else {
    data = await response.text();
  }

  if (!response.ok) {
    // 401 自动清理并登出
    if (response.status === 401 && typeof window !== "undefined") {
      localStorage.removeItem("agent_token");
      localStorage.removeItem("agent_email");
      localStorage.removeItem("agent_user_id");
      // 动态触发全局认证变更事件
      window.dispatchEvent(new Event("agent_auth_expired"));
    }

    const retryAfter = response.headers.get("retry-after");
    const errorMsg = data?.message || data?.detail || response.statusText || "Request failed";
    const errorCode = data?.code || `HTTP_${response.status}`;

    const errorDetails = {
      ...data?.details,
      retryAfterSeconds: retryAfter ? parseInt(retryAfter, 10) : undefined,
    };

    throw new ApiError(errorMsg, errorCode, response.status, errorDetails);
  }

  return data as T;
}

export const api = {
  // Auth
  register: (data: { email: string; password: string; display_name?: string }) =>
    apiRequest("/auth/register", { method: "POST", body: JSON.stringify(data) }),

  login: (data: { email: string; password: string }) =>
    apiRequest("/auth/login", { method: "POST", body: JSON.stringify(data) }),

  // Sessions
  getSessions: (token: string) =>
    apiRequest("/sessions", { token }),

  createSession: (title: string, token: string) =>
    apiRequest("/sessions", { method: "POST", body: JSON.stringify({ title }), token }),

  getSessionMessages: (sessionId: string, token: string, afterSeq: number = 0) =>
    apiRequest(`/sessions/${sessionId}/messages?after_seq=${afterSeq}`, { token }),

  sendMessage: (sessionId: string, content: string, token: string) =>
    apiRequest(`/sessions/${sessionId}/messages`, {
      method: "POST",
      body: JSON.stringify({ content }),
      token,
    }),

  // Tasks
  getTask: (taskId: string, token: string) =>
    apiRequest(`/tasks/${taskId}`, { token }),

  getTaskSteps: (taskId: string, token: string, afterStep: number = 0) =>
    apiRequest(`/tasks/${taskId}/steps?after_step=${afterStep}`, { token }),

  cancelTask: (taskId: string, token: string) =>
    apiRequest(`/tasks/${taskId}/cancel`, { method: "POST", token }),

  // HITL
  getPendingHitl: (taskId: string, token: string) =>
    apiRequest(`/tasks/${taskId}/hitl/pending`, { token }),

  respondHitl: (taskId: string, hitlId: string, decision: string, token: string, userInput?: any) =>
    apiRequest(`/tasks/${taskId}/hitl/${hitlId}/respond`, {
      method: "POST",
      body: JSON.stringify({ decision, user_input: userInput }),
      token,
    }),

  // SSE Stream URL generator (携带 token 参数以适配标准 EventSource 鉴权)
  getStreamUrl: (taskId: string, fromStep: number = 0, token?: string | null) => {
    const url = `${API_BASE}/tasks/${taskId}/stream?from_step=${fromStep}`;
    return token ? `${url}&token=${encodeURIComponent(token)}` : url;
  },

  // Files
  getSessionFiles: (sessionId: string, token: string, category?: string) => {
    const query = category && category !== "all" ? `?category=${category}` : "";
    return apiRequest<{ total: number; items: any[] }>(`/sessions/${sessionId}/files${query}`, { token });
  },

  deleteFile: (sessionId: string, fileId: string, token: string) =>
    apiRequest(`/sessions/${sessionId}/files/${fileId}`, { method: "DELETE", token }),

  getFilePreviewUrl: (sessionId: string, fileId: string, token?: string | null, customHost?: string) => {
    const base = customHost ? customHost.replace(/\/+$/, "") : API_BASE;
    const url = `${base}/sessions/${sessionId}/files/${fileId}/preview`;
    return token ? `${url}?token=${encodeURIComponent(token)}` : url;
  },

  getFileDownloadUrl: (sessionId: string, fileId: string, token?: string | null, customHost?: string) => {
    const base = customHost ? customHost.replace(/\/+$/, "") : API_BASE;
    const url = `${base}/sessions/${sessionId}/files/${fileId}/download`;
    return token ? `${url}?token=${encodeURIComponent(token)}` : url;
  },
};
