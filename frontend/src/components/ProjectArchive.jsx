import React from 'react'
import { FolderGit2, Download, FileCode, Calendar, ArrowRight } from 'lucide-react'

export default function ProjectArchive({ projects, onLoadProject, onDownloadZip }) {
  if (!projects || projects.length === 0) {
    return (
      <div
        className="glass-panel"
        style={{
          padding: '60px 20px',
          textAlign: 'center',
          color: 'var(--text-muted)',
        }}
      >
        <FolderGit2 size={48} style={{ margin: '0 auto 16px auto', color: '#6366f1', opacity: 0.7 }} />
        <h3 style={{ fontSize: '1.2rem', color: '#fff', marginBottom: '8px' }}>No Saved Projects Yet</h3>
        <p style={{ fontSize: '0.9rem', maxWidth: '400px', margin: '0 auto' }}>
          When you launch the multi-agent team to build a project, it will automatically be archived
          here with its files, test results, and documentation.
        </p>
      </div>
    )
  }

  return (
    <div>
      <div style={{ marginBottom: '20px' }}>
        <h2 style={{ fontSize: '1.4rem', fontWeight: 700 }}>Generated Project Repository</h2>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
          Browse, inspect, and download completed builds created by the CodeCrew agent swarm.
        </p>
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
          gap: '16px',
        }}
      >
        {projects.map((proj) => {
          const formattedDate = new Date(proj.created_at * 1000).toLocaleString()

          return (
            <div
              key={proj.id}
              className="glass-panel"
              style={{
                padding: '20px',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                transition: 'all 0.2s ease',
              }}
            >
              <div>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginBottom: '10px',
                  }}
                >
                  <span
                    style={{
                      fontSize: '0.75rem',
                      color: 'var(--text-dim)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                    }}
                  >
                    <Calendar size={12} /> {formattedDate}
                  </span>
                  <span
                    className="badge-tag"
                    style={{
                      background: 'rgba(99, 102, 241, 0.15)',
                      color: '#a5b4fc',
                    }}
                  >
                    {proj.file_count} file(s)
                  </span>
                </div>

                <h3
                  style={{
                    fontSize: '1.1rem',
                    fontWeight: 700,
                    color: '#fff',
                    marginBottom: '10px',
                  }}
                >
                  {proj.name}
                </h3>

                <div
                  style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: '6px',
                    marginBottom: '18px',
                  }}
                >
                  {proj.files.slice(0, 4).map((f) => (
                    <span
                      key={f}
                      style={{
                        fontSize: '0.72rem',
                        background: 'rgba(255,255,255,0.05)',
                        padding: '3px 8px',
                        borderRadius: '4px',
                        color: 'var(--text-muted)',
                      }}
                    >
                      {f}
                    </span>
                  ))}
                  {proj.files.length > 4 && (
                    <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>
                      +{proj.files.length - 4} more
                    </span>
                  )}
                </div>
              </div>

              <div
                style={{
                  display: 'flex',
                  gap: '8px',
                  borderTop: '1px solid var(--border-subtle)',
                  paddingTop: '14px',
                }}
              >
                <button
                  className="chip-btn"
                  onClick={() => onLoadProject(proj.id)}
                  style={{
                    flex: 1,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '6px',
                    background: 'rgba(99, 102, 241, 0.2)',
                    borderColor: 'rgba(99, 102, 241, 0.4)',
                    color: '#fff',
                  }}
                >
                  <span>Open in Studio</span>
                  <ArrowRight size={13} />
                </button>

                <button
                  className="chip-btn"
                  onClick={() => onDownloadZip(proj.id)}
                  title="Download as .zip"
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    padding: '8px 12px',
                  }}
                >
                  <Download size={14} />
                </button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
