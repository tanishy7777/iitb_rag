export type Role = 'operator' | 'admin';

export type AuthUser = {
  id: number | null;
  username: string;
  role: Role;
};

export type AuthMeResponse = {
  auth_enabled: boolean;
  authenticated: boolean;
  user?: AuthUser;
  expires_at?: string | null;
};

export type ApiError = {
  status: number;
  message: string;
};

export type Machine = {
  machine_id: number;
  name: string;
  category?: string;
  location?: string;
};

export type RecentMachine = {
  machine_id: number;
  name?: string;
  issue?: string;
  session_id?: string;
  created_at?: string;
};

export type Citation = {
  doc_type: string;
  path: string;
  snippet: string;
  score?: number;
};

export type HistoricalSuggestion = {
  action: string;
  support_count: number;
  trace?: string;
};

export type FlowNodeKind = 'question' | 'action' | 'final';

export type FlowNode = {
  id: string;
  kind: FlowNodeKind;
  text: string;
  yes?: string;
  no?: string;
  next?: string;
};

export type TroubleshootingFlow = {
  start_node_id: string;
  nodes: FlowNode[];
  query_terms?: string[];
  history_snapshot?: Record<string, { count: number; support_count: number }>;
  flow_mode?: string;
  flow_source?: string;
  flow_reason?: string;
};

export type StartTroubleshootResponse = {
  session_id: string;
  machine_id: number;
  answer: string;
  answer_mode: string;
  triage: string;
  confidence_score: number;
  confidence_label: string;
  checklist: string[];
  citations: Citation[];
  historical_suggestions: HistoricalSuggestion[];
  troubleshooting_flow: TroubleshootingFlow;
  current_node: FlowNode;
  is_closed: boolean;
};

export type NextTroubleshootResponse = {
  session_id: string;
  machine_id: number;
  current_node: FlowNode;
  is_closed: boolean;
  allowed_responses?: string[];
  message?: string;
};

export type AdminUser = {
  id: number;
  username: string;
  role: Role;
  is_active: boolean;
  created_at?: string;
};

export type AdminUsersResponse = {
  users: AdminUser[];
};

export type AdminUpsertUserPayload = {
  username: string;
  password: string;
  role: Role;
  is_active: boolean;
  upsert?: boolean;
};

export type AdminUpdateUserPayload = {
  user_id: number;
  role?: Role;
  is_active?: boolean;
  password?: string;
};

export type BreakdownByMachine = {
  machine_id: number;
  name?: string;
  count: number;
};

export type BreakdownByCategory = {
  category: string;
  count: number;
};

export type BreakdownByMonth = {
  month_key: string;
  count: number;
};

export type UnresolvedIssue = {
  complaint_id: number;
  machine_id: number;
  name?: string;
  complaint_description?: string;
  time_of_complaint?: string;
};

export type FailedFeedback = {
  session_id?: string;
  machine_id: number;
  name?: string;
  issue?: string;
  workaround?: string;
  created_at?: string;
};

export type FeedbackSummaryRow = {
  machine_id: number;
  helpful_count: number;
  not_helpful_count: number;
};

export type KnowledgeGapRow = {
  keyword: string;
  count: number;
};

export type AdminAnalyticsResponse = {
  top_breakdowns: BreakdownByMachine[];
  category_breakdowns: BreakdownByCategory[];
  monthly_breakdowns: BreakdownByMonth[];
  unresolved_issues: UnresolvedIssue[];
  failed_feedback: FailedFeedback[];
  feedback_summary: FeedbackSummaryRow[];
  knowledge_gaps?: KnowledgeGapRow[];
  applied_filters?: {
    machine_id?: number | null;
    category?: string;
    date_from?: string;
    date_to?: string;
  };
};

export type AdminAnalyticsFilters = {
  machine_id?: number;
  category?: string;
  date_from?: string;
  date_to?: string;
};

async function parseJson<T>(response: Response): Promise<T> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const message =
      typeof payload === 'object' && payload && 'error' in payload
        ? String((payload as { error?: unknown }).error || response.statusText)
        : response.statusText;
    throw { status: response.status, message } satisfies ApiError;
  }

  return payload as T;
}

export async function apiFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    credentials: 'same-origin',
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  });
  return parseJson<T>(response);
}

export async function fetchAuthMe(): Promise<AuthMeResponse> {
  return apiFetch<AuthMeResponse>('/api/auth/me', { method: 'GET' });
}

export async function login(username: string, password: string): Promise<{ ok: boolean; user: AuthUser }> {
  return apiFetch<{ ok: boolean; user: AuthUser }>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
}

export async function logout(): Promise<{ ok: boolean }> {
  return apiFetch<{ ok: boolean }>('/api/auth/logout', {
    method: 'POST',
  });
}

export async function fetchMachines(): Promise<{ machines: Machine[] }> {
  return apiFetch<{ machines: Machine[] }>('/api/machines', { method: 'GET' });
}

export async function fetchRecentMachines(limit = 8): Promise<{ recent_machines: RecentMachine[] }> {
  return apiFetch<{ recent_machines: RecentMachine[] }>(`/api/machines/recent?limit=${limit}`, { method: 'GET' });
}

export async function startTroubleshoot(machineId: number, question: string): Promise<StartTroubleshootResponse> {
  return apiFetch<StartTroubleshootResponse>('/api/troubleshoot/start', {
    method: 'POST',
    body: JSON.stringify({
      machine_id: machineId,
      question,
    }),
  });
}

export async function nextTroubleshoot(sessionId: string, response: 'yes' | 'no' | 'done'): Promise<NextTroubleshootResponse> {
  return apiFetch<NextTroubleshootResponse>('/api/troubleshoot/next', {
    method: 'POST',
    body: JSON.stringify({
      session_id: sessionId,
      response,
    }),
  });
}

export async function submitFeedback(payload: {
  session_id: string;
  machine_id: number;
  issue: string;
  helpful: boolean;
  workaround: string;
}): Promise<{ ok: boolean; error?: string }> {
  return apiFetch<{ ok: boolean; error?: string }>('/api/feedback', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function fetchAdminUsers(): Promise<AdminUsersResponse> {
  return apiFetch<AdminUsersResponse>('/api/admin/users', { method: 'GET' });
}

export async function createOrUpdateAdminUser(payload: AdminUpsertUserPayload): Promise<{ ok: boolean; user: AdminUser }> {
  return apiFetch<{ ok: boolean; user: AdminUser }>('/api/admin/users', {
    method: 'POST',
    body: JSON.stringify({
      ...payload,
      upsert: payload.upsert ?? true,
    }),
  });
}

export async function updateAdminUser(payload: AdminUpdateUserPayload): Promise<{ ok: boolean; user: AdminUser }> {
  return apiFetch<{ ok: boolean; user: AdminUser }>('/api/admin/users/update', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function fetchAdminAnalytics(filters?: AdminAnalyticsFilters): Promise<AdminAnalyticsResponse> {
  const params = new URLSearchParams();
  if (filters?.machine_id) params.set('machine_id', String(filters.machine_id));
  if (filters?.category) params.set('category', filters.category);
  if (filters?.date_from) params.set('date_from', filters.date_from);
  if (filters?.date_to) params.set('date_to', filters.date_to);
  const query = params.toString();
  const path = query ? `/api/admin/analytics?${query}` : '/api/admin/analytics';
  return apiFetch<AdminAnalyticsResponse>(path, { method: 'GET' });
}

export function asApiError(error: unknown): ApiError {
  if (typeof error === 'object' && error && 'status' in error && 'message' in error) {
    const candidate = error as { status?: unknown; message?: unknown };
    return {
      status: Number(candidate.status || 500),
      message: String(candidate.message || 'Unexpected error'),
    };
  }
  return {
    status: 500,
    message: 'Unexpected error',
  };
}
