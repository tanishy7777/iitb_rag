import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import {
  asApiError,
  createOrUpdateAdminUser,
  fetchAdminAnalytics,
  fetchAdminUsers,
  fetchMachines,
  updateAdminUser,
  type AdminAnalyticsFilters,
  type AdminAnalyticsResponse,
  type AdminUser,
  type Machine,
  type Role,
} from '../lib/api';

type Tone = 'blue' | 'teal' | 'amber' | 'red';
type AnalyticsView = 'overview' | 'incidents' | 'knowledge';
type DatePreset = 'all' | '30d' | '90d' | '180d' | '1y';

function compactText(text: string | undefined, maxLen: number): string {
  return String(text || '').replace(/\s+/g, ' ').trim().slice(0, maxLen);
}

function isoDate(value: Date): string {
  return value.toISOString().slice(0, 10);
}

function rangeForPreset(preset: DatePreset): { from: string; to: string } | null {
  if (preset === 'all') return null;
  const end = new Date();
  const start = new Date(end);
  if (preset === '30d') start.setDate(start.getDate() - 30);
  if (preset === '90d') start.setDate(start.getDate() - 90);
  if (preset === '180d') start.setDate(start.getDate() - 180);
  if (preset === '1y') start.setFullYear(start.getFullYear() - 1);
  return { from: isoDate(start), to: isoDate(end) };
}

function MetricTile({ label, value, tone }: { label: string; value: number | string; tone: Tone }) {
  return (
    <div className={`metric-tile tone-${tone}`}>
      <p className="metric-label">{label}</p>
      <p className="metric-value">{value}</p>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return <p className="status-text">{text}</p>;
}

function HorizontalBars({
  rows,
  valueLabel,
}: {
  rows: Array<{ label: string; value: number; sub?: string }>;
  valueLabel: string;
}) {
  const maxValue = Math.max(1, ...rows.map((row) => row.value));
  if (!rows.length) return <EmptyState text="No data." />;

  return (
    <div className="bars-wrap">
      {rows.map((row, index) => {
        const widthPct = Math.max(3, Math.round((row.value / maxValue) * 100));
        return (
          <div className="bar-row" key={`${row.label}-${index}`}>
            <div className="bar-head">
              <span className="bar-label">{row.label}</span>
              <span className="bar-value">{`${row.value} ${valueLabel}`}</span>
            </div>
            {row.sub ? <p className="bar-sub">{row.sub}</p> : null}
            <div className="bar-track">
              <div className={`bar-fill tone-${['blue', 'teal', 'amber', 'red'][index % 4]}`} style={{ width: `${widthPct}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function MonthlyTrend({ rows }: { rows: Array<{ label: string; value: number }> }) {
  if (!rows.length) return <EmptyState text="No monthly trend available." />;

  const points = rows.slice(-8);
  const width = 640;
  const height = 220;
  const padX = 36;
  const padY = 24;
  const innerW = width - padX * 2;
  const innerH = height - padY * 2;
  const maxValue = Math.max(1, ...points.map((p) => p.value));

  const coords = points.map((point, idx) => {
    const x = points.length <= 1 ? width / 2 : padX + (idx * innerW) / (points.length - 1);
    const y = padY + innerH - (point.value / maxValue) * innerH;
    return { ...point, x, y };
  });
  const polyline = coords.map((p) => `${p.x},${p.y}`).join(' ');

  return (
    <div className="trend-wrap">
      <svg viewBox={`0 0 ${width} ${height}`} className="trend-svg" role="img" aria-label="Monthly breakdown trend">
        <defs>
          <linearGradient id="trendArea" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#1d4ed8" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#1d4ed8" stopOpacity="0.04" />
          </linearGradient>
        </defs>
        <line x1={padX} y1={padY + innerH} x2={width - padX} y2={padY + innerH} stroke="#d8e0ea" strokeWidth="1" />
        <line x1={padX} y1={padY} x2={padX} y2={padY + innerH} stroke="#d8e0ea" strokeWidth="1" />
        <polygon
          points={`${coords.map((p) => `${p.x},${p.y}`).join(' ')} ${width - padX},${padY + innerH} ${padX},${padY + innerH}`}
          fill="url(#trendArea)"
        />
        <polyline points={polyline} fill="none" stroke="#1d4ed8" strokeWidth="3" strokeLinecap="round" />
        {coords.map((point) => (
          <g key={`${point.label}-${point.value}`}>
            <circle cx={point.x} cy={point.y} r="4" fill="#0f172a" />
            <text x={point.x} y={point.y - 10} textAnchor="middle" className="trend-point-label">
              {point.value}
            </text>
          </g>
        ))}
      </svg>
      <div className="trend-labels">
        {coords.map((point) => (
          <span key={`m-${point.label}`} className="trend-month">{point.label}</span>
        ))}
      </div>
    </div>
  );
}

function WeightedKeywords({ rows }: { rows: Array<{ keyword: string; count: number }> }) {
  if (!rows.length) return <EmptyState text="No keyword clusters yet." />;

  const maxCount = Math.max(1, ...rows.map((row) => row.count));
  return (
    <div className="keyword-cloud" aria-label="Knowledge gap keyword clusters">
      {rows.map((row, index) => {
        const weight = row.count / maxCount;
        const fontSize = 0.9 + weight * 0.9;
        const padX = 10 + Math.round(weight * 8);
        const toneClass = `tone-${['blue', 'teal', 'amber', 'red'][index % 4]}`;
        return (
          <span
            key={row.keyword}
            className={`keyword-chip ${toneClass}`}
            style={{ fontSize: `${fontSize}rem`, padding: `8px ${padX}px` }}
          >
            {`${row.keyword} (${row.count})`}
          </span>
        );
      })}
    </div>
  );
}

function severityForIssue(text: string): 'high' | 'medium' | 'low' {
  const normalized = text.toLowerCase();
  if (/leak|fail|alarm|error|vacuum|pressure|break|shutdown/.test(normalized)) return 'high';
  if (/unstable|fluctuat|delay|slow|retry|issue/.test(normalized)) return 'medium';
  return 'low';
}

function SeverityBadge({ level }: { level: 'high' | 'medium' | 'low' }) {
  return <span className={`severity-badge severity-${level}`}>{level.toUpperCase()}</span>;
}

function IssueCards({
  rows,
  type,
}: {
  rows: Array<{ title: string; machineLabel: string; detail: string; footer?: string }>;
  type: 'unresolved' | 'risk';
}) {
  if (!rows.length) return <EmptyState text="No issues in this queue." />;

  return (
    <div className="issue-grid">
      {rows.map((row, index) => {
        const severity = severityForIssue(`${row.title} ${row.detail}`);
        return (
          <article className={`issue-card issue-${type}`} key={`${row.title}-${index}`}>
            <div className="issue-head">
              <p className="issue-title">{row.title}</p>
              <SeverityBadge level={severity} />
            </div>
            <p className="issue-machine">{row.machineLabel}</p>
            <p className="issue-detail">{row.detail}</p>
            {row.footer ? <p className="issue-footer">{row.footer}</p> : null}
          </article>
        );
      })}
    </div>
  );
}

function FeedbackStackBars({
  rows,
}: {
  rows: Array<{ machine: string; helpful: number; notHelpful: number }>;
}) {
  if (!rows.length) return <EmptyState text="No feedback summary yet." />;

  return (
    <div className="stacked-wrap">
      {rows.map((row) => {
        const total = Math.max(1, row.helpful + row.notHelpful);
        const helpfulPct = Math.round((row.helpful / total) * 100);
        const notHelpfulPct = 100 - helpfulPct;
        return (
          <div className="stacked-row" key={row.machine}>
            <div className="stacked-meta">
              <span className="stacked-machine">{row.machine}</span>
              <span className="stacked-counts">{`helpful ${row.helpful} / not helpful ${row.notHelpful}`}</span>
            </div>
            <div className="stacked-track" role="img" aria-label={`Feedback split for ${row.machine}`}>
              <div className="stacked-good" style={{ width: `${helpfulPct}%` }} />
              <div className="stacked-bad" style={{ width: `${notHelpfulPct}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function UserRow({
  user,
  disabled,
  onSaved,
  onError,
}: {
  user: AdminUser;
  disabled: boolean;
  onSaved: (username: string) => Promise<void>;
  onError: (message: string) => void;
}) {
  const [role, setRole] = useState<Role>(user.role || 'operator');
  const [isActive, setIsActive] = useState(Boolean(user.is_active));
  const [password, setPassword] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setRole(user.role || 'operator');
    setIsActive(Boolean(user.is_active));
    setPassword('');
  }, [user]);

  async function onSave() {
    setSaving(true);
    onError('');
    try {
      const payload: { user_id: number; role: Role; is_active: boolean; password?: string } = {
        user_id: user.id,
        role,
        is_active: isActive,
      };
      const newPassword = password.trim();
      if (newPassword) payload.password = newPassword;
      const response = await updateAdminUser(payload);
      setPassword('');
      await onSaved(response.user.username || user.username);
    } catch (error) {
      const apiError = asApiError(error);
      onError(apiError.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="user-row-react">
      <div className="meta">{`${user.username} (#${user.id}) | created: ${user.created_at || 'n/a'}`}</div>
      <select value={role} disabled={disabled || saving} onChange={(event) => setRole(event.target.value as Role)}>
        <option value="operator">operator</option>
        <option value="admin">admin</option>
      </select>
      <label className="checkbox-inline">
        <input
          type="checkbox"
          checked={isActive}
          disabled={disabled || saving}
          onChange={(event) => setIsActive(event.target.checked)}
        />
        active
      </label>
      <input
        type="password"
        placeholder="new password (optional)"
        value={password}
        disabled={disabled || saving}
        onChange={(event) => setPassword(event.target.value)}
      />
      <button className="btn btn-alt" type="button" disabled={disabled || saving} onClick={onSave}>
        {saving ? 'Saving...' : 'Save'}
      </button>
    </div>
  );
}

export function AdminPage() {
  const navigate = useNavigate();

  const [users, setUsers] = useState<AdminUser[]>([]);
  const [machines, setMachines] = useState<Machine[]>([]);
  const [analytics, setAnalytics] = useState<AdminAnalyticsResponse | null>(null);

  const [usersLoading, setUsersLoading] = useState(false);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);

  const [usersStatus, setUsersStatus] = useState('');
  const [pageError, setPageError] = useState('');
  const [filtersStatus, setFiltersStatus] = useState('');

  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newRole, setNewRole] = useState<Role>('operator');
  const [newActive, setNewActive] = useState(true);

  const [activeView, setActiveView] = useState<AnalyticsView>('overview');
  const [datePreset, setDatePreset] = useState<DatePreset>('all');
  const [machineFilter, setMachineFilter] = useState<string>('all');
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [customFrom, setCustomFrom] = useState('');
  const [customTo, setCustomTo] = useState('');
  const [appliedFilters, setAppliedFilters] = useState<AdminAnalyticsFilters>({});

  function handleAuthError(status: number): boolean {
    if (status === 401) {
      navigate('/login?next=/admin', { replace: true });
      return true;
    }
    if (status === 403) {
      navigate('/operator', { replace: true });
      return true;
    }
    return false;
  }

  async function refreshUsers() {
    setUsersLoading(true);
    try {
      const data = await fetchAdminUsers();
      setUsers(data.users || []);
    } catch (error) {
      const apiError = asApiError(error);
      if (handleAuthError(apiError.status)) return;
      setPageError(apiError.message);
    } finally {
      setUsersLoading(false);
    }
  }

  async function refreshMachines() {
    try {
      const data = await fetchMachines();
      setMachines(data.machines || []);
    } catch (error) {
      const apiError = asApiError(error);
      if (handleAuthError(apiError.status)) return;
      setPageError(apiError.message);
    }
  }

  async function refreshAnalytics(filters?: AdminAnalyticsFilters) {
    setAnalyticsLoading(true);
    try {
      const data = await fetchAdminAnalytics(filters);
      setAnalytics(data);
    } catch (error) {
      const apiError = asApiError(error);
      if (handleAuthError(apiError.status)) return;
      setPageError(apiError.message);
    } finally {
      setAnalyticsLoading(false);
    }
  }

  async function refreshAll() {
    setPageError('');
    await Promise.all([refreshUsers(), refreshMachines(), refreshAnalytics(appliedFilters)]);
  }

  useEffect(() => {
    void refreshAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onCreateOrUpdateUser() {
    const username = newUsername.trim();
    if (!username || !newPassword) {
      setUsersStatus('Username and password are required.');
      return;
    }

    setUsersStatus('Saving user...');
    setPageError('');
    try {
      const data = await createOrUpdateAdminUser({
        username,
        password: newPassword,
        role: newRole,
        is_active: newActive,
        upsert: true,
      });
      setNewPassword('');
      setUsersStatus(`User ${data.user.username} saved.`);
      await refreshUsers();
    } catch (error) {
      const apiError = asApiError(error);
      if (handleAuthError(apiError.status)) return;
      setUsersStatus(apiError.message);
    }
  }

  function buildFiltersFromControls(): AdminAnalyticsFilters | null {
    const next: AdminAnalyticsFilters = {};

    if (machineFilter !== 'all') {
      const parsed = Number(machineFilter);
      if (parsed > 0) next.machine_id = parsed;
    }

    if (categoryFilter !== 'all') {
      next.category = categoryFilter;
    }

    const fromManual = customFrom.trim();
    const toManual = customTo.trim();
    if (fromManual || toManual) {
      if (fromManual) next.date_from = fromManual;
      if (toManual) next.date_to = toManual;
    } else {
      const presetRange = rangeForPreset(datePreset);
      if (presetRange) {
        next.date_from = presetRange.from;
        next.date_to = presetRange.to;
      }
    }

    if (next.date_from && next.date_to && next.date_from > next.date_to) {
      setFiltersStatus('Invalid date range: From date must be earlier than To date.');
      return null;
    }

    return next;
  }

  async function applyFilters() {
    const next = buildFiltersFromControls();
    if (next === null) return;

    setFiltersStatus('Applying filters...');
    setAppliedFilters(next);
    await refreshAnalytics(next);
    setFiltersStatus('Filters applied.');
  }

  async function resetFilters() {
    setDatePreset('all');
    setMachineFilter('all');
    setCategoryFilter('all');
    setCustomFrom('');
    setCustomTo('');
    setAppliedFilters({});
    setFiltersStatus('Filters reset.');
    await refreshAnalytics({});
  }

  const machineLookup = useMemo(() => {
    const out = new Map<number, Machine>();
    machines.forEach((m) => out.set(Number(m.machine_id), m));
    return out;
  }, [machines]);

  const categoryOptions = useMemo(() => {
    return Array.from(new Set(machines.map((m) => String(m.category || '').trim()).filter((v) => v))).sort((a, b) =>
      a.localeCompare(b)
    );
  }, [machines]);

  const activeFilterChips = useMemo(() => {
    const chips: string[] = [];
    if (appliedFilters.machine_id) {
      const machine = machineLookup.get(appliedFilters.machine_id);
      chips.push(`Machine: ${machine ? `${machine.machine_id} - ${machine.name}` : appliedFilters.machine_id}`);
    }
    if (appliedFilters.category) chips.push(`Category: ${appliedFilters.category}`);
    if (appliedFilters.date_from || appliedFilters.date_to) {
      chips.push(`Date: ${appliedFilters.date_from || '...'} to ${appliedFilters.date_to || '...'}`);
    }
    return chips;
  }, [appliedFilters.category, appliedFilters.date_from, appliedFilters.date_to, appliedFilters.machine_id, machineLookup]);

  const topBreakdowns = analytics?.top_breakdowns || [];
  const categoryBreakdowns = analytics?.category_breakdowns || [];
  const monthlyBreakdowns = [...(analytics?.monthly_breakdowns || [])].reverse();
  const unresolved = (analytics?.unresolved_issues || []).slice(0, 12);
  const failedFeedback = (analytics?.failed_feedback || []).slice(0, 12);
  const knowledgeGaps = analytics?.knowledge_gaps || [];
  const feedbackSummary = analytics?.feedback_summary || [];

  const dashboardLoading = analyticsLoading && !analytics;
  const kpis = useMemo(
    () => ({
      unresolved: unresolved.length,
      atRisk: failedFeedback.length,
      machines: topBreakdowns.length,
      keywords: knowledgeGaps.length,
    }),
    [failedFeedback.length, knowledgeGaps.length, topBreakdowns.length, unresolved.length]
  );

  return (
    <AppShell
      title="Digital Brain - Admin Dashboard"
      subtitle="Most frequent breakdowns, unresolved issues, and operator feedback signal."
    >
      {pageError ? <p className="error-text">{pageError}</p> : null}

      <section className="card">
        <button className="btn btn-alt" type="button" onClick={refreshAll} disabled={usersLoading || analyticsLoading}>
          {usersLoading || analyticsLoading ? 'Refreshing...' : 'Refresh All'}
        </button>
      </section>

      <section className="card">
        <h2>User Access Management</h2>
        <div className="grid grid-two">
          <div>
            <label htmlFor="new-user-name">Username</label>
            <input
              id="new-user-name"
              placeholder="operator1"
              value={newUsername}
              onChange={(event) => setNewUsername(event.target.value)}
            />
          </div>
          <div>
            <label htmlFor="new-user-password">Password</label>
            <input
              id="new-user-password"
              type="password"
              placeholder="Set initial password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
            />
          </div>
        </div>

        <div className="grid grid-two">
          <div>
            <label htmlFor="new-user-role">Role</label>
            <select id="new-user-role" value={newRole} onChange={(event) => setNewRole(event.target.value as Role)}>
              <option value="operator">operator</option>
              <option value="admin">admin</option>
            </select>
          </div>
          <div>
            <label className="checkbox-inline checkbox-inline-gap">
              <input type="checkbox" checked={newActive} onChange={(event) => setNewActive(event.target.checked)} />
              Active user
            </label>
          </div>
        </div>

        <div className="grid grid-two">
          <button className="btn" type="button" onClick={onCreateOrUpdateUser}>
            Create or Update User
          </button>
          <button className="btn btn-alt" type="button" onClick={refreshUsers} disabled={usersLoading}>
            {usersLoading ? 'Refreshing users...' : 'Refresh Users'}
          </button>
        </div>

        <p className="status-text">{usersStatus}</p>

        <div className="users-panel-react">
          {users.length ? (
            users.map((user) => (
              <UserRow
                key={user.id}
                user={user}
                disabled={usersLoading}
                onSaved={async (username) => {
                  setUsersStatus(`Updated user ${username}.`);
                  await refreshUsers();
                }}
                onError={setUsersStatus}
              />
            ))
          ) : (
            <p className="status-text">No users found.</p>
          )}
        </div>
      </section>

      <section className="card analytics-workspace">
        <div className="filter-sticky">
          <div className="filter-grid">
            <div>
              <label htmlFor="filter-window">Date Window</label>
              <select id="filter-window" value={datePreset} onChange={(event) => setDatePreset(event.target.value as DatePreset)}>
                <option value="all">All time</option>
                <option value="30d">Last 30 days</option>
                <option value="90d">Last 90 days</option>
                <option value="180d">Last 180 days</option>
                <option value="1y">Last 1 year</option>
              </select>
            </div>
            <div>
              <label htmlFor="filter-machine">Machine</label>
              <select id="filter-machine" value={machineFilter} onChange={(event) => setMachineFilter(event.target.value)}>
                <option value="all">All machines</option>
                {machines.map((machine) => (
                  <option key={machine.machine_id} value={String(machine.machine_id)}>{`${machine.machine_id} - ${machine.name}`}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="filter-category">Category</label>
              <select id="filter-category" value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}>
                <option value="all">All categories</option>
                {categoryOptions.map((category) => (
                  <option key={category} value={category}>{category}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="filter-date-from">Custom From</label>
              <input
                id="filter-date-from"
                type="date"
                value={customFrom}
                onChange={(event) => setCustomFrom(event.target.value)}
              />
            </div>
            <div>
              <label htmlFor="filter-date-to">Custom To</label>
              <input id="filter-date-to" type="date" value={customTo} onChange={(event) => setCustomTo(event.target.value)} />
            </div>
            <div className="filter-actions">
              <button className="btn" type="button" onClick={applyFilters} disabled={analyticsLoading}>
                {analyticsLoading ? 'Applying...' : 'Apply'}
              </button>
              <button className="tab-btn" type="button" onClick={resetFilters} disabled={analyticsLoading}>
                Reset
              </button>
            </div>
          </div>

          <div className="filter-chips-wrap">
            {activeFilterChips.length ? (
              activeFilterChips.map((chip) => (
                <span className="filter-chip" key={chip}>{chip}</span>
              ))
            ) : (
              <span className="filter-chip neutral">No filters: showing all data</span>
            )}
          </div>
          <p className="status-text">{filtersStatus}</p>
        </div>

        <div className="view-tabs" role="tablist" aria-label="Analytics views">
          <button className={`tab-btn ${activeView === 'overview' ? 'active' : ''}`} onClick={() => setActiveView('overview')}>
            Overview
          </button>
          <button className={`tab-btn ${activeView === 'incidents' ? 'active' : ''}`} onClick={() => setActiveView('incidents')}>
            Incidents
          </button>
          <button className={`tab-btn ${activeView === 'knowledge' ? 'active' : ''}`} onClick={() => setActiveView('knowledge')}>
            Knowledge
          </button>
        </div>

        {dashboardLoading ? <p className="status-text">Loading dashboard...</p> : null}

        {activeView === 'overview' ? (
          <div className="analytics-grid">
            <section className="card analytics-panel analytics-wide">
              <h2>Operations Signal</h2>
              <div className="metric-grid">
                <MetricTile label="Unresolved Issues" value={kpis.unresolved} tone="red" />
                <MetricTile label="At-Risk Feedback" value={kpis.atRisk} tone="amber" />
                <MetricTile label="Machines in Top Failures" value={kpis.machines} tone="blue" />
                <MetricTile label="Knowledge Keywords" value={kpis.keywords} tone="teal" />
              </div>
            </section>

            <section className="card analytics-panel">
              <h2>Top Breakdown Machines</h2>
              <HorizontalBars
                rows={topBreakdowns.map((row) => ({
                  label: row.name || `Machine ${row.machine_id}`,
                  sub: `Machine ID ${row.machine_id}`,
                  value: Number(row.count || 0),
                }))}
                valueLabel="complaints"
              />
            </section>

            <section className="card analytics-panel">
              <h2>Monthly Breakdown Trend</h2>
              <MonthlyTrend
                rows={monthlyBreakdowns.map((row) => ({
                  label: row.month_key,
                  value: Number(row.count || 0),
                }))}
              />
            </section>
          </div>
        ) : null}

        {activeView === 'incidents' ? (
          <div className="analytics-grid">
            <section className="card analytics-panel analytics-wide">
              <h2>Knowledge Gaps (Unresolved Issues)</h2>
              <IssueCards
                type="unresolved"
                rows={unresolved.map((row) => ({
                  title: `Complaint #${row.complaint_id}`,
                  machineLabel: `${row.name || 'Unknown'} | Machine ${row.machine_id}`,
                  detail: compactText(row.complaint_description, 180),
                  footer: row.time_of_complaint ? `Reported: ${row.time_of_complaint}` : '',
                }))}
              />
            </section>

            <section className="card analytics-panel analytics-wide">
              <h2>At-Risk Queue (Failed Feedback)</h2>
              <IssueCards
                type="risk"
                rows={failedFeedback.map((row) => ({
                  title: compactText(row.issue, 120) || 'Issue not captured',
                  machineLabel: `${row.name || 'Unknown'} | Machine ${row.machine_id}`,
                  detail: compactText(row.workaround, 140) || 'No workaround submitted.',
                  footer: row.created_at ? `Feedback at ${row.created_at}` : '',
                }))}
              />
            </section>
          </div>
        ) : null}

        {activeView === 'knowledge' ? (
          <div className="analytics-grid">
            <section className="card analytics-panel">
              <h2>Breakdowns by Category</h2>
              <HorizontalBars
                rows={categoryBreakdowns.map((row) => ({
                  label: row.category || 'uncategorized',
                  value: Number(row.count || 0),
                }))}
                valueLabel="events"
              />
            </section>

            <section className="card analytics-panel">
              <h2>Knowledge Gap Clusters</h2>
              <WeightedKeywords rows={knowledgeGaps.map((row) => ({ keyword: row.keyword, count: row.count }))} />
            </section>

            <section className="card analytics-panel analytics-wide">
              <h2>Feedback Summary</h2>
              <FeedbackStackBars
                rows={feedbackSummary.map((row) => ({
                  machine: `Machine ${row.machine_id}`,
                  helpful: Number(row.helpful_count || 0),
                  notHelpful: Number(row.not_helpful_count || 0),
                }))}
              />
            </section>
          </div>
        ) : null}
      </section>
    </AppShell>
  );
}
