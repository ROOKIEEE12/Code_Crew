import React from 'react'
import { CheckCircle2, Clock, Loader2, AlertTriangle } from 'lucide-react'

const AGENT_ROSTER = [
  {
    id: 'planner',
    name: 'Principal Architect',
    role: 'System Design & Decomposition',
    avatar: '🧠',
    accent: '#8b5cf6',
  },
  {
    id: 'coder',
    name: 'Staff Polyglot Engineer',
    role: 'Zero-Bloat Implementation',
    avatar: '💻',
    accent: '#3b82f6',
  },
  {
    id: 'auditor',
    name: 'Code Auditor & Fact-Checker',
    role: 'Line-by-Line Fact & Logic Audit',
    avatar: '🔍',
    accent: '#10b981',
  },
  {
    id: 'tester',
    name: 'QA Automation Lead',
    role: 'PyTest & Multi-File Contracts',
    avatar: '🧪',
    accent: '#f59e0b',
  },
  {
    id: 'debugger',
    name: 'Root Cause Specialist',
    role: 'Surgical Patching & Triage',
    avatar: '🛠️',
    accent: '#ef4444',
  },
  {
    id: 'reviewer',
    name: 'Technical Documentation Lead',
    role: 'Executable README & Setup',
    avatar: '📝',
    accent: '#06b6d4',
  },
]

export default function AgentSwarm({ pipelineState }) {
  const getAgentStatus = (agentId) => {
    const s = pipelineState.state
    if (s === 'completed') return { status: 'complete', text: 'Done', color: '#10b981' }

    if (agentId === 'planner') {
      if (s === 'planning') return { status: 'working', text: 'Architecting', color: '#8b5cf6' }
      if (['coding', 'auditing', 'testing', 'debugging', 'documenting'].includes(s))
        return { status: 'complete', text: 'Plan Ready', color: '#10b981' }
    }

    if (agentId === 'coder') {
      if (s === 'coding')
        return {
          status: 'working',
          text: `Coding Wave ${pipelineState.wave || 1}/${pipelineState.total_waves || 1}`,
          color: '#3b82f6',
        }
      if (['testing', 'debugging', 'documenting'].includes(s))
        return { status: 'complete', text: 'Built', color: '#10b981' }
    }

    if (agentId === 'auditor') {
      if (s === 'coding' || s === 'auditing')
        return { status: 'working', text: 'Fact-Checking', color: '#10b981' }
      if (['testing', 'debugging', 'documenting'].includes(s))
        return { status: 'complete', text: 'Verified', color: '#10b981' }
    }

    if (agentId === 'tester') {
      if (s === 'testing')
        return {
          status: 'working',
          text: `Testing (Try ${pipelineState.attempt || 1})`,
          color: '#f59e0b',
        }
      if (['documenting'].includes(s))
        return { status: 'complete', text: 'Passed', color: '#10b981' }
    }

    if (agentId === 'debugger') {
      if (s === 'debugging')
        return {
          status: 'working',
          text: `Patching (${pipelineState.broken?.length || 1} file)`,
          color: '#ef4444',
        }
      if (['documenting'].includes(s))
        return { status: 'complete', text: 'Resolved', color: '#10b981' }
    }

    if (agentId === 'reviewer') {
      if (s === 'documenting') return { status: 'working', text: 'Documenting', color: '#06b6d4' }
    }

    return { status: 'idle', text: 'Standby', color: 'var(--text-dim)' }
  }

  return (
    <div className="agent-grid">
      {AGENT_ROSTER.map((agent) => {
        const status = getAgentStatus(agent.id)
        const isWorking = status.status === 'working'
        const isDone = status.status === 'complete'

        return (
          <div
            key={agent.id}
            className={`agent-card ${isWorking ? 'active pulse-active' : ''} ${isDone ? 'completed' : ''}`}
            style={{
              borderColor: isWorking ? agent.accent : undefined,
            }}
          >
            <div className="agent-header">
              <span className="agent-avatar">{agent.avatar}</span>
              <span
                className="agent-status-badge"
                style={{
                  background: isWorking
                    ? `${agent.accent}25`
                    : isDone
                    ? 'rgba(16, 185, 129, 0.15)'
                    : 'rgba(255, 255, 255, 0.05)',
                  color: isWorking ? agent.accent : isDone ? '#10b981' : 'var(--text-dim)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                }}
              >
                {isWorking && <Loader2 size={11} className="spin-slow" />}
                {isDone && <CheckCircle2 size={11} />}
                {!isWorking && !isDone && <Clock size={11} />}
                {status.text}
              </span>
            </div>

            <div className="agent-name" style={{ color: isWorking ? '#fff' : 'var(--text-main)' }}>
              {agent.name}
            </div>
            <div className="agent-desc">{agent.role}</div>
          </div>
        )
      })}
    </div>
  )
}
