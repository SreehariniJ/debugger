import React, { useState, useCallback, useEffect, useRef } from 'react';
import { GitBranch, Network, Activity, Box, ZoomIn, ZoomOut, Maximize2, Loader, AlertCircle } from 'lucide-react';

const NODE_COLORS = {
    default: { bg: 'rgba(168, 85, 247, 0.15)', border: '#a855f7' },
    entry: { bg: 'rgba(16, 185, 129, 0.15)', border: '#10b981' },
    exit: { bg: 'rgba(239, 68, 68, 0.15)', border: '#ef4444' },
    if_true: { bg: 'rgba(59, 130, 246, 0.15)', border: '#3b82f6' },
    if_false: { bg: 'rgba(245, 158, 11, 0.15)', border: '#f59e0b' },
    loop_body: { bg: 'rgba(139, 92, 246, 0.15)', border: '#8b5cf6' },
    except: { bg: 'rgba(239, 68, 68, 0.15)', border: '#ef4444' },
};

const EDGE_COLORS = {
    true: '#10b981', false: '#ef4444', except: '#f59e0b',
    finally: '#6366f1', loop_back: '#8b5cf6', return: '#ef4444',
    default: '#64748b',
};

const GraphNode = React.memo(({ node, scale, offset }) => {
    const pos = node.position || { x: 0, y: 0 };
    const x = pos.x * scale + offset.x;
    const y = pos.y * scale + offset.y;
    const label = node.data?.label || node.id;
    const nodeStyle = node.style || {};
    const borderColor = nodeStyle.borderColor || NODE_COLORS.default.border;

    return (
        <g transform={`translate(${x}, ${y})`}>
            <rect
                width={160 * scale} height={50 * scale} rx={8 * scale}
                fill="rgba(15, 15, 20, 0.9)"
                stroke={borderColor} strokeWidth={2}
            />
            <text
                x={80 * scale} y={30 * scale}
                fill="#e2e8f0" fontSize={12 * scale}
                textAnchor="middle" fontFamily="JetBrains Mono, monospace"
            >
                {label.length > 20 ? label.slice(0, 20) + '…' : label}
            </text>
        </g>
    );
});

const GraphEdge = React.memo(({ edge, nodes, scale, offset }) => {
    const src = nodes[edge.source];
    const tgt = nodes[edge.target];
    if (!src || !tgt) return null;

    const x1 = (src.position?.x || 0) * scale + offset.x + 80 * scale;
    const y1 = (src.position?.y || 0) * scale + offset.y + 50 * scale;
    const x2 = (tgt.position?.x || 0) * scale + offset.x + 80 * scale;
    const y2 = (tgt.position?.y || 0) * scale + offset.y;
    const color = edge.style?.stroke || EDGE_COLORS[edge.label] || EDGE_COLORS.default;

    const midY = (y1 + y2) / 2;
    const path = `M ${x1} ${y1} C ${x1} ${midY}, ${x2} ${midY}, ${x2} ${y2}`;

    return (
        <g>
            <defs>
                <marker id={`arrow-${edge.id}`} viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                    <path d="M 0 0 L 10 5 L 0 10 z" fill={color} />
                </marker>
            </defs>
            <path d={path} stroke={color} strokeWidth={1.5} fill="none" markerEnd={`url(#arrow-${edge.id})`} strokeDasharray={edge.animated ? "5,5" : "none"} />
            {edge.label && (
                <text x={(x1 + x2) / 2 + 5} y={(y1 + y2) / 2} fill={color} fontSize={10 * scale} fontFamily="JetBrains Mono, monospace">{edge.label}</text>
            )}
        </g>
    );
});

export const GraphViewer = React.memo(({ data, title, loading, error, graphType }) => {
    const [scale, setScale] = useState(0.8);
    const [offset, setOffset] = useState({ x: 40, y: 30 });
    const svgRef = useRef(null);
    const [dragging, setDragging] = useState(false);
    const [dragStart, setDragStart] = useState({ x: 0, y: 0 });

    if (loading) return (
        <div className="card glass" style={{ padding: '2rem', textAlign: 'center' }}>
            <Loader className="spin" size={24} style={{ margin: '0 auto 1rem' }} />
            <p style={{ color: 'var(--text-secondary)' }}>Building {graphType || 'graph'}...</p>
        </div>
    );

    if (error) return (
        <div className="card glass border-error" style={{ padding: '1.5rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--error)' }}>
                <AlertCircle size={16} /> {error}
            </div>
        </div>
    );

    if (!data || !data.nodes || data.nodes.length === 0) return null;

    const nodeMap = {};
    data.nodes.forEach(n => { nodeMap[n.id] = n; });

    const handleMouseDown = (e) => {
        setDragging(true);
        setDragStart({ x: e.clientX - offset.x, y: e.clientY - offset.y });
    };
    const handleMouseMove = (e) => {
        if (dragging) setOffset({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y });
    };
    const handleMouseUp = () => setDragging(false);

    const typeIcon = graphType === 'call_graph' ? <Network size={16} /> :
        graphType === 'cfg' ? <GitBranch size={16} /> :
            graphType === 'dependency_graph' ? <Box size={16} /> : <Activity size={16} />;

    return (
        <div className="card glass" style={{ overflow: 'hidden', padding: 0 }}>
            <div style={{ padding: '1rem 1.25rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    {typeIcon}
                    <h4 style={{ fontSize: '0.85rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{title || 'Graph View'}</h4>
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-tertiary)' }}>{data.nodes.length} nodes · {(data.edges || []).length} edges</span>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                    <button className="btn btn-secondary btn-sm" onClick={() => setScale(s => Math.min(2, s + 0.1))} title="Zoom In"><ZoomIn size={14} /></button>
                    <button className="btn btn-secondary btn-sm" onClick={() => setScale(s => Math.max(0.3, s - 0.1))} title="Zoom Out"><ZoomOut size={14} /></button>
                    <button className="btn btn-secondary btn-sm" onClick={() => { setScale(0.8); setOffset({ x: 40, y: 30 }); }} title="Reset"><Maximize2 size={14} /></button>
                </div>
            </div>
            <svg
                ref={svgRef}
                width="100%" height="450"
                style={{ background: 'rgba(0,0,0,0.2)', cursor: dragging ? 'grabbing' : 'grab' }}
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={handleMouseUp}
                onMouseLeave={handleMouseUp}
            >
                {(data.edges || []).map(edge => (
                    <GraphEdge key={edge.id} edge={edge} nodes={nodeMap} scale={scale} offset={offset} />
                ))}
                {data.nodes.map(node => (
                    <GraphNode key={node.id} node={node} scale={scale} offset={offset} />
                ))}
            </svg>
        </div>
    );
});

export default GraphViewer;
