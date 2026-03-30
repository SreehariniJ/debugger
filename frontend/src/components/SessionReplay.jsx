import React, { useState, useEffect } from 'react';
import { History, FileText, Download, Play, Clock3, CheckCircle2, AlertTriangle, Loader } from 'lucide-react';
import { fetchJson } from '../lib/api';

const API = import.meta.env.VITE_API_URL || (window.location.port.startsWith('517') ? 'http://127.0.0.1:8001' : '')

export const SessionReplay = React.memo(({ sessionId }) => {
    const [session, setSession] = useState(null);
    const [loading, setLoading] = useState(false);
    const [report, setReport] = useState(null);
    const [showReport, setShowReport] = useState(false);

    useEffect(() => {
        if (!sessionId) return;
        const loadSession = async () => {
            setLoading(true);
            try {
                const data = await fetchJson(`${API}/sessions/${sessionId}`);
                setSession(data);
            } catch (e) {
                console.error("Failed to load session", e);
            } finally {
                setLoading(false);
            }
        };
        loadSession();
    }, [sessionId]);

    const loadReport = async () => {
        try {
            const data = await fetchJson(`${API}/sessions/${sessionId}/report`);
            setReport(data.markdown);
            setShowReport(true);
        } catch (e) {
            console.error("Failed to load report", e);
        }
    };

    if (loading) return <div className="card glass shimmer" style={{ height: '200px' }} />;
    if (!session) return null;

    return (
        <div className="card glass">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <History size={18} color="var(--accent)" />
                    <h4 style={{ fontSize: '0.85rem', fontWeight: 800, textTransform: 'uppercase' }}>Session Replay</h4>
                    <code style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)' }}>{session.session_id}</code>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                    <button className="btn btn-secondary btn-sm" onClick={loadReport}>
                        <FileText size={14} /> Report
                    </button>
                </div>
            </div>

            {/* Summary */}
            <div className="insights-kpi-grid" style={{ marginBottom: '1rem' }}>
                {[
                    ['File', session.target_file?.split(/[\\/]/).pop()],
                    ['Duration', `${session.duration_seconds}s`],
                    ['Agents', session.total_interactions],
                    ['Patches', session.total_patches],
                ].map(([label, val]) => (
                    <div key={label} className="insights-kpi-card">
                        <label className="kpi-label">{label}</label>
                        <div className="kpi-value">{val}</div>
                    </div>
                ))}
            </div>

            {/* Error */}
            {session.error_message && (
                <div style={{ padding: '0.75rem', background: 'rgba(239, 68, 68, 0.05)', borderRadius: '0.5rem', marginBottom: '1rem', fontSize: '0.8rem', fontFamily: 'JetBrains Mono', color: 'var(--error)', border: '1px solid rgba(239, 68, 68, 0.1)' }}>
                    {session.error_message}
                </div>
            )}

            {/* Agent Timeline */}
            {session.interactions && session.interactions.length > 0 && (
                <div style={{ marginBottom: '1rem' }}>
                    <h5 style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)', marginBottom: '0.5rem', textTransform: 'uppercase' }}>Agent Pipeline</h5>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                        {session.interactions.map((interaction, i) => (
                            <div key={i} style={{ display: 'flex', gap: '0.75rem', padding: '0.4rem 0.5rem', fontSize: '0.75rem', background: 'rgba(255,255,255,0.02)', borderRadius: '0.4rem' }}>
                                <span style={{ fontWeight: 700, color: 'var(--accent)', minWidth: '100px' }}>{interaction.agent}</span>
                                <span style={{ color: 'var(--text-secondary)', flex: 1 }}>{interaction.action}</span>
                                <span style={{ color: 'var(--text-tertiary)', fontFamily: 'JetBrains Mono' }}>{interaction.duration_ms}ms</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Patch Attempts */}
            {session.patches && session.patches.length > 0 && (
                <div>
                    <h5 style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)', marginBottom: '0.5rem', textTransform: 'uppercase' }}>Patch Attempts</h5>
                    {session.patches.map((patch, i) => (
                        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.75rem', padding: '0.3rem 0' }}>
                            {patch.passed ? <CheckCircle2 size={14} color="var(--success)" /> : <AlertTriangle size={14} color="var(--warning)" />}
                            <span>Attempt {patch.attempt}: {patch.passed ? 'Passed' : patch.reason || 'Failed'}</span>
                        </div>
                    ))}
                </div>
            )}

            {/* Report Modal */}
            {showReport && report && (
                <div style={{ marginTop: '1rem', padding: '1rem', background: 'rgba(0,0,0,0.3)', borderRadius: '0.75rem', maxHeight: '400px', overflowY: 'auto' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                        <h5 style={{ fontSize: '0.75rem', color: 'var(--text-tertiary)' }}>DEBUGGING REPORT</h5>
                        <button className="btn btn-secondary btn-sm" onClick={() => setShowReport(false)}>Close</button>
                    </div>
                    <pre style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', whiteSpace: 'pre-wrap', fontFamily: 'JetBrains Mono' }}>{report}</pre>
                </div>
            )}
        </div>
    );
});

export const SessionList = React.memo(({ onSelect }) => {
    const [sessions, setSessions] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const loadSessions = async () => {
            setLoading(true);
            try {
                const data = await fetchJson(`${API}/sessions/`);
                setSessions(data.sessions || []);
            } catch (e) {
                console.error("Failed to load sessions", e);
            } finally {
                setLoading(false);
            }
        };
        loadSessions();
    }, []);

    if (loading) return <div className="card glass shimmer" style={{ height: '100px' }} />;
    if (sessions.length === 0) return (
        <div className="card glass" style={{ textAlign: 'center', padding: '1.5rem', color: 'var(--text-tertiary)', fontSize: '0.85rem' }}>
            <History size={24} style={{ opacity: 0.2, marginBottom: '0.5rem' }} />
            <p>No debugging sessions recorded yet.</p>
        </div>
    );

    return (
        <div className="card glass">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
                <History size={16} color="var(--accent)" />
                <h4 style={{ fontSize: '0.8rem', fontWeight: 800, textTransform: 'uppercase' }}>Recent Sessions</h4>
            </div>
            <div className="insights-list">
                {sessions.map((s, i) => (
                    <div key={i} className="insights-row" style={{ cursor: 'pointer' }} onClick={() => onSelect(s.session_id)}>
                        <div style={{ overflow: 'hidden' }}>
                            <div className="insights-title">{s.target_file?.split(/[\\/]/).pop() || 'Unknown'}</div>
                            <div className="insights-sub">{s.status} | {s.error?.slice(0, 50) || 'No error'}</div>
                        </div>
                        <div className="insights-score">{s.session_id?.slice(0, 6)}</div>
                    </div>
                ))}
            </div>
        </div>
    );
});

export default SessionReplay;
