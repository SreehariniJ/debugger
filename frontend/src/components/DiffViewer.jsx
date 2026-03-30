import { useState, useMemo, useCallback } from 'react';

/**
 * DiffViewer — A rich side-by-side / unified diff viewer for AI-generated code fixes.
 *
 * Props:
 *   originalCode  (string)  — The original source code
 *   fixedCode     (string)  — The AI-generated fixed code
 *   filePath      (string)  — Path to the file being patched
 *   hunks         (array)   — Structured diff hunks from /patch/preview
 *   stats         (object)  — { additions, deletions, modifications }
 *   gitAvailable  (boolean) — Whether Git workflow is available
 *   onApplyFix    (fn)      — Callback to apply the fix
 *   onClose       (fn)      — Callback to close the viewer
 */

/* ── Styles ──────────────────────────────────────────────────────────────── */

const styles = {
  overlay: {
    position: 'fixed',
    inset: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.75)',
    backdropFilter: 'blur(8px)',
    zIndex: 9999,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '24px',
    animation: 'diffFadeIn 0.2s ease-out',
  },
  container: {
    width: '100%',
    maxWidth: '1400px',
    maxHeight: '90vh',
    backgroundColor: '#0d1117',
    borderRadius: '16px',
    border: '1px solid rgba(139, 148, 158, 0.2)',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    boxShadow: '0 24px 80px rgba(0, 0, 0, 0.6)',
  },

  /* Header */
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '16px 24px',
    borderBottom: '1px solid rgba(139, 148, 158, 0.15)',
    background: 'linear-gradient(135deg, rgba(56, 139, 253, 0.08), rgba(139, 92, 246, 0.06))',
    flexWrap: 'wrap',
    gap: '12px',
  },
  headerLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    minWidth: 0,
  },
  headerIcon: {
    width: '36px',
    height: '36px',
    borderRadius: '10px',
    background: 'linear-gradient(135deg, #388bfd, #8b5cf6)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: '18px',
    flexShrink: 0,
  },
  headerTitle: {
    fontSize: '15px',
    fontWeight: 600,
    color: '#e6edf3',
    fontFamily: "'Inter', 'Segoe UI', sans-serif",
  },
  headerFile: {
    fontSize: '12px',
    color: '#8b949e',
    fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },

  /* Stats bar */
  statsBar: {
    display: 'flex',
    alignItems: 'center',
    gap: '16px',
    padding: '10px 24px',
    borderBottom: '1px solid rgba(139, 148, 158, 0.1)',
    backgroundColor: 'rgba(13, 17, 23, 0.6)',
    flexWrap: 'wrap',
  },
  statBadge: (color) => ({
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    padding: '4px 10px',
    borderRadius: '20px',
    fontSize: '12px',
    fontWeight: 600,
    fontFamily: "'JetBrains Mono', monospace",
    backgroundColor: `${color}18`,
    color: color,
    border: `1px solid ${color}30`,
  }),

  /* Toggle */
  toggleGroup: {
    display: 'flex',
    borderRadius: '8px',
    overflow: 'hidden',
    border: '1px solid rgba(139, 148, 158, 0.2)',
  },
  toggleBtn: (active) => ({
    padding: '6px 14px',
    fontSize: '12px',
    fontWeight: 500,
    fontFamily: "'Inter', sans-serif",
    border: 'none',
    cursor: 'pointer',
    transition: 'all 0.15s ease',
    backgroundColor: active ? 'rgba(56, 139, 253, 0.2)' : 'transparent',
    color: active ? '#58a6ff' : '#8b949e',
  }),

  /* Diff body */
  diffBody: {
    flex: 1,
    overflow: 'auto',
    fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace",
    fontSize: '13px',
    lineHeight: '20px',
  },

  /* Split view */
  splitContainer: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    minWidth: '800px',
  },
  splitPane: {
    borderRight: '1px solid rgba(139, 148, 158, 0.1)',
  },
  paneHeader: (type) => ({
    padding: '8px 16px',
    fontSize: '11px',
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    color: type === 'original' ? '#f85149' : '#3fb950',
    backgroundColor: type === 'original' ? 'rgba(248, 81, 73, 0.06)' : 'rgba(63, 185, 80, 0.06)',
    borderBottom: '1px solid rgba(139, 148, 158, 0.1)',
    position: 'sticky',
    top: 0,
    zIndex: 2,
  }),

  /* Lines */
  lineRow: (type) => {
    const bgMap = {
      insert: 'rgba(63, 185, 80, 0.10)',
      delete: 'rgba(248, 81, 73, 0.10)',
      replace: 'rgba(210, 153, 34, 0.08)',
      equal: 'transparent',
    };
    return {
      display: 'flex',
      minHeight: '20px',
      backgroundColor: bgMap[type] || 'transparent',
      borderBottom: '1px solid rgba(139, 148, 158, 0.04)',
    };
  },
  lineNumber: {
    width: '50px',
    minWidth: '50px',
    padding: '0 8px',
    textAlign: 'right',
    color: 'rgba(139, 148, 158, 0.5)',
    fontSize: '12px',
    userSelect: 'none',
    flexShrink: 0,
  },
  lineContent: (type) => {
    const colorMap = {
      insert: '#3fb950',
      delete: '#f85149',
      replace: '#d29922',
      equal: '#e6edf3',
    };
    return {
      flex: 1,
      padding: '0 12px',
      color: colorMap[type] || '#e6edf3',
      whiteSpace: 'pre',
      overflow: 'hidden',
      textOverflow: 'ellipsis',
    };
  },
  lineMarker: (type) => ({
    width: '20px',
    minWidth: '20px',
    textAlign: 'center',
    fontWeight: 700,
    fontSize: '13px',
    color: type === 'insert' ? '#3fb950' : type === 'delete' ? '#f85149' : '#8b949e',
    userSelect: 'none',
  }),

  /* Collapsed block */
  collapsedBlock: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '6px 16px',
    backgroundColor: 'rgba(56, 139, 253, 0.04)',
    borderTop: '1px dashed rgba(56, 139, 253, 0.2)',
    borderBottom: '1px dashed rgba(56, 139, 253, 0.2)',
    color: '#58a6ff',
    fontSize: '11px',
    cursor: 'pointer',
    userSelect: 'none',
    gap: '6px',
  },

  /* Footer */
  footer: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '16px 24px',
    borderTop: '1px solid rgba(139, 148, 158, 0.15)',
    background: 'rgba(13, 17, 23, 0.8)',
    flexWrap: 'wrap',
    gap: '12px',
  },
  footerInfo: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    fontSize: '12px',
    color: '#8b949e',
  },
  gitBadge: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    padding: '3px 8px',
    borderRadius: '6px',
    fontSize: '11px',
    fontWeight: 500,
    backgroundColor: 'rgba(63, 185, 80, 0.1)',
    color: '#3fb950',
    border: '1px solid rgba(63, 185, 80, 0.2)',
  },
  footerActions: {
    display: 'flex',
    gap: '10px',
  },
  btnSecondary: {
    padding: '8px 16px',
    borderRadius: '8px',
    border: '1px solid rgba(139, 148, 158, 0.3)',
    background: 'transparent',
    color: '#e6edf3',
    fontSize: '13px',
    fontWeight: 500,
    cursor: 'pointer',
    fontFamily: "'Inter', sans-serif",
    transition: 'all 0.15s ease',
  },
  btnPrimary: {
    padding: '8px 20px',
    borderRadius: '8px',
    border: 'none',
    background: 'linear-gradient(135deg, #238636, #2ea043)',
    color: '#ffffff',
    fontSize: '13px',
    fontWeight: 600,
    cursor: 'pointer',
    fontFamily: "'Inter', sans-serif",
    transition: 'all 0.15s ease',
    boxShadow: '0 2px 8px rgba(35, 134, 54, 0.3)',
  },
  btnApplying: {
    padding: '8px 20px',
    borderRadius: '8px',
    border: 'none',
    background: 'rgba(139, 148, 158, 0.2)',
    color: '#8b949e',
    fontSize: '13px',
    fontWeight: 600,
    cursor: 'not-allowed',
    fontFamily: "'Inter', sans-serif",
  },

  /* Result banner */
  resultBanner: (success) => ({
    padding: '12px 24px',
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    fontSize: '13px',
    fontWeight: 500,
    backgroundColor: success ? 'rgba(63, 185, 80, 0.1)' : 'rgba(248, 81, 73, 0.1)',
    color: success ? '#3fb950' : '#f85149',
    borderTop: `1px solid ${success ? 'rgba(63, 185, 80, 0.2)' : 'rgba(248, 81, 73, 0.2)'}`,
    fontFamily: "'Inter', sans-serif",
  }),
};


/* ── Helpers ─────────────────────────────────────────────────────────────── */

function computeHunksFromCode(original, fixed) {
  const origLines = original.split('\n');
  const fixedLines = fixed.split('\n');
  const hunks = [];

  // Basic LCS-style diff (simplified for display)
  let i = 0, j = 0;
  while (i < origLines.length || j < fixedLines.length) {
    if (i < origLines.length && j < fixedLines.length && origLines[i] === fixedLines[j]) {
      // Equal lines — batch them
      const start = i;
      while (i < origLines.length && j < fixedLines.length && origLines[i] === fixedLines[j]) {
        i++;
        j++;
      }
      hunks.push({
        type: 'equal',
        original_start: start + 1,
        original_end: i,
        fixed_start: start + 1,
        fixed_end: j,
        original_lines: origLines.slice(start, i),
        fixed_lines: fixedLines.slice(start, j),
      });
    } else {
      // Difference — find next match
      const origStart = i;
      const fixedStart = j;

      // Look ahead for a matching line
      let foundMatch = false;
      for (let lookAhead = 1; lookAhead < 10 && !foundMatch; lookAhead++) {
        if (i + lookAhead < origLines.length && j + lookAhead < fixedLines.length
            && origLines[i + lookAhead] === fixedLines[j + lookAhead]) {
          // Collect the differing lines
          hunks.push({
            type: 'replace',
            original_start: origStart + 1,
            original_end: i + lookAhead,
            fixed_start: fixedStart + 1,
            fixed_end: j + lookAhead,
            original_lines: origLines.slice(origStart, i + lookAhead),
            fixed_lines: fixedLines.slice(fixedStart, j + lookAhead),
          });
          i += lookAhead;
          j += lookAhead;
          foundMatch = true;
        }
      }

      if (!foundMatch) {
        // No match found nearby — treat rest as replacement
        if (i < origLines.length && j < fixedLines.length) {
          hunks.push({
            type: 'replace',
            original_start: i + 1,
            original_end: i + 1,
            fixed_start: j + 1,
            fixed_end: j + 1,
            original_lines: [origLines[i]],
            fixed_lines: [fixedLines[j]],
          });
          i++;
          j++;
        } else if (i < origLines.length) {
          hunks.push({
            type: 'delete',
            original_start: i + 1,
            original_end: i + 1,
            fixed_start: j + 1,
            fixed_end: j,
            original_lines: [origLines[i]],
            fixed_lines: [],
          });
          i++;
        } else {
          hunks.push({
            type: 'insert',
            original_start: i + 1,
            original_end: i,
            fixed_start: j + 1,
            fixed_end: j + 1,
            original_lines: [],
            fixed_lines: [fixedLines[j]],
          });
          j++;
        }
      }
    }
  }

  return hunks;
}


/* ── Component ───────────────────────────────────────────────────────────── */

export default function DiffViewer({
  originalCode = '',
  fixedCode = '',
  filePath = 'unknown.py',
  hunks: externalHunks = null,
  stats: externalStats = null,
  gitAvailable = false,
  onApplyFix = null,
  onClose = null,
}) {
  const [viewMode, setViewMode] = useState('split'); // 'split' | 'unified'
  const [expandedBlocks, setExpandedBlocks] = useState(new Set());
  const [applying, setApplying] = useState(false);
  const [applyResult, setApplyResult] = useState(null);

  // Use server hunks if provided, otherwise compute client-side
  const hunks = useMemo(() => {
    if (externalHunks && externalHunks.length > 0) return externalHunks;
    if (!originalCode && !fixedCode) return [];
    return computeHunksFromCode(originalCode, fixedCode);
  }, [originalCode, fixedCode, externalHunks]);

  const stats = useMemo(() => {
    if (externalStats) return externalStats;
    let additions = 0, deletions = 0, modifications = 0;
    hunks.forEach(h => {
      if (h.type === 'insert') additions += (h.fixed_lines?.length || 0);
      else if (h.type === 'delete') deletions += (h.original_lines?.length || 0);
      else if (h.type === 'replace') {
        modifications += Math.max(h.original_lines?.length || 0, h.fixed_lines?.length || 0);
      }
    });
    return { additions, deletions, modifications };
  }, [hunks, externalStats]);

  const COLLAPSE_THRESHOLD = 8;

  const toggleExpand = useCallback((idx) => {
    setExpandedBlocks(prev => {
      const next = new Set(prev);
      next.has(idx) ? next.delete(idx) : next.add(idx);
      return next;
    });
  }, []);

  const handleApply = useCallback(async () => {
    if (!onApplyFix || applying) return;
    setApplying(true);
    setApplyResult(null);
    try {
      const result = await onApplyFix();
      setApplyResult(result);
    } catch (err) {
      setApplyResult({ success: false, message: err.message || 'Apply failed' });
    } finally {
      setApplying(false);
    }
  }, [onApplyFix, applying]);

  const fileName = filePath.split(/[/\\]/).pop() || 'file.py';

  /* ── Render Split View ─────────────────────────────────────────────── */
  const renderSplitView = () => (
    <div style={styles.splitContainer}>
      {/* Original pane */}
      <div style={styles.splitPane}>
        <div style={styles.paneHeader('original')}>⊖ Original</div>
        {hunks.map((hunk, idx) => {
          const isEqual = hunk.type === 'equal';
          const lines = hunk.original_lines || [];
          const shouldCollapse = isEqual && lines.length > COLLAPSE_THRESHOLD && !expandedBlocks.has(idx);

          if (shouldCollapse) {
            return (
              <div key={`orig-${idx}`} style={styles.collapsedBlock} onClick={() => toggleExpand(idx)}>
                ⋯ {lines.length} unchanged lines (click to expand)
              </div>
            );
          }

          return lines.map((line, lineIdx) => (
            <div key={`orig-${idx}-${lineIdx}`} style={styles.lineRow(hunk.type === 'replace' ? 'delete' : hunk.type)}>
              <div style={styles.lineNumber}>
                {(hunk.original_start || 0) + lineIdx}
              </div>
              <div style={styles.lineMarker(hunk.type === 'delete' || hunk.type === 'replace' ? 'delete' : 'equal')}>
                {hunk.type === 'delete' || hunk.type === 'replace' ? '−' : ' '}
              </div>
              <div style={styles.lineContent(hunk.type === 'replace' ? 'delete' : hunk.type)}>
                {line}
              </div>
            </div>
          ));
        })}
      </div>

      {/* Fixed pane */}
      <div>
        <div style={styles.paneHeader('fixed')}>⊕ Fixed</div>
        {hunks.map((hunk, idx) => {
          const isEqual = hunk.type === 'equal';
          const lines = hunk.fixed_lines || [];
          const shouldCollapse = isEqual && lines.length > COLLAPSE_THRESHOLD && !expandedBlocks.has(idx);

          if (shouldCollapse) {
            return (
              <div key={`fix-${idx}`} style={styles.collapsedBlock} onClick={() => toggleExpand(idx)}>
                ⋯ {lines.length} unchanged lines (click to expand)
              </div>
            );
          }

          if (hunk.type === 'delete') {
            // Show empty placeholder lines for deleted lines
            return (hunk.original_lines || []).map((_, lineIdx) => (
              <div key={`fix-${idx}-${lineIdx}`} style={{ ...styles.lineRow('delete'), opacity: 0.3 }}>
                <div style={styles.lineNumber}></div>
                <div style={styles.lineMarker('equal')}> </div>
                <div style={styles.lineContent('equal')}></div>
              </div>
            ));
          }

          return lines.map((line, lineIdx) => (
            <div key={`fix-${idx}-${lineIdx}`} style={styles.lineRow(hunk.type === 'replace' ? 'insert' : hunk.type)}>
              <div style={styles.lineNumber}>
                {(hunk.fixed_start || 0) + lineIdx}
              </div>
              <div style={styles.lineMarker(hunk.type === 'insert' || hunk.type === 'replace' ? 'insert' : 'equal')}>
                {hunk.type === 'insert' || hunk.type === 'replace' ? '+' : ' '}
              </div>
              <div style={styles.lineContent(hunk.type === 'replace' ? 'insert' : hunk.type)}>
                {line}
              </div>
            </div>
          ));
        })}
      </div>
    </div>
  );


  /* ── Render Unified View ───────────────────────────────────────────── */
  const renderUnifiedView = () => (
    <div style={{ minWidth: '600px' }}>
      {hunks.map((hunk, idx) => {
        const isEqual = hunk.type === 'equal';
        const origLines = hunk.original_lines || [];
        const fixedLines = hunk.fixed_lines || [];

        if (isEqual) {
          const shouldCollapse = origLines.length > COLLAPSE_THRESHOLD && !expandedBlocks.has(idx);
          if (shouldCollapse) {
            return (
              <div key={`uni-${idx}`} style={styles.collapsedBlock} onClick={() => toggleExpand(idx)}>
                ⋯ {origLines.length} unchanged lines (click to expand)
              </div>
            );
          }
          return origLines.map((line, li) => (
            <div key={`uni-${idx}-eq-${li}`} style={styles.lineRow('equal')}>
              <div style={styles.lineNumber}>{(hunk.original_start || 0) + li}</div>
              <div style={styles.lineNumber}>{(hunk.fixed_start || 0) + li}</div>
              <div style={styles.lineMarker('equal')}> </div>
              <div style={styles.lineContent('equal')}>{line}</div>
            </div>
          ));
        }

        // Show deletions then insertions
        const rows = [];
        origLines.forEach((line, li) => {
          rows.push(
            <div key={`uni-${idx}-del-${li}`} style={styles.lineRow('delete')}>
              <div style={styles.lineNumber}>{(hunk.original_start || 0) + li}</div>
              <div style={styles.lineNumber}></div>
              <div style={styles.lineMarker('delete')}>−</div>
              <div style={styles.lineContent('delete')}>{line}</div>
            </div>
          );
        });
        fixedLines.forEach((line, li) => {
          rows.push(
            <div key={`uni-${idx}-add-${li}`} style={styles.lineRow('insert')}>
              <div style={styles.lineNumber}></div>
              <div style={styles.lineNumber}>{(hunk.fixed_start || 0) + li}</div>
              <div style={styles.lineMarker('insert')}>+</div>
              <div style={styles.lineContent('insert')}>{line}</div>
            </div>
          );
        });
        return rows;
      })}
    </div>
  );


  /* ── Main render ───────────────────────────────────────────────────── */
  return (
    <div style={styles.overlay} onClick={(e) => e.target === e.currentTarget && onClose?.()}>
      <style>{`
        @keyframes diffFadeIn {
          from { opacity: 0; transform: scale(0.97); }
          to   { opacity: 1; transform: scale(1); }
        }
        .diff-btn-secondary:hover {
          background-color: rgba(139, 148, 158, 0.15) !important;
        }
        .diff-btn-primary:hover {
          filter: brightness(1.15);
          box-shadow: 0 4px 16px rgba(35, 134, 54, 0.4) !important;
        }
        .diff-scrollbar::-webkit-scrollbar {
          width: 8px;
          height: 8px;
        }
        .diff-scrollbar::-webkit-scrollbar-track {
          background: transparent;
        }
        .diff-scrollbar::-webkit-scrollbar-thumb {
          background: rgba(139, 148, 158, 0.3);
          border-radius: 4px;
        }
      `}</style>

      <div style={styles.container}>
        {/* Header */}
        <div style={styles.header}>
          <div style={styles.headerLeft}>
            <div style={styles.headerIcon}>📋</div>
            <div>
              <div style={styles.headerTitle}>Patch Review</div>
              <div style={styles.headerFile}>{filePath}</div>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div style={styles.toggleGroup}>
              <button
                style={styles.toggleBtn(viewMode === 'split')}
                onClick={() => setViewMode('split')}
              >
                Split
              </button>
              <button
                style={styles.toggleBtn(viewMode === 'unified')}
                onClick={() => setViewMode('unified')}
              >
                Unified
              </button>
            </div>
          </div>
        </div>

        {/* Stats bar */}
        <div style={styles.statsBar}>
          <span style={styles.statBadge('#3fb950')}>+{stats.additions || 0} additions</span>
          <span style={styles.statBadge('#f85149')}>−{stats.deletions || 0} deletions</span>
          {(stats.modifications > 0) && (
            <span style={styles.statBadge('#d29922')}>~{stats.modifications} modified</span>
          )}
          <span style={{ flex: 1 }} />
          <span style={{ fontSize: '12px', color: '#8b949e' }}>
            {fileName}
          </span>
        </div>

        {/* Diff body */}
        <div style={styles.diffBody} className="diff-scrollbar">
          {viewMode === 'split' ? renderSplitView() : renderUnifiedView()}
        </div>

        {/* Apply result banner */}
        {applyResult && (
          <div style={styles.resultBanner(applyResult.success)}>
            <span>{applyResult.success ? '✓' : '✗'}</span>
            <span>{applyResult.message}</span>
            {applyResult.branch_name && (
              <code style={{
                fontSize: '12px',
                padding: '2px 6px',
                borderRadius: '4px',
                backgroundColor: 'rgba(56, 139, 253, 0.1)',
                color: '#58a6ff',
                marginLeft: '8px',
              }}>
                {applyResult.branch_name}
              </code>
            )}
            {applyResult.commit_sha && (
              <code style={{
                fontSize: '12px',
                padding: '2px 6px',
                borderRadius: '4px',
                backgroundColor: 'rgba(139, 148, 158, 0.1)',
                color: '#8b949e',
                marginLeft: '4px',
              }}>
                {applyResult.commit_sha}
              </code>
            )}
          </div>
        )}

        {/* Footer */}
        <div style={styles.footer}>
          <div style={styles.footerInfo}>
            {gitAvailable && <span style={styles.gitBadge}>⎇ Git Safe Mode</span>}
            {!gitAvailable && (
              <span style={{ ...styles.gitBadge, backgroundColor: 'rgba(210, 153, 34, 0.1)', color: '#d29922', borderColor: 'rgba(210, 153, 34, 0.2)' }}>
                ⚠ Direct Mode (no Git)
              </span>
            )}
            <span style={{ color: '#484f58', fontSize: '11px' }}>
              {gitAvailable
                ? 'Fix will be committed on an isolated branch'
                : 'Fix will be applied directly with .bak backup'}
            </span>
          </div>

          <div style={styles.footerActions}>
            {onClose && (
              <button
                className="diff-btn-secondary"
                style={styles.btnSecondary}
                onClick={onClose}
              >
                Cancel
              </button>
            )}
            {onApplyFix && (
              <button
                className={applying ? '' : 'diff-btn-primary'}
                style={applying ? styles.btnApplying : styles.btnPrimary}
                onClick={handleApply}
                disabled={applying || applyResult?.success}
              >
                {applying ? '⟳ Applying...' : applyResult?.success ? '✓ Applied' : '⊕ Apply Fix'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
