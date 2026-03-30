/**
 * useStream — React hook for consuming Server-Sent Events from the debug pipeline.
 *
 * Usage:
 *   const { events, currentStage, progress, result, error, isComplete, startStream } = useStream()
 *
 *   // Trigger a streaming debug
 *   await startStream('/debug_stream', { file_path: '...', mode: 'fast' })
 *
 *   // Events arrive in real-time:
 *   events.forEach(e => console.log(e.data.message))
 */
import { useState, useRef, useCallback } from 'react'

const API = import.meta.env.VITE_API_URL || (window.location.port.startsWith('517') ? 'http://127.0.0.1:8001' : '')
const AUTH_TOKEN_KEY = 'auth_token'

export function useStream() {
  const [events, setEvents] = useState([])
  const [currentStage, setCurrentStage] = useState(null)
  const [progress, setProgress] = useState({ stageIndex: 0, totalStages: 6 })
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [isComplete, setIsComplete] = useState(false)
  const [isConnecting, setIsConnecting] = useState(false)
  const [taskId, setTaskId] = useState(null)
  const eventSourceRef = useRef(null)

  const cleanup = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
  }, [])

  const reset = useCallback(() => {
    cleanup()
    setEvents([])
    setCurrentStage(null)
    setProgress({ stageIndex: 0, totalStages: 6 })
    setResult(null)
    setError(null)
    setIsComplete(false)
    setIsConnecting(false)
    setTaskId(null)
  }, [cleanup])

  const startStream = useCallback(async (endpoint, body) => {
    // Reset state
    reset()
    setIsConnecting(true)

    try {
      // Step 1: POST to /debug_stream → get task_id (HTTP 202)
      const token = localStorage.getItem(AUTH_TOKEN_KEY)
      const headers = { 'Content-Type': 'application/json' }
      if (token) headers['Authorization'] = `Bearer ${token}`

      const res = await fetch(`${API}${endpoint}`, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
      })

      if (!res.ok) {
        const errPayload = await res.json().catch(() => ({}))
        throw new Error(errPayload?.detail || `Request failed (${res.status})`)
      }

      const { task_id, stream_url } = await res.json()
      setTaskId(task_id)

      // Step 2: Connect to SSE stream
      const es = new EventSource(`${API}${stream_url}`)
      eventSourceRef.current = es

      const handleEvent = (e) => {
        try {
          const parsed = JSON.parse(e.data)
          const eventData = parsed.data || {}
          const eventType = parsed.event || e.type

          setEvents(prev => [...prev, { type: eventType, ...eventData, timestamp: parsed.timestamp }])

          switch (eventType) {
            case 'stage':
              setCurrentStage(eventData.message)
              if (eventData.stage_index !== undefined) {
                setProgress({
                  stageIndex: eventData.stage_index,
                  totalStages: eventData.total_stages || 6,
                })
              }
              break

            case 'progress':
              setCurrentStage(eventData.message)
              break

            case 'result':
              setResult(eventData.result)
              break

            case 'error':
              setError(eventData.message)
              setIsComplete(true)
              cleanup()
              break

            case 'complete':
              setIsComplete(true)
              cleanup()
              break
          }
        } catch (parseErr) {
          console.warn('[useStream] Failed to parse SSE event:', parseErr)
        }
      }

      // Listen to all named event types
      es.addEventListener('stage', handleEvent)
      es.addEventListener('progress', handleEvent)
      es.addEventListener('partial', handleEvent)
      es.addEventListener('result', handleEvent)
      es.addEventListener('error', handleEvent)
      es.addEventListener('complete', handleEvent)

      // Generic message handler (fallback)
      es.onmessage = handleEvent

      es.onerror = (err) => {
        // EventSource auto-reconnects, but if the connection is permanently
        // closed (readyState === CLOSED) we should clean up
        if (es.readyState === EventSource.CLOSED) {
          if (!isComplete) {
            setError('Stream connection lost.')
            setIsComplete(true)
          }
          cleanup()
        }
      }

      es.onopen = () => {
        setIsConnecting(false)
      }

      return task_id

    } catch (err) {
      setError(err.message)
      setIsComplete(true)
      setIsConnecting(false)
      cleanup()
      return null
    }
  }, [reset, cleanup])

  return {
    events,
    currentStage,
    progress,
    result,
    error,
    isComplete,
    isConnecting,
    taskId,
    startStream,
    reset,
    cleanup,
    /** Percentage (0–100) based on stage progress */
    percentComplete: Math.round((progress.stageIndex / progress.totalStages) * 100),
  }
}
