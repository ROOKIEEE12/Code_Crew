import React, { useState } from 'react'
import { GitCompare, Columns, ListFilter } from 'lucide-react'

export default function DiffViewer({
  filename,
  oldCode = '',
  newCode = '',
}) {
  const [viewMode, setViewMode] = useState('split') // 'split' | 'unified'

  // Basic line-by-line diff calculator
  const computeDiff = () => {
    const oldLines = oldCode.split('\n')
    const newLines = newCode.split('\n')
    const maxLen = Math.max(oldLines.length, newLines.length)
    const diff = []

    for (let i = 0; i < maxLen; i++) {
      const o = oldLines[i]
      const n = newLines[i]

      if (o === undefined) {
        diff.push({ type: 'added', oldLine: null, newLine: i + 1, oldText: '', newText: n })
      } else if (n === undefined) {
        diff.push({ type: 'removed', oldLine: i + 1, newLine: null, oldText: o, newText: '' })
      } else if (o !== n) {
        diff.push({ type: 'modified', oldLine: i + 1, newLine: i + 1, oldText: o, newText: n })
      } else {
        diff.push({ type: 'unchanged', oldLine: i + 1, newLine: i + 1, oldText: o, newText: n })
      }
    }
    return diff
  }

  const diffRows = computeDiff()

  return (
    <div className="diff-viewer-container">
      {/* Diff Controls Header */}
      <div className="diff-header-bar">
        <div className="diff-file-tag">
          <GitCompare size={14} color="#818cf8" />
          <span>{filename}</span>
          <span className="diff-stats">
            +{diffRows.filter((r) => r.type === 'added' || r.type === 'modified').length} / -
            {diffRows.filter((r) => r.type === 'removed' || r.type === 'modified').length}
          </span>
        </div>

        <div className="diff-mode-toggle">
          <button
            className={`diff-toggle-btn ${viewMode === 'split' ? 'active' : ''}`}
            onClick={() => setViewMode('split')}
            title="Side-by-side split view"
          >
            <Columns size={12} />
            <span>Split</span>
          </button>
          <button
            className={`diff-toggle-btn ${viewMode === 'unified' ? 'active' : ''}`}
            onClick={() => setViewMode('unified')}
            title="Unified line-by-line view"
          >
            <ListFilter size={12} />
            <span>Unified</span>
          </button>
        </div>
      </div>

      {/* Diff Content View */}
      <div className="diff-content-scroll">
        {viewMode === 'split' ? (
          <div className="split-diff-table">
            <div className="split-diff-side old-side">
              <div className="side-column-header">Original / Prior State</div>
              {diffRows.map((row, idx) => (
                <div
                  key={`old-${idx}`}
                  className={`diff-line-row ${
                    row.type === 'removed' || row.type === 'modified' ? 'line-removed' : ''
                  }`}
                >
                  <span className="diff-gutter">{row.oldLine || ''}</span>
                  <span className="diff-code-text">{row.oldText}</span>
                </div>
              ))}
            </div>

            <div className="split-diff-side new-side">
              <div className="side-column-header">Specialist Patched State</div>
              {diffRows.map((row, idx) => (
                <div
                  key={`new-${idx}`}
                  className={`diff-line-row ${
                    row.type === 'added' || row.type === 'modified' ? 'line-added' : ''
                  }`}
                >
                  <span className="diff-gutter">{row.newLine || ''}</span>
                  <span className="diff-code-text">{row.newText}</span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="unified-diff-view">
            {diffRows.map((row, idx) => (
              <div
                key={`uni-${idx}`}
                className={`unified-line-row ${
                  row.type === 'added'
                    ? 'line-added'
                    : row.type === 'removed'
                    ? 'line-removed'
                    : row.type === 'modified'
                    ? 'line-modified'
                    : ''
                }`}
              >
                <span className="diff-gutter">{row.oldLine || ''}</span>
                <span className="diff-gutter">{row.newLine || ''}</span>
                <span className="diff-symbol">
                  {row.type === 'added' ? '+' : row.type === 'removed' ? '-' : ' '}
                </span>
                <span className="diff-code-text">
                  {row.type === 'removed' ? row.oldText : row.newText}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
