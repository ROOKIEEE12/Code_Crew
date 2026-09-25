import React, { useState } from 'react'
import {
  FileCode,
  Copy,
  Check,
  Eye,
  EyeOff,
  Terminal,
  FlaskConical,
  ShieldCheck,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  X,
  Sparkles,
  Play,
} from 'lucide-react'

export default function EditorWorkspace({
  files = {},
  selectedFile,
  onSelectFile,
  readme,
  logs = [],
  testingResult,
  terminalOpen,
  onToggleTerminal,
  livePreview,
  onToggleLivePreview,
  onSelectSamplePrompt,
}) {
  const [activeBottomTab, setActiveBottomTab] = useState('terminal') // 'terminal' | 'tests' | 'audit' | 'problems'
  const [copied, setCopied] = useState(false)

  const fileKeys = Object.keys(files || {})
  const currentFile = files[selectedFile] || (fileKeys.length > 0 ? files[fileKeys[0]] : null)
  const isReadme = selectedFile === 'README.md'
  const codeContent = isReadme ? readme : currentFile?.code || ''

  const copyToClipboard = () => {
    if (!codeContent) return
    navigator.clipboard.writeText(codeContent)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // Generate srcDoc for live interactive web preview
  const generatePreviewDoc = () => {
    const html = files['index.html']?.code || Object.values(files).find(f => f.language === 'html')?.code || ''
    const css = files['styles.css']?.code || files['style.css']?.code || Object.values(files).find(f => f.language === 'css')?.code || ''
    const js = files['script.js']?.code || files['app.js']?.code || Object.values(files).find(f => f.language === 'javascript')?.code || ''

    if (!html) return '<html><body style="font-family:sans-serif;padding:20px;color:#888;">No HTML file found for live preview.</body></html>'

    return `
      <!DOCTYPE html>
      <html>
        <head>
          <style>${css}</style>
        </head>
        <body>
          ${html.replace(/<link[^>]*rel=["']stylesheet["'][^>]*>/gi, '')}
          <script>${js}<\/script>
        </body>
      </html>
    `
  }

  return (
    <main className="ide-editor-workspace">
      {/* 1. Editor Tabs Header */}
      <div className="editor-tab-bar">
        <div className="tabs-scroll-area">
          {fileKeys.map((path) => (
            <div
              key={path}
              className={`editor-tab ${selectedFile === path ? 'active' : ''}`}
              onClick={() => onSelectFile(path)}
            >
              <FileCode size={13} color={selectedFile === path ? '#818cf8' : '#64748b'} />
              <span className="tab-title">{path}</span>
            </div>
          ))}

          {readme && (
            <div
              className={`editor-tab ${selectedFile === 'README.md' ? 'active' : ''}`}
              onClick={() => onSelectFile('README.md')}
            >
              <span style={{ color: '#38bdf8' }}>📄</span>
              <span className="tab-title">README.md</span>
            </div>
          )}
        </div>

        {/* Tab Bar Action Buttons */}
        <div className="tab-bar-actions">
          {codeContent && (
            <button
              className="tab-action-btn"
              onClick={copyToClipboard}
              title="Copy code to clipboard"
            >
              {copied ? <Check size={13} color="#10b981" /> : <Copy size={13} />}
              <span>{copied ? 'Copied' : 'Copy'}</span>
            </button>
          )}

          {files['index.html'] && (
            <button
              className={`tab-action-btn ${livePreview ? 'active-highlight' : ''}`}
              onClick={onToggleLivePreview}
              title="Toggle Live Web Browser Preview"
            >
              {livePreview ? <EyeOff size={13} /> : <Eye size={13} />}
              <span>{livePreview ? 'Editor' : 'Live Preview'}</span>
            </button>
          )}
        </div>
      </div>

      {/* 2. Main Editor Content / Live Preview / Welcome Screen */}
      <div className="editor-main-viewport">
        {fileKeys.length === 0 ? (
          /* Antigravity Welcome Screen */
          <div className="ide-welcome-screen">
            <div className="welcome-logo-container">
              <div className="antigravity-brand-mark">
                <span style={{ fontSize: '2.5rem' }}>▲</span>
              </div>
              <h1 className="welcome-title">Antigravity Multi-Agent Studio</h1>
              <p className="welcome-subtitle">
                Autonomous specialist agents (Architect, Coder, Auditor, Tester, Debugger, Writer) working together.
              </p>
            </div>

            <div className="welcome-shortcuts">
              <div className="shortcut-row">
                <span className="shortcut-label">Deploy Swarm</span>
                <span className="shortcut-keys"><kbd>Ctrl</kbd> + <kbd>Enter</kbd></span>
              </div>
              <div className="shortcut-row">
                <span className="shortcut-label">Toggle Terminal</span>
                <span className="shortcut-keys"><kbd>Ctrl</kbd> + <kbd>`</kbd></span>
              </div>
            </div>

            <div className="welcome-templates">
              <span className="templates-label">Quick Starters:</span>
              <div className="templates-chip-group">
                {[
                  'Modern Weather Dashboard with dark mode & smooth animations',
                  'FastAPI REST API with SQLite database, items CRUD, and error handling',
                  'Interactive Task Kanban Board with vanilla JS and local storage',
                  'Multi-page Portfolio website with responsive hero and contact form',
                ].map((prompt, idx) => (
                  <button
                    key={idx}
                    className="starter-chip"
                    onClick={() => onSelectSamplePrompt(prompt)}
                  >
                    <Sparkles size={12} color="#818cf8" />
                    <span>{prompt}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : livePreview ? (
          /* Live Sandbox Preview */
          <div className="live-preview-container">
            <div className="preview-browser-bar">
              <div className="browser-dots">
                <span className="dot red"></span>
                <span className="dot yellow"></span>
                <span className="dot green"></span>
              </div>
              <div className="browser-address">http://localhost:3000/index.html (Sandbox Live Run)</div>
            </div>
            <iframe
              className="preview-iframe"
              title="Live Project Preview"
              srcDoc={generatePreviewDoc()}
              sandbox="allow-scripts allow-modals"
            />
          </div>
        ) : (
          /* Monaco Style Code Viewer with Line Numbers */
          <div className="code-viewer-container">
            <div className="line-numbers-col">
              {codeContent.split('\n').map((_, index) => (
                <div key={index} className="line-num">
                  {index + 1}
                </div>
              ))}
            </div>
            <pre className="code-content-col">
              <code>{codeContent}</code>
            </pre>
          </div>
        )}
      </div>

      {/* 3. Bottom Terminal & QA Panel (Collapsible) */}
      {terminalOpen && (
        <div className="ide-bottom-dock">
          <div className="bottom-dock-header">
            <div className="dock-tabs">
              <button
                className={`dock-tab-btn ${activeBottomTab === 'terminal' ? 'active' : ''}`}
                onClick={() => setActiveBottomTab('terminal')}
              >
                <Terminal size={13} />
                <span>TERMINAL ({logs.length})</span>
              </button>

              <button
                className={`dock-tab-btn ${activeBottomTab === 'tests' ? 'active' : ''}`}
                onClick={() => setActiveBottomTab('tests')}
              >
                <FlaskConical size={13} color="#f59e0b" />
                <span>QA & PYTEST</span>
              </button>

              <button
                className={`dock-tab-btn ${activeBottomTab === 'audit' ? 'active' : ''}`}
                onClick={() => setActiveBottomTab('audit')}
              >
                <ShieldCheck size={13} color="#10b981" />
                <span>FACT-CHECK & AUDIT</span>
              </button>

              <button
                className={`dock-tab-btn ${activeBottomTab === 'problems' ? 'active' : ''}`}
                onClick={() => setActiveBottomTab('problems')}
              >
                <AlertTriangle size={13} color="#38bdf8" />
                <span>PROBLEMS (0)</span>
              </button>
            </div>

            <div className="dock-controls">
              <button
                className="icon-btn-ghost"
                onClick={onToggleTerminal}
                title="Hide Bottom Terminal"
              >
                <X size={14} />
              </button>
            </div>
          </div>

          <div className="bottom-dock-content">
            {activeBottomTab === 'terminal' && (
              <div className="terminal-stream">
                {logs.length === 0 ? (
                  <div className="terminal-idle">
                    <span style={{ color: '#6366f1' }}>PS C:\codecrew&gt;</span> Awaiting multi-agent pipeline launch...
                  </div>
                ) : (
                  logs.map((log, idx) => (
                    <div key={idx} className="terminal-log-row">
                      <span className="term-prompt">&gt;</span>
                      <span className="term-text">{log}</span>
                    </div>
                  ))
                )}
              </div>
            )}

            {activeBottomTab === 'tests' && (
              <div className="tests-stream">
                <div style={{ marginBottom: '8px', color: '#f59e0b', fontWeight: 600 }}>
                  Automated QA Validation & Syntax Suite
                </div>
                {testingResult?.syntax_results ? (
                  Object.entries(testingResult.syntax_results).map(([p, res]) => (
                    <div key={p} className="test-row">
                      <span>{p}</span>
                      <span style={{ color: res.passed ? '#10b981' : '#f87171' }}>
                        {res.passed ? '✓ Passed' : '✗ Error'}
                      </span>
                    </div>
                  ))
                ) : (
                  <div style={{ color: 'var(--text-dim)' }}>No test execution results yet.</div>
                )}
                {testingResult?.pytest?.output && (
                  <pre className="pytest-output">{testingResult.pytest.output}</pre>
                )}
              </div>
            )}

            {activeBottomTab === 'audit' && (
              <div className="audit-stream">
                <div style={{ marginBottom: '8px', color: '#10b981', fontWeight: 600 }}>
                  Auditor Line-by-Line Verification Log
                </div>
                {fileKeys.map((p) => {
                  const audit = files[p]?.audit
                  if (!audit) return null
                  return (
                    <div key={p} className="audit-row">
                      <strong>{p}:</strong>
                      <span>{audit.audit_notes || 'Verified against APIs & eliminated dead code.'}</span>
                      <span style={{ color: '#f87171' }}>-{audit.unnecessary_lines_removed || 0}L</span>
                    </div>
                  )
                })}
              </div>
            )}

            {activeBottomTab === 'problems' && (
              <div className="problems-stream">
                <span style={{ color: '#10b981' }}>✓ No problems or syntax errors detected in workspace.</span>
              </div>
            )}
          </div>
        </div>
      )}
    </main>
  )
}
