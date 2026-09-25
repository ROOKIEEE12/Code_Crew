import React from 'react'
import { ShieldCheck, Cpu, FolderGit2, CheckCircle2, AlertCircle } from 'lucide-react'

export default function Navbar({ activeTab, setActiveTab, backendStatus, projectCount }) {
  return (
    <header className="navbar">
      <div className="brand-section">
        <div className="brand-logo">🤖</div>
        <div>
          <h1 className="brand-title">
            Code<span className="text-gradient">Crew</span>
          </h1>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            Autonomous Multi-Agent Engineering Swarm
          </p>
        </div>
      </div>

      <div className="nav-badges">
        {/* Safe GitHub Shield Badge */}
        <div
          className="badge-tag"
          style={{
            background: 'rgba(16, 185, 129, 0.12)',
            color: '#10b981',
            border: '1px solid rgba(16, 185, 129, 0.3)',
          }}
          title="Git Shield active: .env and secrets are protected against GitHub leakage"
        >
          <ShieldCheck size={14} />
          <span>Git Shield: Safe</span>
        </div>

        {/* Backend Status Badge */}
        <div
          className="badge-tag"
          style={{
            background: backendStatus === 'online' ? 'rgba(59, 130, 246, 0.12)' : 'rgba(239, 68, 68, 0.12)',
            color: backendStatus === 'online' ? '#60a5fa' : '#f87171',
            border: `1px solid ${backendStatus === 'online' ? 'rgba(59, 130, 246, 0.3)' : 'rgba(239, 68, 68, 0.3)'}`,
          }}
        >
          {backendStatus === 'online' ? <CheckCircle2 size={13} /> : <AlertCircle size={13} />}
          <span>FastAPI: {backendStatus}</span>
        </div>

        {/* View Switchers */}
        <div style={{ display: 'flex', gap: '6px', background: 'rgba(255,255,255,0.05)', padding: '4px', borderRadius: '10px' }}>
          <button
            onClick={() => setActiveTab('studio')}
            className={`nav-tab-btn ${activeTab === 'studio' ? 'active' : ''}`}
          >
            <Cpu size={15} />
            <span>Live Studio</span>
          </button>
          <button
            onClick={() => setActiveTab('archive')}
            className={`nav-tab-btn ${activeTab === 'archive' ? 'active' : ''}`}
          >
            <FolderGit2 size={15} />
            <span>Projects ({projectCount})</span>
          </button>
        </div>
      </div>
    </header>
  )
}
