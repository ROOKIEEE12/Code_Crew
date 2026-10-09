import React from 'react'
import {
  Layers,
  FileCode,
  CheckCircle2,
  Clock,
  Sparkles,
  Zap,
  ShieldCheck,
  AlertTriangle,
  ArrowRight,
} from 'lucide-react'

export default function ArchitectureGraph({
  plan,
  files = {},
  pipelineState,
  selectedFile,
  onSelectFile,
}) {
  const planFiles = plan?.files || []
  const fileKeys = Object.keys(files)

  // Group files into topological waves based on dependencies
  const computeWaves = () => {
    if (!planFiles.length) {
      // Fallback from active files
      return [fileKeys.map((p) => ({ path: p, language: files[p]?.language || 'text', depends_on: [] }))]
    }

    const remaining = { ...Object.fromEntries(planFiles.map((f) => [f.path, f])) }
    const done = new Set()
    const waves = []

    while (Object.keys(remaining).length > 0) {
      const currentWave = Object.values(remaining).filter((f) =>
        (f.depends_on || []).every((dep) => done.has(dep))
      )

      if (currentWave.length === 0) {
        // Fallback for circular dependencies
        waves.push(Object.values(remaining))
        break
      }

      waves.push(currentWave)
      for (const f of currentWave) {
        done.add(f.path)
        delete remaining[f.path]
      }
    }

    return waves
  }

  const waves = computeWaves()

  const getNodeStatus = (filePath) => {
    const file = files[filePath]
    if (!file) {
      return { status: 'queued', label: 'Queued', color: '#64748b' }
    }
    if (file.audit?.fact_check_passed) {
      return { status: 'audited', label: 'Audited & Verified', color: '#10b981' }
    }
    return { status: 'generated', label: 'Generated', color: '#38bdf8' }
  }

  return (
    <div className="architecture-graph-canvas">
      {/* Header bar */}
      <div className="graph-header">
        <div className="graph-title-group">
          <Layers size={16} color="#818cf8" />
          <span className="graph-title">Living Swarm Architecture Topology</span>
          {plan?.project_type && (
            <span className="graph-badge">{plan.project_type.toUpperCase()}</span>
          )}
        </div>
        <div className="graph-meta">
          <span>{waves.length} Wave(s)</span>
          <span>•</span>
          <span>{planFiles.length || fileKeys.length} Files</span>
        </div>
      </div>

      {/* Main Canvas Waves */}
      <div className="waves-flow-container">
        {waves.map((wave, waveIdx) => (
          <div key={waveIdx} className="wave-column">
            <div className="wave-column-header">
              <span className="wave-number">WAVE {waveIdx + 1}</span>
              <span className="wave-tagline">
                {waveIdx === 0 ? 'Foundation Contracts' : 'Dependent Modules'}
              </span>
            </div>

            <div className="wave-nodes-list">
              {wave.map((node) => {
                const isSelected = selectedFile === node.path
                const nodeState = getNodeStatus(node.path)
                const auditData = files[node.path]?.audit

                return (
                  <div
                    key={node.path}
                    className={`arch-node-card ${isSelected ? 'selected' : ''}`}
                    onClick={() => onSelectFile(node.path)}
                  >
                    <div className="node-card-top">
                      <div className="node-file-info">
                        <FileCode size={15} color="#818cf8" />
                        <span className="node-file-name">{node.path}</span>
                      </div>
                      <span className="node-lang-pill">{node.language || 'code'}</span>
                    </div>

                    {node.description && (
                      <p className="node-purpose">{node.description}</p>
                    )}

                    {/* Status & Badges */}
                    <div className="node-footer">
                      <div className="node-status-indicator">
                        <span
                          className="status-dot-pulse"
                          style={{ backgroundColor: nodeState.color }}
                        />
                        <span style={{ color: nodeState.color, fontSize: '11px', fontWeight: 600 }}>
                          {nodeState.label}
                        </span>
                      </div>

                      {auditData?.unnecessary_lines_removed > 0 && (
                        <span className="audit-cut-badge">
                          -{auditData.unnecessary_lines_removed} dead lines
                        </span>
                      )}
                    </div>

                    {/* Dependencies preview */}
                    {node.depends_on && node.depends_on.length > 0 && (
                      <div className="node-dependencies">
                        <ArrowRight size={11} color="#64748b" />
                        <span>Depends on: {node.depends_on.join(', ')}</span>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
