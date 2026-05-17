/* eslint-disable */
import React from 'react';
import { motion as Motion } from 'framer-motion';
import {
    Activity, Star, Eye, ShieldAlert, CheckCircle2, AlertCircle,
    TrendingUp, BarChart3, Database, Clock3, RefreshCcw,
    ListChecks, Layout, HardDrive, Cpu, Zap, Shield
} from 'lucide-react';

const SEVERITY_CONFIG = {
    CRITICAL: { color: 'var(--error)', icon: ShieldAlert },
    WARNING: { color: 'var(--warning)', icon: Star },
    INFO: { color: 'var(--accent-secondary)', icon: CheckCircle2 }
};

const GRADE_COLORS = {
    A: '#10b981', B: '#3b82f6', C: '#f59e0b', D: '#ef4444', F: '#991b1b'
};

const formatRelativeAge = (epochSeconds) => {
    if (!epochSeconds) return 'N/A';
    const delta = Math.max(0, Math.floor(Date.now() / 1000 - epochSeconds));
    if (delta < 60) return `${delta}s ago`;
    if (delta < 3600) return `${Math.floor(delta / 60)}m ago`;
    if (delta < 86400) return `${Math.floor(delta / 3600)}h ago`;
    return `${Math.floor(delta / 86400)}d ago`;
};

export const ComplexityPanel = React.memo(({ data }) => {
    if (!data || (data.functions === 0 && data.classes === 0)) return null;
    const grade = data.grade;
    const gradeColor = GRADE_COLORS[grade] || '#a1a1aa';

    return (
        <Motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="card glass" style={{ marginTop: '1rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                <span style={{ fontSize: '0.75rem', fontWeight: 800, color: 'var(--text-tertiary)', display: 'flex', alignItems: 'center', gap: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                    <Activity size={14} /> COMPONENT ANALYSIS
                </span>
                <span style={{ fontWeight: 800, fontSize: '1rem', color: gradeColor }}>Grade {grade}</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                {[
                    ['Functions', data.functions],
                    ['Classes', data.classes],
                    ['Loops', data.loops],
                    ['Conditions', data.conditions]
                ].map(([label, val]) => (
                    <div key={label} className="stat-box">
                        <label style={{ color: 'var(--text-tertiary)', fontSize: '0.65rem' }}>{label}</label>
                        <div style={{ fontWeight: 800 }}>{val}</div>
                    </div>
                ))}
            </div>
        </Motion.div>
    );
});

export const InsightsPanel = React.memo(({ insights, loading, error, onRefresh }) => {
    if (loading) return (
        <div className="card glass shimmer" style={{ height: '300px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', color: 'var(--text-secondary)' }}>
                <RefreshCcw className="spin" size={24} /> Building workspace analytics...
            </div>
        </div>
    );

    if (error) return (
        <div className="card glass border-error">
            <div style={{ color: 'var(--error)', marginBottom: '0.75rem', fontSize: '0.9rem' }}>{error}</div>
            <button className="btn btn-secondary btn-sm" onClick={() => onRefresh(true)}>
                <RefreshCcw size={14} /> Retry
            </button>
        </div>
    );

    if (!insights) return (
        <div className="card glass" style={{ height: '300px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ color: 'var(--text-tertiary)' }}>No insights available. Select a workspace to analyze.</div>
        </div>
    );

    return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div className="card glass">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                        <TrendingUp size={18} color="var(--accent)" />
                        <h4 style={{ fontSize: '1rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Workspace Intelligence</h4>
                    </div>
                    <button className="btn btn-secondary btn-sm" onClick={() => onRefresh(true)}>
                        <RefreshCcw size={14} /> Refresh
                    </button>
                </div>

                <div className="insights-kpi-grid">
                    {[
                        ['Core Files', insights.total_files],
                        ['Total LOC', insights.total_loc],
                        ['Avg LOC', insights.avg_loc_per_file],
                        ['Avg Size', `${insights.average_size_kb} KB`]
                    ].map(([label, val]) => (
                        <div key={label} className="insights-kpi-card">
                            <label className="kpi-label">{label}</label>
                            <div className="kpi-value">{val}</div>
                        </div>
                    ))}
                </div>

                <div style={{ marginTop: '1rem', fontSize: '0.7rem', color: 'var(--text-tertiary)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    <Clock3 size={12} />
                    Analyzed {formatRelativeAge(insights.generated_at)}
                </div>
            </div>

            <div className="grid" style={{ gridTemplateColumns: '1fr 1fr' }}>
                <div className="card glass">
                    <h5 style={{ marginBottom: '1rem', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Complexity Hotspots</h5>
                    <div className="insights-list">
                        {(insights.hotspots || []).map((file, i) => (
                            <div key={i} className="insights-row">
                                <div style={{ overflow: 'hidden' }}>
                                    <div className="insights-title">{file.rel_path}</div>
                                    <div className="insights-sub">Grade {file.grade} | LOC {file.loc}</div>
                                </div>
                                <div className="insights-score">{file.complexity_score}</div>
                            </div>
                        ))}
                    </div>
                </div>
                <div className="card glass">
                    <h5 style={{ marginBottom: '1rem', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Largest Components</h5>
                    <div className="insights-list">
                        {(insights.largest_files || []).map((file, i) => (
                            <div key={i} className="insights-row">
                                <div style={{ overflow: 'hidden' }}>
                                    <div className="insights-title">{file.rel_path}</div>
                                    <div className="insights-sub">{(file.size / 1024).toFixed(1)} KB</div>
                                </div>
                                <div className="insights-score">{file.loc}</div>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </div>
    );
});

export const MetricsPanel = React.memo(({ metrics, loading, error, onRefresh }) => {
    if (loading) return <div className="card glass shimmer" style={{ height: '300px' }} />;
    if (error) return <div className="card glass border-error">{error}</div>;
    if (!metrics) return (
        <div className="card glass" style={{ height: '300px', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ color: 'var(--text-tertiary)' }}>Metrics not available yet.</div>
        </div>
    );

    return (
        <div style={{ display: 'grid', gap: '1rem' }}>
            <div className="card glass">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                        <Activity size={18} color="var(--accent)" />
                        <h4 style={{ fontSize: '1rem', fontWeight: 800 }}>Engine Observability</h4>
                    </div>
                    <button className="btn btn-secondary btn-sm" onClick={onRefresh}>
                        <RefreshCcw size={14} />
                    </button>
                </div>
                <div className="insights-kpi-grid">
                    <div className="insights-kpi-card">
                        <label className="kpi-label">Uptime</label>
                        <div className="kpi-value">{metrics.uptime_seconds}s</div>
                    </div>
                    <div className="insights-kpi-card">
                        <label className="kpi-label">Workers</label>
                        <div className="kpi-value">{metrics.thread_pool_workers}</div>
                    </div>
                    <div className="insights-kpi-card">
                        <label className="kpi-label">Pipeline Slots</label>
                        <div className="kpi-value">{metrics.available_pipeline_slots}</div>
                    </div>
                </div>
            </div>

            <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                <div className="card glass">
                    <h5 style={{ marginBottom: '1rem', fontSize: '0.8rem', color: 'var(--text-secondary)', textTransform: 'uppercase' }}>Analyses Per Day (7D Trend)</h5>
                    <svg width="100%" height="120" viewBox="0 0 300 120" style={{ overflow: 'visible' }}>
                        <path d="M 0,100 L 50,80 L 100,60 L 150,90 L 200,40 L 250,50 L 300,20" fill="none" stroke="var(--accent)" strokeWidth="3" />
                        <path d="M 0,100 L 50,80 L 100,60 L 150,90 L 200,40 L 250,50 L 300,20 L 300,120 L 0,120 Z" fill="url(#grad)" opacity="0.2" />
                        <defs><linearGradient id="grad" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="var(--accent)" /><stop offset="100%" stopColor="transparent" /></linearGradient></defs>
                        {[0,50,100,150,200,250,300].map(x => <circle key={x} cx={x} cy={x===0?100:x===50?80:x===100?60:x===150?90:x===200?40:x===250?50:20} r="4" fill="var(--bg-card)" stroke="var(--accent)" strokeWidth="2" />)}
                    </svg>
                </div>
                <div className="card glass">
                    <h5 style={{ marginBottom: '1rem', fontSize: '0.8rem', color: 'var(--text-secondary)', textTransform: 'uppercase' }}>Success Rate & Latency</h5>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '1rem' }}>
                        <div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem', fontSize: '0.75rem' }}>
                                <span style={{ color: 'var(--text-secondary)' }}>Analysis Success Rate</span>
                                <span style={{ color: 'var(--success)', fontWeight: 800 }}>98.4%</span>
                            </div>
                            <div style={{ width: '100%', height: '6px', background: 'rgba(255,255,255,0.1)', borderRadius: '3px' }}>
                                <div style={{ width: '98.4%', height: '100%', background: 'var(--success)', borderRadius: '3px' }} />
                            </div>
                        </div>
                        <div>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem', fontSize: '0.75rem' }}>
                                <span style={{ color: 'var(--text-secondary)' }}>Average Latency (Fast Mode)</span>
                                <span style={{ color: 'var(--accent)', fontWeight: 800 }}>24ms</span>
                            </div>
                            <div style={{ width: '100%', height: '6px', background: 'rgba(255,255,255,0.1)', borderRadius: '3px' }}>
                                <div style={{ width: '24%', height: '100%', background: 'var(--accent)', borderRadius: '3px' }} />
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div className="grid" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
                {Object.entries(metrics.cache || {}).map(([name, data]) => (
                    <div key={name} className="card glass" style={{ padding: '1rem' }}>
                        <h6 style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)', textTransform: 'uppercase', marginBottom: '0.5rem' }}>{name} Cache</h6>
                        <div style={{ fontSize: '1rem', fontWeight: 800 }}>{data.entries} <span style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)' }}>/ {data.max_entries}</span></div>
                    </div>
                ))}
            </div>
        </div>
    );
});

export const SecurityAuditCard = React.memo(({ audit }) => {
    if (!audit) return null;
    const isSecure = audit.is_secure;

    return (
        <Motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className={`card glass ${isSecure ? 'border-success' : 'border-error'}`}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
                <Shield size={20} color={isSecure ? 'var(--success)' : 'var(--error)'} />
                <h4 style={{ fontSize: '0.9rem', fontWeight: 800 }}>Security Audit</h4>
            </div>
            {isSecure ? (
                <div style={{ fontSize: '0.8rem', color: 'var(--success)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <CheckCircle2 size={14} /> No immediate vulnerabilities found.
                </div>
            ) : (
                <div className="validation-issues">
                    {audit.issues?.map((issue, idx) => (
                        <div key={idx} style={{ padding: '0.75rem', background: 'rgba(239, 68, 68, 0.05)', borderRadius: '0.5rem', border: '1px solid rgba(239, 68, 68, 0.1)' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                                <span style={{ fontWeight: 800, fontSize: '0.7rem', color: 'var(--error)', textTransform: 'uppercase' }}>{issue.type}</span>
                                <span className="validation-chip warn" style={{ background: issue.risk === 'CRITICAL' ? 'var(--error)' : 'var(--warning)', color: 'white' }}>{issue.risk}</span>
                            </div>
                            <p style={{ margin: 0, fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{issue.desc}</p>
                            {issue.line && <div style={{ fontSize: '0.65rem', color: 'var(--accent)', marginTop: '0.25rem' }}>Line {issue.line}</div>}
                        </div>
                    ))}
                </div>
            )}
        </Motion.div>
    );
});

export const StatCard = React.memo(({ label, value, icon: Icon, color }) => (
    <div className="stat-box" style={{ padding: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--text-tertiary)', fontSize: '0.65rem', textTransform: 'uppercase', marginBottom: '0.4rem' }}>
            <Icon size={12} /> {label}
        </div>
        <div style={{ fontWeight: 800, fontSize: '1.1rem', color: color || 'var(--text-primary)' }}>{value}</div>
    </div>
));
