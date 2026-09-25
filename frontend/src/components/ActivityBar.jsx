import React from 'react'
import {
  Files,
  Archive,
  Bot,
  TerminalSquare,
  Settings,
  ShieldCheck,
} from 'lucide-react'

export default function ActivityBar({
  activeNav,
  setActiveNav,
  projectCount = 0,
  terminalOpen,
  onToggleTerminal,
}) {
  return (
    <aside className="ide-activity-bar">
      <div className="activity-top">
        <button
          className={`activity-icon-btn ${activeNav === 'explorer' ? 'active' : ''}`}
          onClick={() => setActiveNav('explorer')}
          title="Explorer (Project Files)"
        >
          <Files size={22} />
        </button>

        <button
          className={`activity-icon-btn ${activeNav === 'archive' ? 'active' : ''}`}
          onClick={() => setActiveNav('archive')}
          title={`Saved Projects Archive (${projectCount})`}
        >
          <Archive size={22} />
          {projectCount > 0 && <span className="activity-badge">{projectCount}</span>}
        </button>

        <button
          className={`activity-icon-btn ${activeNav === 'agents' ? 'active' : ''}`}
          onClick={() => setActiveNav('agents')}
          title="Specialist Agent Swarm Roster"
        >
          <Bot size={22} />
        </button>

        <button
          className={`activity-icon-btn ${terminalOpen ? 'terminal-active' : ''}`}
          onClick={onToggleTerminal}
          title={terminalOpen ? 'Hide Terminal / Logs' : 'Show Terminal / Logs'}
        >
          <TerminalSquare size={22} />
        </button>
      </div>

      <div className="activity-bottom">
        <button
          className="activity-icon-btn"
          title="Auditor Security & Fact Verification Guard"
          style={{ color: '#10b981' }}
        >
          <ShieldCheck size={20} />
        </button>

        <button
          className="activity-icon-btn"
          title="Settings / Architecture Config"
        >
          <Settings size={20} />
        </button>
      </div>
    </aside>
  )
}
