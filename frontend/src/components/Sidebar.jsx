import React from 'react'
import {
  Folder,
  FileCode,
  FileText,
  ShieldCheck,
  Download,
  Plus,
  Clock,
  Sparkles,
  ChevronRight,
  ChevronDown,
  Layers,
  Code,
} from 'lucide-react'

export default function Sidebar({
  activeNav,
  files = {},
  selectedFile,
  onSelectFile,
  readme,
  projectId,
  projects = [],
  onLoadProject,
  onDownloadZip,
  onNewProject,
  agents = [],
}) {
  const fileKeys = Object.keys(files || {})

  const getFileIcon = (filename) => {
    const ext = filename.split('.').pop().toLowerCase()
    switch (ext) {
      case 'html':
        return <span style={{ color: '#e34f26', fontSize: '13px', fontWeight: 'bold' }}>&lt;&gt;</span>
      case 'css':
        return <span style={{ color: '#38bdf8', fontSize: '13px', fontWeight: 'bold' }}>#</span>
      case 'js':
      case 'jsx':
        return <span style={{ color: '#f7df1e', fontSize: '13px', fontWeight: 'bold' }}>JS</span>
      case 'py':
        return <span style={{ color: '#3b82f6', fontSize: '13px', fontWeight: 'bold' }}>Py</span>
      case 'json':
        return <span style={{ color: '#cbd5e1', fontSize: '13px', fontWeight: 'bold' }}>&#123;&#125;</span>
      case 'md':
        return <FileText size={14} color="#38bdf8" />
      default:
        return <FileCode size={14} color="#94a3b8" />
    }
  }

  // Calculate auditor stats
  let totalLinesAudited = 0
  let totalLinesCut = 0
  fileKeys.forEach((k) => {
    if (files[k]?.audit) {
      totalLinesAudited += files[k].audit.lines_analyzed || 0
      totalLinesCut += files[k].audit.unnecessary_lines_removed || 0
    }
  })

  return (
    <aside className="ide-sidebar">
      {/* 1. EXPLORER VIEW */}
      {activeNav === 'explorer' && (
        <div className="sidebar-view">
          <div className="sidebar-title">
            <span>EXPLORER</span>
            <div className="sidebar-title-actions">
              <button
                className="icon-btn-ghost"
                onClick={onNewProject}
                title="Start a new build"
              >
                <Plus size={14} />
              </button>
            </div>
          </div>

          {/* Project Folder Section */}
          <div className="explorer-folder-header">
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <ChevronDown size={14} color="#818cf8" />
              <Folder size={14} color="#818cf8" />
              <span className="folder-name">{projectId || 'workspace'}</span>
            </div>
            <span className="file-count-tag">{fileKeys.length} files</span>
          </div>

          {/* File Tree */}
          <div className="explorer-file-tree">
            {fileKeys.length === 0 ? (
              <div className="empty-tree-hint">
                <Sparkles size={16} color="#6366f1" />
                <p>No project active.</p>
                <span>Ask the Agent Copilot on the right to build something!</span>
              </div>
            ) : (
              fileKeys.map((path) => {
                const isSelected = path === selectedFile
                const removed = files[path]?.audit?.unnecessary_lines_removed || 0

                return (
                  <div
                    key={path}
                    className={`explorer-file-row ${isSelected ? 'selected' : ''}`}
                    onClick={() => onSelectFile(path)}
                  >
                    <div className="file-row-main">
                      <span className="file-type-icon">{getFileIcon(path)}</span>
                      <span className="file-name-text">{path}</span>
                    </div>

                    {removed > 0 && (
                      <span
                        className="lines-cut-pill"
                        title={`${removed} unneeded lines eliminated by Auditor`}
                      >
                        -{removed}L
                      </span>
                    )}
                  </div>
                )
              })
            )}

            {readme && (
              <div
                className={`explorer-file-row ${selectedFile === 'README.md' ? 'selected' : ''}`}
                onClick={() => onSelectFile('README.md')}
              >
                <div className="file-row-main">
                  <FileText size={14} color="#38bdf8" />
                  <span className="file-name-text">README.md</span>
                </div>
                <span style={{ fontSize: '0.65rem', color: '#38bdf8' }}>DOCS</span>
              </div>
            )}
          </div>

          {/* Auditor Code Economy Summary */}
          {fileKeys.length > 0 && (
            <div className="sidebar-audit-card">
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px' }}>
                <ShieldCheck size={14} color="#10b981" />
                <span style={{ fontWeight: 600, color: '#10b981', fontSize: '0.78rem' }}>
                  Audited & Fact-Checked
                </span>
              </div>
              <div className="audit-stats-row">
                <span>Verified Lines:</span>
                <strong style={{ color: '#10b981' }}>{totalLinesAudited}</strong>
              </div>
              <div className="audit-stats-row">
                <span>Dead Lines Cut:</span>
                <strong style={{ color: '#f43f5e' }}>{totalLinesCut}</strong>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 2. SAVED PROJECTS ARCHIVE */}
      {activeNav === 'archive' && (
        <div className="sidebar-view">
          <div className="sidebar-title">
            <span>SAVED PROJECTS ({projects.length})</span>
          </div>

          <div className="archive-list">
            {projects.length === 0 ? (
              <div className="empty-tree-hint">
                <Clock size={16} />
                <p>No saved projects found on disk yet.</p>
              </div>
            ) : (
              projects.map((proj) => (
                <div
                  key={proj.id}
                  className={`archive-item-card ${proj.id === projectId ? 'active' : ''}`}
                  onClick={() => onLoadProject(proj.id)}
                >
                  <div className="archive-item-header">
                    <span className="archive-name">{proj.name}</span>
                    <span className="archive-files-pill">{proj.file_count} files</span>
                  </div>
                  <div className="archive-item-date">
                    {new Date(proj.created_at * 1000).toLocaleString([], {
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* 3. AGENT ROSTER VIEW */}
      {activeNav === 'agents' && (
        <div className="sidebar-view">
          <div className="sidebar-title">
            <span>SWARM ROSTER (6)</span>
          </div>

          <div className="agents-roster-list">
            {[
              { id: 'planner', name: 'Principal Architect', avatar: '🧠', role: 'Deconstruction & Specs', color: '#8b5cf6' },
              { id: 'coder', name: 'Senior Staff Polyglot', avatar: '💻', role: 'Zero-Bloat Implementation', color: '#3b82f6' },
              { id: 'auditor', name: 'Code Auditor & Fact-Checker', avatar: '🔍', role: 'Fact & Contract Verification', color: '#10b981' },
              { id: 'tester', name: 'QA Automation Lead', avatar: '🧪', role: 'PyTest & Syntax Checks', color: '#f59e0b' },
              { id: 'debugger', name: 'Root Cause Specialist', avatar: '🛠️', role: 'Surgical Patching', color: '#ef4444' },
              { id: 'reviewer', name: 'Technical Documentation Lead', avatar: '📝', role: 'Executable README & Setup', color: '#06b6d4' },
            ].map((a) => (
              <div key={a.id} className="roster-agent-card">
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '1.3rem' }}>{a.avatar}</span>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: '0.82rem', color: a.color }}>
                      {a.name}
                    </div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>{a.role}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </aside>
  )
}
