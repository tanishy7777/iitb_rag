import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { AppShell } from '../components/AppShell';
import {
  asApiError,
  fetchMachines,
  fetchRecentMachines,
  nextTroubleshoot,
  startTroubleshoot,
  submitFeedback,
  type Citation,
  type FlowNode,
  type HistoricalSuggestion,
  type Machine,
  type RecentMachine,
  type TroubleshootingFlow,
} from '../lib/api';

type BusyAction = '' | 'init' | 'diagnosis' | 'flow' | 'feedback';

const TRIAGE_CHIPS = [
  { label: 'Power', text: 'power issue interlock breaker alarm' },
  { label: 'Hydraulics', text: 'vacuum pressure leak gas flow issue' },
  { label: 'Tooling', text: 'recipe alignment wafer process issue' },
];

function topHistorySignals(flow: TroubleshootingFlow): string {
  const snapshot = flow.history_snapshot || {};
  const top = Object.entries(snapshot)
    .filter(([, value]) => Number(value?.count || 0) > 0)
    .slice(0, 3)
    .map(([key, value]) => `${key}:${value.count}`);
  if (!top.length) {
    return 'History signal is limited for this machine.';
  }
  return `History signals used: ${top.join(', ')}`;
}

export function OperatorPage() {
  const navigate = useNavigate();
  const [busyAction, setBusyAction] = useState<BusyAction>('init');
  const [pageError, setPageError] = useState('');

  const [machines, setMachines] = useState<Machine[]>([]);
  const [recentMachines, setRecentMachines] = useState<RecentMachine[]>([]);
  const [machineId, setMachineId] = useState<number>(0);
  const [question, setQuestion] = useState('');
  const [workaround, setWorkaround] = useState('');

  const [sessionId, setSessionId] = useState('');
  const [answer, setAnswer] = useState('No query yet.');
  const [answerMeta, setAnswerMeta] = useState('');
  const [checklist, setChecklist] = useState<string[]>([]);
  const [citations, setCitations] = useState<Citation[]>([]);
  const [history, setHistory] = useState<HistoricalSuggestion[]>([]);

  const [flowMeta, setFlowMeta] = useState('Run diagnosis to generate history-aware routing.');
  const [currentNode, setCurrentNode] = useState<FlowNode | null>(null);
  const [flowLog, setFlowLog] = useState<string[]>([]);

  const [feedbackStatus, setFeedbackStatus] = useState('');

  const flowKind = currentNode?.kind || 'final';
  const isBusy = busyAction !== '';
  const busyText = useMemo(() => {
    if (busyAction === 'init') return 'Loading machine context...';
    if (busyAction === 'diagnosis') return 'Running diagnosis with RAG/LLM...';
    if (busyAction === 'flow') return 'Processing troubleshooting step...';
    if (busyAction === 'feedback') return 'Saving feedback...';
    return '';
  }, [busyAction]);

  function handleAuthError(status: number) {
    if (status === 401) {
      navigate('/login?next=/operator', { replace: true });
      return true;
    }
    if (status === 403) {
      navigate('/operator', { replace: true });
      return true;
    }
    return false;
  }

  async function loadMachinesAndRecent() {
    setBusyAction('init');
    setPageError('');
    try {
      const [machinesPayload, recentPayload] = await Promise.all([fetchMachines(), fetchRecentMachines(8)]);
      const preferred = new Set([1, 3, 7]);
      const sorted = [...(machinesPayload.machines || [])].sort((a, b) => {
        const ap = preferred.has(Number(a.machine_id)) ? 0 : 1;
        const bp = preferred.has(Number(b.machine_id)) ? 0 : 1;
        if (ap !== bp) return ap - bp;
        return Number(a.machine_id) - Number(b.machine_id);
      });
      setMachines(sorted);
      setRecentMachines(recentPayload.recent_machines || []);
      if (!machineId && sorted.length) {
        setMachineId(Number(sorted[0].machine_id));
      }
    } catch (error) {
      const apiError = asApiError(error);
      if (handleAuthError(apiError.status)) return;
      setPageError(apiError.message);
    } finally {
      setBusyAction('');
    }
  }

  async function refreshRecent() {
    try {
      const recentPayload = await fetchRecentMachines(8);
      setRecentMachines(recentPayload.recent_machines || []);
    } catch (error) {
      const apiError = asApiError(error);
      if (handleAuthError(apiError.status)) return;
      setPageError(apiError.message);
    }
  }

  useEffect(() => {
    void loadMachinesAndRecent();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function initializeFlow(flow: TroubleshootingFlow, node: FlowNode | null) {
    const mode = flow.flow_mode || 'deterministic';
    const source = flow.flow_source || 'history_rules';
    const reason = flow.flow_reason ? ` | reason: ${flow.flow_reason}` : '';
    setFlowMeta(`Flow mode: ${mode} (${source}) | ${topHistorySignals(flow)}${reason}`);

    if (!node) {
      setCurrentNode(null);
      setFlowLog([]);
      return;
    }
    setCurrentNode(node);
    setFlowLog([`Start -> ${node.text}`]);
  }

  async function onRunDiagnosis() {
    if (!question.trim()) return;
    if (!machineId) {
      setPageError('Select a machine before diagnosis.');
      return;
    }

    setBusyAction('diagnosis');
    setPageError('');
    try {
      const data = await startTroubleshoot(machineId, question.trim());
      setSessionId(data.session_id);
      setAnswer(data.answer || '');
      setAnswerMeta(
        `Mode: ${data.answer_mode || 'deterministic'} | Confidence: ${data.confidence_label || 'unknown'} (${data.confidence_score || 0})`
      );
      setChecklist(data.checklist || []);
      setCitations(data.citations || []);
      setHistory(data.historical_suggestions || []);
      initializeFlow(data.troubleshooting_flow || { start_node_id: '', nodes: [] }, data.current_node || null);
      setFeedbackStatus(`Session: ${data.session_id}`);
      await refreshRecent();
    } catch (error) {
      const apiError = asApiError(error);
      if (handleAuthError(apiError.status)) return;
      setPageError(apiError.message);
    } finally {
      setBusyAction('');
    }
  }

  async function onFlowStep(responseValue: 'yes' | 'no' | 'done', label: string) {
    if (!sessionId) {
      setPageError('Run diagnosis before traversing flow.');
      return;
    }

    setBusyAction('flow');
    setPageError('');
    try {
      const data = await nextTroubleshoot(sessionId, responseValue);
      const node = data.current_node || null;
      if (!node) {
        setPageError('Flow node not found.');
        return;
      }
      setCurrentNode(node);
      setFlowLog((prev) => [...prev, `${label} -> ${node.text}`]);
      if (data.is_closed) {
        setFeedbackStatus('Troubleshooting flow closed. Please submit fix feedback.');
      }
    } catch (error) {
      const apiError = asApiError(error);
      if (handleAuthError(apiError.status)) return;
      setPageError(apiError.message);
    } finally {
      setBusyAction('');
    }
  }

  async function onFeedback(helpful: boolean) {
    if (!sessionId || !question.trim()) {
      setFeedbackStatus('Run diagnosis before sending feedback.');
      return;
    }
    if (!machineId) {
      setFeedbackStatus('Select a machine first.');
      return;
    }

    setBusyAction('feedback');
    setPageError('');
    try {
      const data = await submitFeedback({
        session_id: sessionId,
        machine_id: machineId,
        issue: question.trim(),
        helpful,
        workaround: workaround.trim(),
      });
      setFeedbackStatus(data.ok ? 'Feedback saved.' : data.error || 'Feedback failed.');
      await refreshRecent();
    } catch (error) {
      const apiError = asApiError(error);
      if (handleAuthError(apiError.status)) return;
      setFeedbackStatus(apiError.message);
    } finally {
      setBusyAction('');
    }
  }

  return (
    <AppShell
      title="Digital Brain - Operator Console"
      subtitle="Machine troubleshooting with manual grounding + historical fixes."
    >
      {pageError ? <p className="error-text">{pageError}</p> : null}

      <section className="card">
        <h2>Recent Machines</h2>
        <ul className="list-clean">
          {recentMachines.length ? (
            recentMachines.map((row, index) => (
              <li key={`${row.session_id || row.machine_id}-${index}`}>
                <button
                  className="btn btn-alt recent-btn"
                  type="button"
                  disabled={isBusy}
                  onClick={() => {
                    setMachineId(Number(row.machine_id || 0));
                    setQuestion(String(row.issue || ''));
                  }}
                >
                  {`${row.machine_id} - ${row.name || 'Unknown'}: ${(row.issue || '').slice(0, 60)}`}
                </button>
              </li>
            ))
          ) : (
            <li>No recent machine sessions yet.</li>
          )}
        </ul>
      </section>

      <section className="card">
        <div className="grid grid-two">
          <div>
            <label htmlFor="machine-select">Machine</label>
            <select
              id="machine-select"
              value={machineId || ''}
              disabled={isBusy}
              onChange={(event) => setMachineId(Number(event.target.value || 0))}
            >
              {machines.map((machine) => (
                <option key={machine.machine_id} value={machine.machine_id}>
                  {`${machine.machine_id} - ${machine.name}`}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="issue-input">Issue</label>
            <input
              id="issue-input"
              value={question}
              placeholder="e.g. vacuum leak and pressure not stable"
              onChange={(event) => setQuestion(event.target.value)}
              disabled={isBusy}
            />
          </div>
        </div>
        <div className="grid grid-three">
          {TRIAGE_CHIPS.map((chip) => (
            <button
              key={chip.label}
              className="btn btn-alt"
              type="button"
              disabled={isBusy}
              onClick={() => setQuestion(chip.text)}
            >
              {chip.label}
            </button>
          ))}
        </div>
        <button className="btn" type="button" disabled={isBusy || !question.trim()} onClick={onRunDiagnosis}>
          Run Diagnosis
        </button>
        {isBusy ? <p className="status-text">{busyText}</p> : null}
      </section>

      <section className="card">
        <h2>Diagnosis Output</h2>
        <p className="status-text">{answerMeta}</p>
        <pre className="mono-block">{answer}</pre>
        <div className="grid grid-two">
          <div>
            <h3>Checklist</h3>
            <ul>
              {checklist.map((item, index) => (
                <li key={`${item}-${index}`}>{item}</li>
              ))}
            </ul>
          </div>
          <div>
            <h3>Citations</h3>
            <ul>
              {citations.map((item, index) => (
                <li key={`${item.path}-${index}`}>{`${item.doc_type}: ${item.path}`}</li>
              ))}
            </ul>
          </div>
        </div>
        <div>
          <h3>Historical Suggestions</h3>
          <ul>
            {history.map((item, index) => (
              <li key={`${item.action}-${index}`}>{`${item.action} (x${item.support_count || 0})`}</li>
            ))}
          </ul>
        </div>
      </section>

      <section className="card">
        <h2>Interactive Troubleshooting Flow</h2>
        <p className="status-text">{flowMeta}</p>
        <pre className="mono-block">{currentNode ? currentNode.text : 'No flow generated yet.'}</pre>

        {flowKind === 'question' ? (
          <div className="grid grid-two">
            <button className="btn btn-good" type="button" disabled={isBusy} onClick={() => onFlowStep('yes', 'Yes')}>
              Yes
            </button>
            <button className="btn btn-bad" type="button" disabled={isBusy} onClick={() => onFlowStep('no', 'No')}>
              No
            </button>
          </div>
        ) : null}

        {flowKind === 'action' ? (
          <button className="btn btn-alt" type="button" disabled={isBusy} onClick={() => onFlowStep('done', 'Completed')}>
            Step Completed
          </button>
        ) : null}

        <div>
          <h3>Traversal Log</h3>
          <ul>
            {flowLog.map((row, index) => (
              <li key={`${row}-${index}`}>{row}</li>
            ))}
          </ul>
        </div>
      </section>

      <section className="card">
        <h2>Did this fix it?</h2>
        <div className="grid grid-two">
          <button className="btn btn-good" type="button" disabled={isBusy} onClick={() => onFeedback(true)}>
            Thumbs Up
          </button>
          <button className="btn btn-bad" type="button" disabled={isBusy} onClick={() => onFeedback(false)}>
            Thumbs Down
          </button>
        </div>
        <label htmlFor="workaround-input">Workaround or actual fix</label>
        <textarea
          id="workaround-input"
          value={workaround}
          placeholder="What actually worked on the floor?"
          onChange={(event) => setWorkaround(event.target.value)}
          disabled={isBusy}
        />
        <p className="status-text">{feedbackStatus}</p>
      </section>
    </AppShell>
  );
}
