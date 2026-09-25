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

  return (
    <aside className="ide-copilot-panel">
      {/* 1. Header */}
      <div className="copilot-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Bot size={17} color="#818cf8" />
          <span className="copilot-title">Agent Copilot</span>
        </div>
        <span className="copilot-model-pill">Gemini 3.8 Flash</span>
      </div>

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
