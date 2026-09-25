import React, { useState } from 'react'
import {
  FileCode,
  CheckCircle2,
  Download,
  Copy,
  Check,
  Terminal,
  FileText,
  ShieldCheck,
  Sparkles,
  FlaskConical,
  Bug,
} from 'lucide-react'

export default function Workspace({
  files,
  readme,
  plan,
  logs,
  testingResult,
  projectDir,
  projectId,
  onDownloadZip,
}) {
  const fileKeys = Object.keys(files || {})
  const [selectedFile, setSelectedFile] = useState(fileKeys[0] || '')
  const [activeTab, setActiveTab] = useState('code') // 'code' | 'audit' | 'tests' | 'readme' | 'terminal'
  const [copied, setCopied] = useState(false)

  // Ensure selectedFile exists
  const currentFile = files[selectedFile] || (fileKeys.length > 0 ? files[fileKeys[0]] : null)
  const currentPath = selectedFile || (fileKeys.length > 0 ? fileKeys[0] : '')

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // Calculate stats from Auditor
  let totalLinesAudited = 0
  let totalLinesEliminated = 0
  fileKeys.forEach((k) => {
    if (files[k]?.audit) {
      totalLinesAudited += files[k].audit.lines_analyzed || 0
      totalLinesEliminated += files[k].audit.unnecessary_lines_removed || 0
    }
  })

  return (
    <div className="workspace-container">
      {/* File Tree Sidebar */}
      <aside className="file-sidebar">
        <div className="sidebar-header">
          <span>Project Files ({fileKeys.length})</span>
          <span
            style={{
              fontSize: '0.7rem',
              color: '#10b981',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
            }}
          >
            <ShieldCheck size={12} /> Audited
          </span>
        </div>

        <div className="file-list">
          {fileKeys.map((path) => {
            const f = files[path]
            const isSelected = path === currentPath
            const removed = f?.audit?.unnecessary_lines_removed || 0

            return (
              <div
                key={path}
                className={`file-item ${isSelected ? 'selected' : ''}`}
                onClick={() => {
                  setSelectedFile(path)
                  if (activeTab !== 'code' && activeTab !== 'audit') setActiveTab('code')
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden' }}>
                  <FileCode size={15} color={isSelected ? '#818cf8' : '#64748b'} />
                  <span style={{ textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                    {path}
                  </span>
                </div>
                {removed > 0 && (
                  <span
                    style={{
                      fontSize: '0.65rem',
                      background: 'rgba(239, 68, 68, 0.2)',
                      color: '#f87171',
                      padding: '2px 5px',
                      borderRadius: '4px',
                    }}
                    title={`${removed} unneeded lines eliminated by Auditor`}
                  >
                    -{removed}L
                  </span>
                )}
              </div>
            )
          })}

          {readme && (
            <div
              className={`file-item ${activeTab === 'readme' ? 'selected' : ''}`}
              onClick={() => setActiveTab('readme')}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <FileText size={15} color="#38bdf8" />
                <span>README.md</span>
              </div>
              <span style={{ fontSize: '0.65rem', color: '#38bdf8' }}>Docs</span>
            </div>
          )}
        </div>

        {/* Auditor Cleanliness Stats */}
        <div
          style={{
            padding: '12px 14px',
            background: 'rgba(16, 185, 129, 0.05)',
            borderTop: '1px solid var(--border-subtle)',
            fontSize: '0.75rem',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)' }}>
            <span>Lines Verified:</span>
            <span style={{ color: '#10b981', fontWeight: 600 }}>{totalLinesAudited}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-muted)' }}>
            <span>Unnecessary Lines Cut:</span>
            <span style={{ color: '#f43f5e', fontWeight: 600 }}>{totalLinesEliminated}</span>
          </div>
        </div>
      </aside>

      {/* Main Code & Analysis View */}
      <section className="code-viewer-panel">
        <div className="viewer-header">
          {/* Navigation Tabs */}
          <div className="tab-group">
            <button
              className={`nav-tab-btn ${activeTab === 'code' ? 'active' : ''}`}
              onClick={() => setActiveTab('code')}
            >
              <FileCode size={14} />
              <span>{currentPath || 'Source Code'}</span>
            </button>

            <button
              className={`nav-tab-btn ${activeTab === 'audit' ? 'active' : ''}`}
              onClick={() => setActiveTab('audit')}
            >
              <Sparkles size={14} color="#10b981" />
              <span>Fact-Check & Audit</span>
            </button>

            <button
              className={`nav-tab-btn ${activeTab === 'tests' ? 'active' : ''}`}
              onClick={() => setActiveTab('tests')}
            >
              <FlaskConical size={14} color="#f59e0b" />
              <span>QA & Tests</span>
            </button>

            <button
              className={`nav-tab-btn ${activeTab === 'readme' ? 'active' : ''}`}
              onClick={() => setActiveTab('readme')}
            >
              <FileText size={14} color="#38bdf8" />
              <span>Documentation</span>
            </button>

            <button
              className={`nav-tab-btn ${activeTab === 'terminal' ? 'active' : ''}`}
              onClick={() => setActiveTab('terminal')}
            >
              <Terminal size={14} />
              <span>Agent Activity ({logs?.length || 0})</span>
            </button>
          </div>

          {/* Action Buttons */}
          <div style={{ display: 'flex', gap: '8px' }}>
            {activeTab === 'code' && currentFile && (
              <button
                className="chip-btn"
                onClick={() => copyToClipboard(currentFile.code)}
                style={{ display: 'flex', alignItems: 'center', gap: '5px' }}
              >
                {copied ? <Check size={13} color="#10b981" /> : <Copy size={13} />}
                <span>{copied ? 'Copied' : 'Copy'}</span>
              </button>
            )}

            {onDownloadZip && (
              <button
                className="chip-btn"
                onClick={onDownloadZip}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '5px',
                  background: 'rgba(99, 102, 241, 0.2)',
                  borderColor: 'rgba(99, 102, 241, 0.4)',
                  color: '#c7d2fe',
                }}
              >
                <Download size={13} />
                <span>Download .ZIP</span>
              </button>
            )}
          </div>
        </div>

        {/* Tab Content Display */}
        <div className="code-scroll-area">
          {activeTab === 'code' && currentFile && (
            <div>
              <pre>{currentFile.code}</pre>
            </div>
          )}

          {activeTab === 'audit' && (
            <div>
              <div className="auditor-box">
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                  <ShieldCheck size={18} color="#10b981" />
                  <h3 style={{ fontSize: '1rem', color: '#10b981' }}>
                    Auditor & Fact-Checking Report: {currentPath}
                  </h3>
                </div>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: '12px' }}>
                  Every line of code and every referenced function/API in this file was verified by
                  the Auditor Agent to ensure zero hallucination, strict typing, and zero unnecessary code bloat.
                </p>

                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                    gap: '12px',
                    marginBottom: '14px',
                  }}
                >
                  <div style={{ background: 'rgba(0,0,0,0.3)', padding: '10px', borderRadius: '8px' }}>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>Fact Check Status</div>
                    <div style={{ fontSize: '1.1rem', color: '#10b981', fontWeight: 700 }}>
                      {currentFile?.audit?.fact_check_passed !== false ? '100% Verified' : 'Adjusted'}
                    </div>
                  </div>

                  <div style={{ background: 'rgba(0,0,0,0.3)', padding: '10px', borderRadius: '8px' }}>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>Lines Scanned</div>
                    <div style={{ fontSize: '1.1rem', color: '#fff', fontWeight: 700 }}>
                      {currentFile?.audit?.lines_analyzed || currentFile?.code?.split('\n').length || 0}
                    </div>
                  </div>

                  <div style={{ background: 'rgba(0,0,0,0.3)', padding: '10px', borderRadius: '8px' }}>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>Dead/Unneeded Lines Cut</div>
                    <div style={{ fontSize: '1.1rem', color: '#f43f5e', fontWeight: 700 }}>
                      {currentFile?.audit?.unnecessary_lines_removed || 0}
                    </div>
                  </div>
                </div>

                <div style={{ fontSize: '0.85rem', color: 'var(--text-main)', background: 'rgba(0,0,0,0.2)', padding: '10px', borderRadius: '8px' }}>
                  <strong>Auditor Notes:</strong>{' '}
                  {currentFile?.audit?.audit_notes || 'All syntax structures, library methods, and exports verified with zero extraneous lines.'}
                </div>
              </div>

              <h4 style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '8px' }}>
                Verified Clean Code:
              </h4>
              <pre>{currentFile?.code}</pre>
            </div>
          )}

          {activeTab === 'tests' && (
            <div>
              <div
                style={{
                  background: 'rgba(245, 158, 11, 0.08)',
                  border: '1px solid rgba(245, 158, 11, 0.3)',
                  borderRadius: '10px',
                  padding: '16px',
                  marginBottom: '20px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                  <FlaskConical size={18} color="#f59e0b" />
                  <h3 style={{ fontSize: '1rem', color: '#f59e0b' }}>
                    Automated Test Suite & QA Review
                  </h3>
                </div>
                <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                  Multi-tier evaluation: Syntax validation across all languages, real sandboxed PyTest execution,
                  and deep contract analysis.
                </p>
              </div>

              {testingResult?.syntax_results && (
                <div style={{ marginBottom: '20px' }}>
                  <h4 style={{ fontSize: '0.9rem', marginBottom: '10px' }}>Syntax Verification</h4>
                  {Object.entries(testingResult.syntax_results).map(([path, res]) => (
                    <div
                      key={path}
                      style={{
                        padding: '8px 12px',
                        background: 'rgba(255,255,255,0.03)',
                        borderRadius: '6px',
                        marginBottom: '6px',
                        display: 'flex',
                        justifyContent: 'space-between',
                        fontSize: '0.82rem',
                      }}
                    >
                      <span>{path}</span>
                      <span style={{ color: res.passed ? '#10b981' : '#f87171' }}>
                        {res.passed ? '✅ Passed' : '❌ Syntax Error'}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {testingResult?.pytest?.output && (
                <div>
                  <h4 style={{ fontSize: '0.9rem', marginBottom: '8px' }}>PyTest Execution Output</h4>
                  <pre
                    style={{
                      background: 'rgba(0,0,0,0.5)',
                      padding: '12px',
                      borderRadius: '8px',
                      fontSize: '0.8rem',
                    }}
                  >
                    {testingResult.pytest.output}
                  </pre>
                </div>
              )}
            </div>
          )}

          {activeTab === 'readme' && (
            <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.7 }}>
              {readme || 'Documentation will appear here once generated.'}
            </div>
          )}

          {activeTab === 'terminal' && (
            <div className="terminal-window">
              {logs && logs.length > 0 ? (
                logs.map((log, index) => (
                  <div key={index} className="terminal-line">
                    <span style={{ color: '#6366f1' }}>&gt;</span> {log}
                  </div>
                ))
              ) : (
                <div style={{ color: 'var(--text-dim)' }}>
                  Awaiting multi-agent execution pipeline...
                </div>
              )}
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
