import React from 'react';
import { motion as Motion } from 'framer-motion';
import { Zap, Terminal, Code2, FileText, CheckCircle2, AlertTriangle, Clipboard, Copy } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

export const ViperHeader = React.memo(({ result }) => {
    if (!result) return (
        <div className="result-empty">
            <Code2 size={48} style={{ opacity: 0.1 }} />
            <p>Select a file or paste code to begin architecture-aware debugging.</p>
        </div>
    );

    return (
        <div className="card glass result-banner">
            <div className="result-banner-watermark">
                <Zap size={40} color="var(--accent)" />
            </div>
            <div className="result-banner-body">
                <div className="result-banner-content">
                    <div className="result-banner-status-row">
                        <div className={`status-indicator ${result.success ? 'ok' : 'warn'} result-banner-status-pill`}>
                            {result.success ? <CheckCircle2 size={12} color="var(--success)" /> : <AlertTriangle size={12} color="var(--warning)" />}
                            <span className="result-banner-status-label">{result.success ? 'STABLE' : 'ANOMALY DETECTED'}</span>
                        </div>
                        <span className="result-banner-reqid">{result.request_id?.slice(0, 8)}</span>
                    </div>
                    <div className="markdown-body">
                        {result.analysis ? (
                            <ReactMarkdown>{`### Analysis\n${result.analysis}`}</ReactMarkdown>
                        ) : (
                            <h2>Analysis Pending</h2>
                        )}
                        {result.explanation ? (
                            <ReactMarkdown>{`### Resolution\n${result.explanation}`}</ReactMarkdown>
                        ) : (
                            <p>The model is analyzing the execution context...</p>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
});

export const PipelineExecutionLog = React.memo(({ log, loading }) => {
    if (!log || log.length === 0) return null;
    return (
        <Motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="card glass pipeline-trace">
            <div className="pipeline-trace-header">
                <Terminal size={18} color="var(--text-tertiary)" />
                <h4 className="pipeline-trace-title">Pipeline Execution Trace</h4>
            </div>
            <div className="viper-editor-scroll pipeline-trace-scroll">
                {log.map((entry, i) => (
                    <div key={i} className="pipeline-trace-entry">
                        <span className="pipeline-trace-ts">[{entry.timestamp}]</span>
                        <span style={{ color: entry.level === 'ERROR' ? 'var(--error)' : entry.level === 'WARN' ? 'var(--warning)' : 'var(--accent-secondary)' }}>{entry.level}</span>
                        <span className="pipeline-trace-msg">{entry.message}</span>
                    </div>
                ))}
                {loading && <div className="loader" style={{ margin: '0.5rem' }} />}
            </div>
        </Motion.div>
    );
});

export const DiffPanel = React.memo(({ diff, onClose }) => {
    if (!diff) return null;
    return (
        <Motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} className="card glass diff-panel">
            <div className="diff-panel-header">
                <div className="diff-panel-title">
                    <FileText size={18} color="var(--accent)" />
                    <h4>Proposed Changes (Diff)</h4>
                </div>
                <button className="btn btn-secondary btn-sm" onClick={onClose}>Hide Diff</button>
            </div>
            <pre className="viper-editor-scroll diff-pre">
                {diff.split('\n').map((line, i) => {
                    const color = line.startsWith('+') ? 'var(--success)' : line.startsWith('-') ? 'var(--error)' : 'inherit';
                    const bg = line.startsWith('+') ? 'rgba(16, 185, 129, 0.1)' : line.startsWith('-') ? 'rgba(239, 68, 68, 0.1)' : 'transparent';
                    return <div key={i} style={{ color, background: bg }}>{line}</div>;
                })}
            </pre>
        </Motion.div>
    );
});

export const PatchValidationView = React.memo(({ validation }) => {
    if (!validation) return null;
    const isOk = validation.ready_to_apply;
    return (
        <div className={`fix-validation-panel ${isOk ? 'ok' : 'warn'}`} style={{ marginTop: '1.5rem' }}>
            <div className="patch-header">
                <div className="patch-title-group">
                    {isOk ? <CheckCircle2 size={16} color="var(--success)" /> : <AlertTriangle size={16} color="var(--warning)" />}
                    <span className="patch-title-label">Patch Quality Report</span>
                </div>
                <span className={`validation-chip ${isOk ? 'ok' : 'warn'}`}>
                    {isOk ? 'Ready to Apply' : 'Requires Review'}
                </span>
            </div>
            <ul className="validation-issues">
                {validation.issues?.map((issue, idx) => (
                    <li key={idx} className="validation-issue-item">
                        <span className="validation-issue-bullet" style={{ color: isOk ? 'var(--success)' : 'var(--warning)' }}>•</span>
                        {issue}
                    </li>
                ))}
            </ul>
        </div>
    );
});

export const EditorToolbar = React.memo(({ onCopy, onDiff, onApply, onExport, hasFixedCode, showDiff }) => {
    if (!hasFixedCode) return null;
    return (
        <div className="editor-toolbar">
            <button className="btn btn-primary" onClick={onApply} style={{ flex: 1 }}>
                Commit Fix to Disk
            </button>
            <button className="btn btn-secondary" onClick={onExport} title="Export Debug Report">
                <Clipboard size={18} /> Export Report
            </button>
            <button className="btn btn-secondary" onClick={onCopy} title="Copy to Clipboard">
                <Copy size={18} />
            </button>
            <button className={`btn ${showDiff ? 'btn-primary' : 'btn-secondary'}`} onClick={onDiff} title="Toggle Diff View">
                <FileText size={18} />
            </button>
        </div>
    );
});
