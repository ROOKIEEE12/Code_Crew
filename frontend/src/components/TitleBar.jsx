import React from 'react'
import {
  Code2,
  Download,
  Eye,
  EyeOff,
  Sparkles,
  Terminal,
  Layers,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react'

export default function TitleBar({
  projectName,
  backendStatus,
  onDownloadZip,
  hasFiles,
  livePreview,
  onToggleLivePreview,
  hasHtml,
  onNewProject,
}) {
  return (
    <header className="ide-titlebar">
      {/* Left: Brand & Menu */}
      <div className="titlebar-left">
        <div className="ide-brand-badge">
          <Code2 size={16} color="#818cf8" />
          <span className="brand-name">CodeCrew</span>
          <span className="brand-sub">STUDIO</span>
        </div>

        <nav className="titlebar-menu">
          <span className="menu-item" onClick={onNewProject}>New Build</span>
          <span className="menu-item">Project</span>
          <span className="menu-item">Swarm</span>
          <span className="menu-item">Terminal</span>
          <span className="menu-item">Help</span>
        </nav>
      </div>

      {/* Center: Active Project Indicator */}
      <div className="titlebar-center">
        <div className="project-pill">
          <span className="pill-dot"></span>
          <span className="pill-text">
            {projectName ? `${projectName} — Antigravity IDE` : 'Antigravity Multi-Agent Studio'}
          </span>
        </div>
      </div>

      {/* Right: Quick Controls & Status */}
      <div className="titlebar-right">
        {hasHtml && (
          <button
            className={`titlebar-action-btn ${livePreview ? 'active' : ''}`}
            onClick={onToggleLivePreview}
            title={livePreview ? 'Switch to Code View' : 'Open Live Interactive Web Preview'}
          >
            {livePreview ? <EyeOff size={14} /> : <Eye size={14} />}
            <span>{livePreview ? 'Code' : 'Live Preview'}</span>
          </button>
        )}

        {hasFiles && onDownloadZip && (
          <button
            className="titlebar-action-btn"
            onClick={onDownloadZip}
            title="Download full project as .ZIP"
          >
            <Download size={14} />
            <span>Download ZIP</span>
          </button>
        )}

        <div className="connection-badge">
          <span className={`status-indicator ${backendStatus === 'online' ? 'online' : 'offline'}`} />
          <span className="status-label">{backendStatus === 'online' ? 'Engine Online' : 'Engine Offline'}</span>
        </div>
      </div>
    </header>
  )
}
