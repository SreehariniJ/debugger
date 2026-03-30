import React, { useState } from 'react';
import { Play, Pause, SkipForward, StopCircle, Eye, Variable, Clock3, Loader, AlertCircle } from 'lucide-react';

export const DebuggerControls = React.memo(({ onTrace, onProfile, tracing, profiling, filePath }) => {
    return (
        <div className="card glass" style={{ padding: '1rem', marginBottom: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem' }}>
                <Play size={16} color="var(--accent)" />
                <h4 style={{ fontSize: '0.8rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Runtime Analysis</h4>
            </div>
            <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
                <button
                    className="btn btn-primary btn-sm"
                    onClick={onTrace}
                    disabled={tracing || !filePath}
                    style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}
                >
                    {tracing ? <Loader className="spin" size={14} /> : <Eye size={14} />}
                    {tracing ? 'Tracing...' : 'Trace Execution'}
                </button>
                <button
                    className="btn btn-secondary btn-sm"
                    onClick={onProfile}
                    disabled={profiling || !filePath}
                    style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}
                >
                    {profiling ? <Loader className="spin" size={14} /> : <Clock3 size={14} />}
                    {profiling ? 'Profiling...' : 'Profile CPU'}
                </button>
            </div>
        </div>
    );
});

export const ExecutionTimeline = React.memo(({ data, loading, error }) => {
    const [hoveredIdx, setHoveredIdx] = useState(null);

    if (loading) return (
        <div className="card glass shimmer" style={{ height: '200px' }} />
    );
    if (error) return (
        <div className="card glass border-error">
            <AlertCircle size={14} /> {error}
        </div>
    );
    if (!data || !data.entries || data.entries.length === 0) return null;

    const entries = data.entries;
    const maxDepth = data.max_depth || 1;
    const barWidth = Math.max(2, Math.min(8, 600 / entries.length));

    return (
        <div className="card glass" style={{ overflow: 'hidden', padding: 0 }}>
            <div style={{ padding: '1rem 1.25rem', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <Clock3 size={16} color="var(--accent)" />
                <h4 style={{ fontSize: '0.8rem', fontWeight: 800, textTransform: 'uppercase' }}>Execution Timeline</h4>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)' }}>
                    {data.displayed_events} of {data.total_events} events
                </span>
            </div>
            <div style={{ padding: '1rem', overflowX: 'auto' }}>
                <svg width={Math.max(600, entries.length * barWidth)} height={120}>
                    {entries.map((entry, i) => {
                        const height = Math.max(4, (entry.depth / Math.max(maxDepth, 1)) * 80);
                        const isException = !!entry.exception;
                        const color = isException ? '#ef4444' : entry.type === 'call' ? '#3b82f6' : entry.type === 'return' ? '#10b981' : '#a855f7';

                        return (
                            <g key={i} onMouseEnter={() => setHoveredIdx(i)} onMouseLeave={() => setHoveredIdx(null)}>
                                <rect
                                    x={i * barWidth} y={100 - height}
                                    width={barWidth - 1} height={height}
                                    fill={color} opacity={hoveredIdx === i ? 1 : 0.6}
                                    rx={1}
                                />
                            </g>
                        );
                    })}
                </svg>
                {hoveredIdx !== null && entries[hoveredIdx] && (
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-secondary)', marginTop: '0.5rem', fontFamily: 'JetBrains Mono' }}>
                        <strong>L{entries[hoveredIdx].line}</strong> {entries[hoveredIdx].function} [{entries[hoveredIdx].type}]
                        {entries[hoveredIdx].exception && <span style={{ color: 'var(--error)' }}> ⚠ {entries[hoveredIdx].exception}</span>}
                    </div>
                )}
            </div>
        </div>
    );
});

export const VariableInspector = React.memo(({ history, varName, loading }) => {
    if (loading) return <div className="card glass shimmer" style={{ height: '150px' }} />;
    if (!history || history.length === 0) return null;

    return (
        <div className="card glass">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
                <Variable size={16} color="var(--accent-secondary)" />
                <h4 style={{ fontSize: '0.8rem', fontWeight: 800, textTransform: 'uppercase' }}>
                    Variable: <code style={{ color: 'var(--accent)' }}>{varName}</code>
                </h4>
                <span style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)' }}>{history.length} snapshots</span>
            </div>
            <div className="viper-editor-scroll" style={{ maxHeight: '250px', overflowY: 'auto' }}>
                <table style={{ width: '100%', fontSize: '0.75rem', borderCollapse: 'collapse' }}>
                    <thead>
                        <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
                            <th style={{ textAlign: 'left', padding: '0.5rem', color: 'var(--text-tertiary)' }}>Line</th>
                            <th style={{ textAlign: 'left', padding: '0.5rem', color: 'var(--text-tertiary)' }}>Function</th>
                            <th style={{ textAlign: 'left', padding: '0.5rem', color: 'var(--text-tertiary)' }}>Value</th>
                        </tr>
                    </thead>
                    <tbody>
                        {history.map((h, i) => (
                            <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                                <td style={{ padding: '0.4rem 0.5rem', fontFamily: 'JetBrains Mono', color: 'var(--accent)' }}>L{h.lineno || h.line}</td>
                                <td style={{ padding: '0.4rem 0.5rem', color: 'var(--text-secondary)' }}>{h.function}</td>
                                <td style={{ padding: '0.4rem 0.5rem', fontFamily: 'JetBrains Mono', color: 'var(--text-primary)', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis' }}>{h.value || h.y_label}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
});

export default DebuggerControls;
