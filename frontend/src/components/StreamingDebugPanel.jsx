/* eslint-disable */
/**
 * StreamingDebugPanel — Real-time SSE debug pipeline visualization.
 *
 * Shows a live feed of pipeline stages with animated progress,
 * typing-effect messages, and a progress bar. Renders the final
 * result once the pipeline completes.
 */
import React, { useEffect, useRef } from 'react'
import { useStream } from '../lib/useStream'

const STAGE_ICONS = {
  init: '🚀',
  read_file: '📄',
  context_knowledge: '🧠',
  analytics: '🔍',
  fix_generation: '🔧',
  synthesis: '⚗️',
  confidence: '📊',
  finalize: '✅',
  cache_hit: '⚡',
}

/* ── Inline styles (no Tailwind dependency) ────────────────────────────── */

const styles = {
  container: {
    fontFamily: "'Inter', 'Segoe UI', system-ui, sans-serif",
    background: 'rgba(15, 15, 25, 0.85)',
    backdropFilter: 'blur(16px)',
    border: '1px solid rgba(255,255,255,0.08)',
    borderRadius: '16px',
    padding: '24px',
    color: '#e2e8f0',
    maxWidth: '100%',
    overflow: 'hidden',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: '16px',
  },
  title: {
    fontSize: '14px',
    fontWeight: 600,
    letterSpacing: '0.5px',
    textTransform: 'uppercase',
    color: '#94a3b8',
    margin: 0,
  },
  badge: (isComplete, hasError) => ({
    padding: '4px 12px',
    borderRadius: '20px',
    fontSize: '11px',
    fontWeight: 600,
    background: hasError
      ? 'rgba(239, 68, 68, 0.2)'
      : isComplete
        ? 'rgba(34, 197, 94, 0.2)'
        : 'rgba(99, 102, 241, 0.2)',
    color: hasError ? '#f87171' : isComplete ? '#4ade80' : '#818cf8',
    border: `1px solid ${hasError ? 'rgba(239,68,68,0.3)' : isComplete ? 'rgba(34,197,94,0.3)' : 'rgba(99,102,241,0.3)'}`,
  }),
  progressBarOuter: {
    width: '100%',
    height: '4px',
    background: 'rgba(255,255,255,0.06)',
    borderRadius: '4px',
    marginBottom: '20px',
    overflow: 'hidden',
  },
  progressBarInner: (percent) => ({
    width: `${percent}%`,
    height: '100%',
    background: 'linear-gradient(90deg, #6366f1, #a78bfa, #c084fc)',
    borderRadius: '4px',
    transition: 'width 0.5s cubic-bezier(0.4, 0, 0.2, 1)',
  }),
  feed: {
    maxHeight: '300px',
    overflowY: 'auto',
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
    paddingRight: '4px',
  },
  feedItem: (isLatest) => ({
    display: 'flex',
    alignItems: 'flex-start',
    gap: '10px',
    padding: '8px 12px',
    borderRadius: '10px',
    background: isLatest ? 'rgba(99, 102, 241, 0.08)' : 'transparent',
    border: isLatest ? '1px solid rgba(99, 102, 241, 0.15)' : '1px solid transparent',
    transition: 'all 0.3s ease',
    opacity: isLatest ? 1 : 0.6,
    fontSize: '13px',
    lineHeight: '1.5',
  }),
  feedIcon: {
    fontSize: '16px',
    flexShrink: 0,
    marginTop: '2px',
  },
  feedMessage: {
    flex: 1,
    wordBreak: 'break-word',
  },
  feedTime: {
    fontSize: '11px',
    color: '#64748b',
    flexShrink: 0,
    marginTop: '2px',
    fontVariantNumeric: 'tabular-nums',
  },
  currentStage: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '12px 16px',
    borderRadius: '12px',
    background: 'rgba(99, 102, 241, 0.06)',
    border: '1px solid rgba(99, 102, 241, 0.12)',
    marginBottom: '16px',
    fontSize: '14px',
    fontWeight: 500,
  },
  spinner: {
    width: '16px',
    height: '16px',
    border: '2px solid rgba(99, 102, 241, 0.3)',
    borderTopColor: '#818cf8',
    borderRadius: '50%',
    animation: 'spin 0.8s linear infinite',
    flexShrink: 0,
  },
  errorBox: {
    padding: '12px 16px',
    borderRadius: '12px',
    background: 'rgba(239, 68, 68, 0.08)',
    border: '1px solid rgba(239, 68, 68, 0.2)',
    color: '#fca5a5',
    fontSize: '13px',
    marginTop: '12px',
  },
}

function formatEventTime(timestamp) {
  if (!timestamp) return ''
  const d = new Date(timestamp * 1000)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export default function StreamingDebugPanel({ onResult, onError }) {
  const {
    events,
    currentStage,
    progress,
    result,
    error,
    isComplete,
    isConnecting,
    percentComplete,
    startStream,
    reset,
  } = useStream()

  const feedEndRef = useRef(null)

  // Auto-scroll the event feed
  useEffect(() => {
    feedEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events.length])

  // Propagate result/error to parent
  useEffect(() => {
    if (result && onResult) onResult(result)
  }, [result, onResult])

  useEffect(() => {
    if (error && onError) onError(error)
  }, [error, onError])

  // Filter to only show stage/progress events in the feed
  const stageEvents = events.filter(e => e.type === 'stage' || e.type === 'progress')

  const statusText = isConnecting
    ? 'Connecting...'
    : isComplete
      ? error ? 'Failed' : 'Complete'
      : `${percentComplete}%`

  return (
    <>
      {/* Keyframes for spinner (injected once) */}
      <style>{`@keyframes spin { to { transform: rotate(360deg) } }`}</style>

      <div style={styles.container}>
        {/* Header */}
        <div style={styles.header}>
          <h4 style={styles.title}>Pipeline Stream</h4>
          <span style={styles.badge(isComplete, !!error)}>{statusText}</span>
        </div>

        {/* Progress bar */}
        <div style={styles.progressBarOuter}>
          <div style={styles.progressBarInner(percentComplete)} />
        </div>

        {/* Current stage (live indicator) */}
        {currentStage && !isComplete && (
          <div style={styles.currentStage}>
            <div style={styles.spinner} />
            <span>{currentStage}</span>
          </div>
        )}

        {/* Event feed */}
        <div style={styles.feed}>
          {stageEvents.map((evt, i) => {
            const isLatest = i === stageEvents.length - 1 && !isComplete
            const icon = STAGE_ICONS[evt.stage] || '▸'
            return (
              <div key={i} style={styles.feedItem(isLatest)}>
                <span style={styles.feedIcon}>{icon}</span>
                <span style={styles.feedMessage}>{evt.message}</span>
                <span style={styles.feedTime}>{formatEventTime(evt.timestamp)}</span>
              </div>
            )
          })}
          <div ref={feedEndRef} />
        </div>

        {/* Error display */}
        {error && (
          <div style={styles.errorBox}>
            ⚠️ {error}
          </div>
        )}
      </div>
    </>
  )
}

/**
 * Helper: trigger a streaming debug from outside the component.
 * Typically called from App.jsx or a parent component.
 *
 * Example:
 *   const streamRef = useRef()
 *   <StreamingDebugPanel ref={streamRef} onResult={handleResult} />
 *   streamRef.current.startDebug({ file_path: '...', mode: 'fast' })
 */
export { useStream }
