import React, { useState, useEffect } from 'react'
import Navbar from './components/Navbar'
import AgentSwarm from './components/AgentSwarm'
import Workspace from './components/Workspace'
import ProjectArchive from './components/ProjectArchive'
import { Rocket, Sparkles, AlertCircle } from 'lucide-react'
import './App.css'

const SAMPLE_PROMPTS = [
  'Modern Weather Dashboard with dark mode and smooth animations',
  'FastAPI REST API with SQLite database, items CRUD, and error handling',
  'Interactive Task Kanban Board with vanilla JS and local storage',
  'Multi-page Portfolio website with responsive hero and contact form',
]

export default function App() {
  const [activeTab, setActiveTab] = useState('studio') // 'studio' | 'archive'
  const [backendStatus, setBackendStatus] = useState('connecting')
  const [prompt, setPrompt] = useState('')
  const [isBuilding, setIsBuilding] = useState(false)
  const [errorMessage, setErrorMessage] = useState(null)

  // Pipeline execution state
  const [pipelineState, setPipelineState] = useState({ state: 'idle' })
  const [plan, setPlan] = useState(null)
  const [files, setFiles] = useState({})
  const [readme, setReadme] = useState('')
  const [testingResult, setTestingResult] = useState(null)
  const [logs, setLogs] = useState([])
  const [currentProjectId, setCurrentProjectId] = useState(null)

  // Archived projects list
  const [projects, setProjects] = useState([])

  // Check health and load projects
  useEffect(() => {
    checkHealth()
    loadProjects()
  }, [])

  const checkHealth = async () => {
    try {
      const res = await fetch('/api/health')
      if (res.ok) {
        setBackendStatus('online')
      } else {
        setBackendStatus('offline')
      }
    } catch (e) {
      setBackendStatus('offline')
    }
  }

  const loadProjects = async () => {
    try {
      const res = await fetch('/api/projects')
      if (res.ok) {
        const data = await res.json()
        setProjects(data.projects || [])
      }
    } catch (e) {
      console.error('Failed to load projects:', e)
    }
  }

  const handleLaunchBuild = () => {
    if (!prompt.trim() || isBuilding) return

    setIsBuilding(true)
    setErrorMessage(null)
    setPipelineState({ state: 'planning' })
    setFiles({})
    setReadme('')
    setTestingResult(null)
    setPlan(null)
    setLogs([`[Orchestrator] Initiating team swarm for prompt: "${prompt}"`])

    const url = `/api/build/stream?prompt=${encodeURIComponent(prompt)}`
    const eventSource = new EventSource(url)

    eventSource.addEventListener('log', (e) => {
      try {
        const payload = JSON.parse(e.data)
        setLogs((prev) => [...prev, `[${payload.agent}] ${payload.message}`])
      } catch (err) {}
    })

    eventSource.addEventListener('status', (e) => {
      try {
        const payload = JSON.parse(e.data)
        setPipelineState(payload)
        if (payload.state === 'completed' && payload.result) {
          const res = payload.result
          setPlan(res.plan)
          setReadme(res.readme)
          setTestingResult(res.check_result)
          if (res.project_dir) {
            const id = res.project_dir.split(/[\\/]/).pop()
            setCurrentProjectId(id)
          }
          loadProjects()
        }
      } catch (err) {}
    })

    eventSource.addEventListener('plan', (e) => {
      try {
        const payload = JSON.parse(e.data)
        setPlan(payload.plan)
      } catch (err) {}
    })

    eventSource.addEventListener('file_ready', (e) => {
      try {
        const payload = JSON.parse(e.data)
        setFiles((prev) => ({
          ...prev,
          [payload.path]: {
            code: payload.code,
            language: payload.language,
            audit: payload.audit,
          },
        }))
      } catch (err) {}
    })

    eventSource.addEventListener('testing_update', (e) => {
      try {
        const payload = JSON.parse(e.data)
        setTestingResult(payload.result)
      } catch (err) {}
    })

    eventSource.addEventListener('readme_ready', (e) => {
      try {
        const payload = JSON.parse(e.data)
        setReadme(payload.readme)
      } catch (err) {}
    })

    eventSource.addEventListener('error', (e) => {
      try {
        if (e.data) {
          const payload = JSON.parse(e.data)
          setErrorMessage(payload.error || 'Pipeline encountered an issue')
        }
      } catch (err) {}
    })

    eventSource.addEventListener('done', () => {
      setIsBuilding(false)
      eventSource.close()
      loadProjects()
    })

    eventSource.onerror = () => {
      setIsBuilding(false)
      eventSource.close()
    }
  }

  const handleLoadArchivedProject = async (projectId) => {
    try {
      const res = await fetch(`/api/projects/${projectId}`)
      if (res.ok) {
        const data = await res.json()
        setFiles(data.files || {})
        setReadme(data.readme || '')
        setCurrentProjectId(projectId)
        setPlan({ project_name: projectId, summary: 'Archived Project' })
        setPipelineState({ state: 'completed' })
        setActiveTab('studio')
      }
    } catch (e) {
      console.error('Failed to load project:', e)
    }
  }

  const handleDownloadZip = (projId = null) => {
    const targetId = projId || currentProjectId
    if (!targetId) return
    window.open(`/api/projects/${targetId}/download`, '_blank')
  }

  return (
    <div className="app-container">
      <Navbar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        backendStatus={backendStatus}
        projectCount={projects.length}
      />

      <main className="main-content">
        {activeTab === 'studio' ? (
          <>
            {/* Input Prompt Section */}
            <div className="glass-panel-glow prompt-card">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}>
                <Sparkles size={18} color="#818cf8" />
                <h2 style={{ fontSize: '1.15rem', fontWeight: 600 }}>
                  What do you want the agent team to build?
                </h2>
              </div>

              <textarea
                className="prompt-textarea"
                placeholder="Describe your desired project, application, CLI, or website in detail..."
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                disabled={isBuilding}
                rows={3}
              />

              <div className="prompt-actions">
                <div className="template-chips">
                  {SAMPLE_PROMPTS.map((p, i) => (
                    <button
                      key={i}
                      className="chip-btn"
                      onClick={() => setPrompt(p)}
                      disabled={isBuilding}
                    >
                      {p.slice(0, 34)}...
                    </button>
                  ))}
                </div>

                <button
                  className="launch-btn"
                  onClick={handleLaunchBuild}
                  disabled={isBuilding || !prompt.trim()}
                >
                  <Rocket size={17} />
                  <span>{isBuilding ? 'Swarm Working...' : 'Deploy CodeCrew'}</span>
                </button>
              </div>

              {errorMessage && (
                <div
                  style={{
                    marginTop: '14px',
                    padding: '10px 14px',
                    background: 'rgba(239, 68, 68, 0.15)',
                    border: '1px solid rgba(239, 68, 68, 0.4)',
                    borderRadius: '8px',
                    color: '#fca5a5',
                    fontSize: '0.85rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                  }}
                >
                  <AlertCircle size={16} />
                  <span>{errorMessage}</span>
                </div>
              )}
            </div>

            {/* Specialist Agent Swarm Visualizer */}
            <AgentSwarm pipelineState={pipelineState} />

            {/* Workspace: File Tree, Code Viewer, Fact Checker & Test Results */}
            <Workspace
              files={files}
              readme={readme}
              plan={plan}
              logs={logs}
              testingResult={testingResult}
              projectId={currentProjectId}
              onDownloadZip={currentProjectId ? () => handleDownloadZip(currentProjectId) : null}
            />
          </>
        ) : (
          <ProjectArchive
            projects={projects}
            onLoadProject={handleLoadArchivedProject}
            onDownloadZip={handleDownloadZip}
          />
        )}
      </main>
    </div>
  )
}
