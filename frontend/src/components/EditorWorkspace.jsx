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
  Layers,
  GitCompare,
  RotateCw,
  ExternalLink,
  Columns,
  Code2,
} from 'lucide-react'
import ArchitectureGraph from './ArchitectureGraph'
import DiffViewer from './DiffViewer'

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
  plan,
  pipelineState = {},
}) {
  const [activeBottomTab, setActiveBottomTab] = useState('terminal') // 'terminal' | 'tests' | 'audit' | 'problems'
  const [workspaceMode, setWorkspaceMode] = useState('editor') // 'editor' | 'split' | 'preview' | 'graph' | 'diff'
  const [copied, setCopied] = useState(false)
  const [previewKey, setPreviewKey] = useState(0)

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
    const html =
      files['index.html']?.code ||
      Object.values(files).find((f) => f.language === 'html')?.code ||
      ''
    const css =
      files['styles.css']?.code ||
      files['style.css']?.code ||
      Object.values(files).find((f) => f.language === 'css')?.code ||
      ''
    const js =
      files['script.js']?.code ||
      files['app.js']?.code ||
      Object.values(files).find((f) => f.language === 'javascript')?.code ||
      ''

    if (!html) {
      return `<!DOCTYPE html><html><body style="background:#0f172a;color:#94a3b8;font-family:system-ui;display:flex;align-items:center;justify-content:center;height:90vh;margin:0;"><div style="text-align:center;"><h2>No HTML Entry Point Found</h2><p>This project might be a Python script or backend service.</p></div></body></html>`
    }

    return `
      <!DOCTYPE html>
      <html>
        <head>
          <meta charset="utf-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1.0" />
          <style>
            ${css}
          </style>
        </head>
        <body>
          ${html.replace(/<link[^>]*rel=["']stylesheet["'][^>]*>/gi, '')}
          <script>
            try {
              ${js}
            } catch (err) {
              console.error("Runtime error in sandbox:", err);
            }
          <\/script>
        </body>
      </html>
    `
  }

  const handleOpenNewTab = () => {
    const doc = generatePreviewDoc()
    const win = window.open()
    if (win) {
      win.document.write(doc)
      win.document.close()
    }
  }

  const hasHtml = Boolean(files['index.html'] || Object.values(files).some((f) => f.language === 'html'))

  return (
    <main className="ide-editor-workspace">
      {/* 1. Editor Tabs & Controls Bar */}
      <div className="editor-tab-bar">
        <div className="tabs-scroll-area">
          {fileKeys.map((path) => (
            <div
              key={path}
              className={`editor-tab ${selectedFile === path ? 'active' : ''}`}
              onClick={() => {
                onSelectFile(path)
                if (workspaceMode === 'graph') setWorkspaceMode('editor')
              }}
            >
              <FileCode size={13} color={selectedFile === path ? '#818cf8' : '#64748b'} />
              <span className="tab-title">{path}</span>
            </div>
          ))}

          {readme && (
            <div
              className={`editor-tab ${selectedFile === 'README.md' ? 'active' : ''}`}
              onClick={() => {
                onSelectFile('README.md')
                if (workspaceMode === 'graph') setWorkspaceMode('editor')
              }}
            >
              <span style={{ color: '#38bdf8' }}>📄</span>
              <span className="tab-title">README.md</span>
            </div>
          )}
        </div>

        {/* Workspace Mode Selector */}
        {fileKeys.length > 0 && (
          <div className="workspace-mode-pills">
            <button
              className={`mode-pill ${workspaceMode === 'editor' ? 'active' : ''}`}
              onClick={() => setWorkspaceMode('editor')}
              title="Code View"
            >
              <Code2 size={12} />
              <span>Code</span>
            </button>

            {hasHtml && (
              <>
                <button
                  className={`mode-pill ${workspaceMode === 'split' ? 'active' : ''}`}
                  onClick={() => setWorkspaceMode('split')}
                  title="Split Code & Live Sandbox Preview"
                >
                  <Columns size={12} />
                  <span>Split View</span>
                </button>
                <button
                  className={`mode-pill ${workspaceMode === 'preview' ? 'active' : ''}`}
                  onClick={() => setWorkspaceMode('preview')}
                  title="Full Live Web App"
                >
                  <Eye size={12} />
                  <span>Live App</span>
                </button>
              </>
            )}

            <button
              className={`mode-pill ${workspaceMode === 'graph' ? 'active' : ''}`}
              onClick={() => setWorkspaceMode('graph')}
              title="Living Swarm Architecture Graph"
            >
              <Layers size={12} />
              <span>Architecture</span>
            </button>

            {selectedFile && !isReadme && (
              <button
                className={`mode-pill ${workspaceMode === 'diff' ? 'active' : ''}`}
                onClick={() => setWorkspaceMode('diff')}
                title="Specialist Patch Diff Viewer"
              >
                <GitCompare size={12} />
                <span>Diff</span>
              </button>
            )}
          </div>
        )}

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
        </div>
      </div>

      {/* 2. Main Viewport Area */}
      <div className="editor-main-viewport">
        {fileKeys.length === 0 ? (
          /* Welcome Screen */
          <div className="ide-welcome-screen">
            <div className="welcome-logo-container">
              <div className="antigravity-brand-mark">
                <span style={{ fontSize: '2.5rem' }}>▲</span>
              </div>
              <h1 className="welcome-title">CodeCrew Autonomous Swarm Studio</h1>
              <p className="welcome-subtitle">
                Isolated specialist agents (Architect, Coder, Auditor, Tester, Debugger, Writer)
                building multi-file verified applications.
              </p>
            </div>

            <div className="welcome-shortcuts">
              <div className="shortcut-row">
                <span className="shortcut-label">Deploy Swarm</span>
                <span className="shortcut-keys">
                  <kbd>Ctrl</kbd> + <kbd>Enter</kbd>
                </span>
              </div>
              <div className="shortcut-row">
                <span className="shortcut-label">Toggle Terminal</span>
                <span className="shortcut-keys">
                  <kbd>Ctrl</kbd> + <kbd>`</kbd>
                </span>
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
        ) : workspaceMode === 'graph' ? (
          /* Architecture Topology Graph */
          <ArchitectureGraph
            plan={plan}
            files={files}
            pipelineState={pipelineState}
            selectedFile={selectedFile}
            onSelectFile={(path) => {
              onSelectFile(path)
              setWorkspaceMode('editor')
            }}
          />
        ) : workspaceMode === 'diff' ? (
          /* Surgical Diff Viewer */
          <DiffViewer
            filename={selectedFile}
            oldCode={currentFile?.audit?.original_code || currentFile?.code || ''}
            newCode={currentFile?.code || ''}
          />
        ) : workspaceMode === 'split' ? (
          /* Side-by-Side Split View */
          <div className="split-viewport-container">
            {/* Left 50%: Code Editor */}
            <div className="split-half code-half">
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
            </div>

            {/* Right 50%: Live Web Sandbox */}
            <div className="split-half preview-half">
              <div className="live-preview-container">
                <div className="preview-browser-bar">
                  <div className="browser-dots">
                    <span className="dot red"></span>
                    <span className="dot yellow"></span>
                    <span className="dot green"></span>
                  </div>
                  <div className="browser-address">http://localhost:3000/index.html</div>
                  <div className="preview-controls-right">
                    <button
                      className="browser-tool-btn"
                      onClick={() => setPreviewKey((k) => k + 1)}
                      title="Reload sandbox"
                    >
                      <RotateCw size={12} />
                    </button>
                    <button
                      className="browser-tool-btn"
                      onClick={handleOpenNewTab}
                      title="Open in new window"
                    >
                      <ExternalLink size={12} />
                    </button>
                  </div>
                </div>
                <iframe
                  key={previewKey}
                  className="preview-iframe"
                  title="Live Split Preview"
                  srcDoc={generatePreviewDoc()}
                  sandbox="allow-scripts allow-modals"
                />
              </div>
            </div>
          </div>
        ) : workspaceMode === 'preview' ? (
          /* Full Live Sandbox Preview */
          <div className="live-preview-container">
            <div className="preview-browser-bar">
              <div className="browser-dots">
                <span className="dot red"></span>
                <span className="dot yellow"></span>
                <span className="dot green"></span>
              </div>
              <div className="browser-address">http://localhost:3000/index.html (Sandbox Live Run)</div>
              <div className="preview-controls-right">
                <button
                  className="browser-tool-btn"
                  onClick={() => setPreviewKey((k) => k + 1)}
                  title="Reload sandbox"
                >
                  <RotateCw size={12} />
                </button>
                <button
                  className="browser-tool-btn"
                  onClick={handleOpenNewTab}
                  title="Open in new window"
                >
                  <ExternalLink size={12} />
                </button>
              </div>
            </div>
            <iframe
              key={previewKey}
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

      {/* 3. Bottom Terminal & QA Panel */}
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
                <FlaskConical size={13} />
                <span>TESTS & QA</span>
                {testingResult && (
                  <span
                    className={`mini-pill ${testingResult.passed ? 'success' : 'fail'}`}
                  >
                    {testingResult.passed ? 'PASSED' : 'ISSUES'}
                  </span>
                )}
              </button>

              <button
                className={`dock-tab-btn ${activeBottomTab === 'audit' ? 'active' : ''}`}
                onClick={() => setActiveBottomTab('audit')}
              >
                <ShieldCheck size={13} />
                <span>FACT-CHECK AUDIT</span>
              </button>
            </div>

            <div className="dock-actions">
              <button className="icon-btn-ghost" onClick={onToggleTerminal} title="Close Panel">
                <X size={14} />
              </button>
            </div>
          </div>

          <div className="bottom-dock-content">
            {activeBottomTab === 'terminal' && (
              <div className="terminal-log-view">
                {logs.length === 0 ? (
                  <div className="empty-terminal-hint">No swarm logs yet.</div>
                ) : (
                  logs.map((log, idx) => (
                    <div key={idx} className="terminal-line">
                      <span className="log-prefix">&gt;</span>
                      <span className="log-text">{log}</span>
                    </div>
                  ))
                )}
              </div>
            )}

            {activeBottomTab === 'tests' && (
              <div className="qa-report-view">
                {!testingResult ? (
                  <div className="empty-terminal-hint">
                    No test report available yet. Run a build to see automated QA results.
                  </div>
                ) : (
                  <div className="qa-report-grid">
                    <div className="qa-card">
                      <span className="qa-card-title">Syntax & Static Analysis</span>
                      <div className="qa-card-items">
                        {Object.entries(testingResult.syntax_results || {}).map(([p, r]) => (
                          <div key={p} className="qa-status-row">
                            <span>{p}</span>
                            <span
                              className={`status-pill ${
                                r.passed ? 'pill-green' : r.checked ? 'pill-red' : 'pill-gray'
                              }`}
                            >
                              {r.passed ? 'PASSED' : r.checked ? 'FAILED' : 'SKIPPED'}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>

                    <div className="qa-card">
                      <span className="qa-card-title">Sandboxed PyTest Suite</span>
                      <div className="qa-card-body">
                        {testingResult.pytest?.ran ? (
                          <pre className="test-output-box">{testingResult.pytest.output}</pre>
                        ) : (
                          <span style={{ color: '#64748b' }}>No Python test suite required.</span>
                        )}
                      </div>
                    </div>

                    <div className="qa-card">
                      <span className="qa-card-title">LLM Multi-File Contract Audit</span>
                      <div className="qa-card-body">
                        {testingResult.review?.issues?.length > 0 ? (
                          testingResult.review.issues.map((iss, i) => (
                            <div key={i} className="review-issue-item">
                              <span className={`severity-tag ${iss.severity}`}>
                                {iss.severity}
                              </span>
                              <span className="issue-file">{iss.file}:</span>
                              <span className="issue-desc">{iss.problem}</span>
                            </div>
                          ))
                        ) : (
                          <span style={{ color: '#10b981' }}>
                            ✓ Zero cross-file inconsistencies or logic defects found.
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {activeBottomTab === 'audit' && (
              <div className="audit-detail-view">
                <div className="audit-file-cards">
                  {Object.entries(files).map(([p, f]) => {
                    const audit = f.audit
                    if (!audit) return null
                    return (
                      <div key={p} className="audit-file-block">
                        <div className="audit-block-top">
                          <span className="audit-file-name">{p}</span>
                          <span className="lines-removed-tag">
                            -{audit.unnecessary_lines_removed || 0} unneeded lines eliminated
                          </span>
                        </div>
                        <p className="audit-notes-text">
                          {audit.audit_notes || 'Code verified cleanly.'}
                        </p>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </main>
  )
}
