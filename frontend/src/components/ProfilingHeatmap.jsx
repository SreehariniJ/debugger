import React from 'react';
import { Flame, Cpu, HardDrive, AlertCircle, Loader } from 'lucide-react';

export const ProfilingHeatmap = React.memo(({ data, loading, error, type }) => {
    if (loading) return <div className="card glass shimmer" style={{ height: '250px' }} />;
    if (error) return (
        <div className="card glass border-error">
            <AlertCircle size={14} /> {error}
        </div>
    );
    if (!data) return null;

    const isMemory = type === 'memory';
    const title = isMemory ? 'Memory Allocation Profile' : 'CPU Performance Heatmap';
    const Icon = isMemory ? HardDrive : Cpu;

    // For CPU profiling
    if (!isMemory && data.functions) {
        const functions = data.functions.filter(f => f.cumulative_time > 0).slice(0, 20);
        const maxTime = Math.max(...functions.map(f => f.cumulative_time), 0.001);

        return (
            <div className="card glass">
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                        <Flame size={18} color="var(--accent)" />
                        <h4 style={{ fontSize: '0.85rem', fontWeight: 800, textTransform: 'uppercase' }}>{title}</h4>
                    </div>
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)' }}>
                        Total: {data.total_time?.toFixed(4)}s | {data.bottleneck_count || 0} bottlenecks
                    </span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                    {functions.map((func, i) => {
                        const pct = (func.cumulative_time / maxTime) * 100;
                        const hue = 120 - (pct / 100) * 120; // green → red
                        const color = `hsl(${hue}, 80%, 55%)`;

                        return (
                            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                                <div style={{ width: '120px', fontSize: '0.7rem', fontFamily: 'JetBrains Mono', color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={func.name}>
                                    {func.name}
                                </div>
                                <div style={{ flex: 1, height: '20px', background: 'rgba(255,255,255,0.03)', borderRadius: '4px', overflow: 'hidden', position: 'relative' }}>
                                    <div style={{ width: `${pct}%`, height: '100%', background: `linear-gradient(90deg, ${color}33, ${color})`, borderRadius: '4px', transition: 'width 0.5s ease' }} />
                                    <span style={{ position: 'absolute', right: '6px', top: '2px', fontSize: '0.65rem', color: 'var(--text-tertiary)' }}>
                                        {func.cumulative_time.toFixed(4)}s ({func.calls} calls)
                                    </span>
                                </div>
                                {func.is_bottleneck && <Flame size={12} color="#ef4444" />}
                            </div>
                        );
                    })}
                </div>
            </div>
        );
    }

    // For memory profiling
    if (isMemory && data.top_allocations) {
        return (
            <div className="card glass">
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.25rem' }}>
                    <HardDrive size={18} color="var(--accent-secondary)" />
                    <h4 style={{ fontSize: '0.85rem', fontWeight: 800, textTransform: 'uppercase' }}>{title}</h4>
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)' }}>
                        Peak: {data.peak_memory_kb?.toFixed(1)} KB
                    </span>
                </div>
                <div className="viper-editor-scroll" style={{ maxHeight: '300px', overflowY: 'auto' }}>
                    <table style={{ width: '100%', fontSize: '0.75rem', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
                                <th style={{ textAlign: 'left', padding: '0.5rem', color: 'var(--text-tertiary)' }}>File</th>
                                <th style={{ textAlign: 'left', padding: '0.5rem', color: 'var(--text-tertiary)' }}>Line</th>
                                <th style={{ textAlign: 'right', padding: '0.5rem', color: 'var(--text-tertiary)' }}>Size (KB)</th>
                                <th style={{ textAlign: 'right', padding: '0.5rem', color: 'var(--text-tertiary)' }}>Count</th>
                            </tr>
                        </thead>
                        <tbody>
                            {data.top_allocations.map((alloc, i) => (
                                <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                                    <td style={{ padding: '0.4rem 0.5rem', color: 'var(--text-secondary)', maxWidth: '180px', overflow: 'hidden', textOverflow: 'ellipsis' }}>{alloc.file?.split(/[\\/]/).pop()}</td>
                                    <td style={{ padding: '0.4rem 0.5rem', fontFamily: 'JetBrains Mono', color: 'var(--accent)' }}>L{alloc.line}</td>
                                    <td style={{ padding: '0.4rem 0.5rem', fontFamily: 'JetBrains Mono', color: 'var(--text-primary)', textAlign: 'right' }}>{alloc.size_kb?.toFixed(2)}</td>
                                    <td style={{ padding: '0.4rem 0.5rem', color: 'var(--text-tertiary)', textAlign: 'right' }}>{alloc.count}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        );
    }

    return null;
});

export default ProfilingHeatmap;
