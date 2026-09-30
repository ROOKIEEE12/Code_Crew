import React, { useState } from 'react'
import {
  Rocket,
  Sparkles,
  Bot,
  Loader2,
  CheckCircle2,
  Clock,
  Send,
  AlertCircle,
  Cpu,
  Layers,
} from 'lucide-react'

const SPECIALIST_AGENTS = [
  { id: 'planner', name: 'Architect', avatar: '🧠', accent: '#8b5cf6' },
  { id: 'coder', name: 'Coder', avatar: '💻', accent: '#3b82f6' },
  { id: 'auditor', name: 'Auditor', avatar: '🔍', accent: '#10b981' },
  { id: 'tester', name: 'QA Tester', avatar: '🧪', accent: '#f59e0b' },
  { id: 'debugger', name: 'Debugger', avatar: '🛠️', accent: '#ef4444' },
  { id: 'reviewer', name: 'Writer', avatar: '📝', accent: '#06b6d4' },
]

export default function CopilotPanel({
  pipelineState,
  isBuilding,
  isIterating,
  onLaunchBuild,
  onLaunchIteration,
  prompt,
  setPrompt,
  triagePlan,
  projectId,
  errorMessage,
}) {
  const isWorking = isBuilding || isIterating

  const getAgentStatus = (agentId) => {
    const s = pipelineState.state
    const reqAgents = pipelineState.required_agents

    if (s === 'completed') return { status: 'complete', text: 'Done', color: '#10b981' }

    if (s === 'triaging') {
      return { status: 'idle', text: 'Triaging', color: '#6366f1' }
    }

    if (reqAgents && Array.isArray(reqAgents) && !reqAgents.includes(agentId)) {
      return { status: 'idle', text: 'Standby', color: 'var(--text-dim)' }
    }

    if (agentId === 'planner') {
      if (s === 'planning') return { status: 'working', text: 'Designing', color: '#8b5cf6' }
      if (['coding', 'auditing', 'testing', 'debugging', 'documenting'].includes(s))
        return { status: 'complete', text: 'Done', color: '#10b981' }
    }

    if (agentId === 'coder') {
      if (s === 'coding')
        return {
          status: 'working',
          text: pipelineState.wave ? `Wave ${pipelineState.wave}` : 'Coding',
          color: '#3b82f6',
        }
      if (['testing', 'debugging', 'documenting'].includes(s))
        return { status: 'complete', text: 'Done', color: '#10b981' }
    }

    if (agentId === 'auditor') {
      if (s === 'coding' || s === 'auditing')
        return { status: 'working', text: 'Auditing', color: '#10b981' }
      if (['testing', 'debugging', 'documenting'].includes(s))
        return { status: 'complete', text: 'Done', color: '#10b981' }
    }

    if (agentId === 'tester') {
      if (s === 'testing') return { status: 'working', text: 'Testing', color: '#f59e0b' }
      if (['documenting'].includes(s))
        return { status: 'complete', text: 'Done', color: '#10b981' }
    }

    if (agentId === 'debugger') {
      if (s === 'debugging') return { status: 'working', text: 'Fixing', color: '#ef4444' }
      if (['documenting'].includes(s))
        return { status: 'complete', text: 'Done', color: '#10b981' }
    }

    if (agentId === 'reviewer') {
      if (s === 'documenting') return { status: 'working', text: 'Writing Docs', color: '#06b6d4' }
    }

    return { status: 'idle', text: 'Standby', color: 'var(--text-dim)' }
  }

  const handleSubmit = () => {
    if (!prompt.trim() || isWorking) return
    if (projectId) {
      onLaunchIteration(prompt)
    } else {
      onLaunchBuild(prompt)
    }
  }

  const [modelPoolStatus, setModelPoolStatus] = useState(null)
  const [showPoolModal, setShowPoolModal] = useState(false)

  React.useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await fetch('/api/models/status')
        if (res.ok) {
          const data = await res.json()
          setModelPoolStatus(data)
        }
      } catch (e) {
        // Silently keep default
      }
    }
    fetchStatus()
    const timer = setInterval(fetchStatus, 6000)
    return () => clearInterval(timer)
  }, [])

  return (
    <aside className="ide-copilot-panel">
      {/* 1. Header */}
      <div className="copilot-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Bot size={17} color="#818cf8" />
          <span className="copilot-title">Agent Copilot</span>
        </div>
        <button
          className="copilot-model-pill"
          onClick={() => setShowPoolModal(!showPoolModal)}
          title="Click to view Gemini Swarm Models & Quota Refresh Status"
          style={{
            cursor: 'pointer',
            border: 'none',
            display: 'flex',
            alignItems: 'center',
            gap: '5px',
          }}
        >
          <span
            style={{
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              background: modelPoolStatus?.cooldown_models > 0 ? '#f59e0b' : '#10b981',
              boxShadow: modelPoolStatus?.cooldown_models > 0 ? '0 0 6px #f59e0b' : '0 0 6px #10b981',
              display: 'inline-block',
            }}
          />
          {modelPoolStatus
            ? `Swarm: ${modelPoolStatus.active_models}/${modelPoolStatus.total_models} Free`
            : 'Gemini Swarm'}
        </button>
      </div>

      {/* 1.1 Expandable Model Pool & Quota Guardian Drawer */}
      {showPoolModal && (
        <div
          style={{
            background: 'var(--panel-bg, #0f172a)',
            borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
            padding: '12px 14px',
            fontSize: '0.75rem',
            boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
            zIndex: 20,
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <div style={{ fontWeight: 600, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Sparkles size={13} color="#818cf8" />
              <span>Gemini Quota Guardian</span>
            </div>
            <span
              style={{
                fontSize: '0.68rem',
                color: '#10b981',
                background: 'rgba(16, 185, 129, 0.12)',
                padding: '2px 6px',
                borderRadius: '4px',
                fontWeight: 600,
              }}
            >
              Zero-Downtime Fallback
            </span>
          </div>

          <p style={{ margin: '0 0 10px 0', color: 'var(--text-muted, #94a3b8)', fontSize: '0.7rem', lineHeight: '1.4' }}>
            Every free Gemini model is active in rotation. If any model hits a 429 quota limit, CodeCrew automatically shifts to the next model and auto-refreshes tokens in cooldown!
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '200px', overflowY: 'auto' }}>
            {modelPoolStatus?.pool?.map((m) => {
              const isCooling = m.status === 'cooldown'
              const isReady = m.status === 'ready'
              return (
                <div
                  key={m.model_id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '5px 8px',
                    borderRadius: '6px',
                    background: 'rgba(255, 255, 255, 0.03)',
                    border: '1px solid rgba(255, 255, 255, 0.05)',
                  }}
                >
                  <div style={{ display: 'flex', flexDirection: 'column' }}>
                    <span style={{ fontWeight: 600, color: '#e2e8f0', fontSize: '0.72rem' }}>
                      {m.name || m.model_id}
                    </span>
                    <span style={{ fontSize: '0.62rem', color: '#64748b' }}>
                      {m.favored_roles?.length > 0 ? `Assigned: ${m.favored_roles.join(', ')}` : 'Fallback Pool'}
                    </span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    {m.success_count > 0 && (
                      <span style={{ fontSize: '0.62rem', color: '#818cf8' }}>
                        {m.success_count} runs
                      </span>
                    )}
                    <span
                      style={{
                        fontSize: '0.62rem',
                        fontWeight: 600,
                        padding: '2px 6px',
                        borderRadius: '4px',
                        background: isCooling
                          ? 'rgba(245, 158, 11, 0.15)'
                          : isReady
                          ? 'rgba(16, 185, 129, 0.15)'
                          : 'rgba(239, 68, 68, 0.15)',
                        color: isCooling ? '#f59e0b' : isReady ? '#10b981' : '#ef4444',
                      }}
                    >
                      {isCooling ? `Cooldown (${m.seconds_remaining}s)` : isReady ? 'Ready' : 'Retired'}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* 2. Swarm Live Status Radar */}
      <div className="swarm-radar-card">
        <div className="radar-header">
          <span style={{ fontSize: '0.72rem', textTransform: 'uppercase', color: 'var(--text-muted)', fontWeight: 600 }}>
            Specialist Swarm (6)
          </span>
          <span
            className="radar-state-pill"
            style={{
              color: isWorking ? '#818cf8' : pipelineState.state === 'completed' ? '#10b981' : 'var(--text-dim)',
            }}
          >
            {isWorking ? (
              <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <Loader2 size={10} className="spin-slow" /> {pipelineState.state}
              </span>
            ) : pipelineState.state === 'completed' ? (
              'Pipeline Ready'
            ) : (
              'Idle'
            )}
          </span>
        </div>

        <div className="radar-grid">
          {SPECIALIST_AGENTS.map((agent) => {
            const st = getAgentStatus(agent.id)
            const isAgentActive = st.status === 'working'
            const isAgentDone = st.status === 'complete'

            return (
              <div
                key={agent.id}
                className={`radar-item ${isAgentActive ? 'active' : ''} ${isAgentDone ? 'done' : ''}`}
                style={{
                  borderColor: isAgentActive ? agent.accent : undefined,
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span>{agent.avatar}</span>
                  <span className="agent-short-name">{agent.name}</span>
                </div>
                <span
                  className="agent-mini-status"
                  style={{ color: isAgentActive ? agent.accent : isAgentDone ? '#10b981' : 'var(--text-dim)' }}
                >
                  {st.text}
                </span>
              </div>
            )
          })}
        </div>
      </div>

      {/* 3. Orchestrator Triage Intelligence Banner */}
      {triagePlan && (
        <div className="copilot-triage-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
            <span style={{ fontSize: '1rem' }}>🎯</span>
            <strong style={{ fontSize: '0.8rem', color: '#818cf8' }}>Orchestrator Routing</strong>
            <span className="copilot-tag intent">{triagePlan.intent?.toUpperCase()}</span>
          </div>
          <div style={{ fontSize: '0.75rem', color: '#10b981', marginBottom: '4px' }}>
            Dispatched: {triagePlan.required_agents?.join(', ')}
          </div>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)', margin: 0 }}>
            {triagePlan.explanation}
          </p>
        </div>
      )}

      {/* 4. Chat & Activity History Area */}
      <div className="copilot-feed">
        <div className="copilot-welcome-message">
          <div className="copilot-avatar">▲</div>
          <div className="copilot-bubble">
            {projectId ? (
              <p>
                <strong>{projectId}</strong> is loaded in the workspace. Describe any feature additions, UI modifications, or bug fixes!
              </p>
            ) : (
              <p>
                Welcome to <strong>CodeCrew Antigravity Studio</strong>. Describe what you'd like built, and the 6 agents will plan, code, audit, test, and document it for you.
              </p>
            )}
          </div>
        </div>

        {errorMessage && (
          <div className="copilot-error-card">
            <AlertCircle size={14} />
            <span>{errorMessage}</span>
          </div>
        )}
      </div>

      {/* 5. Prompt Dock */}
      <div className="copilot-dock">
        <textarea
          className="copilot-textarea"
          placeholder={
            projectId
              ? "Ask Orchestrator to modify this project (e.g. 'Add dark mode toggle', 'Fix bug')..."
              : "Describe an application, CLI, or website to build..."
          }
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
              handleSubmit()
            }
          }}
          disabled={isWorking}
          rows={3}
        />

        <div className="dock-action-row">
          <div className="shortcut-hint">
            <kbd>Ctrl</kbd> + <kbd>Enter</kbd>
          </div>

          <button
            className="copilot-send-btn"
            onClick={handleSubmit}
            disabled={isWorking || !prompt.trim()}
          >
            {isWorking ? (
              <>
                <Loader2 size={14} className="spin-slow" />
                <span>Working...</span>
              </>
            ) : projectId ? (
              <>
                <Sparkles size={14} />
                <span>Apply Changes</span>
              </>
            ) : (
              <>
                <Rocket size={14} />
                <span>Deploy Swarm</span>
              </>
            )}
          </button>
        </div>
      </div>
    </aside>
  )
}
