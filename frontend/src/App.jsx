import React, { useState, useEffect } from 'react'
import TitleBar from './components/TitleBar'
import ActivityBar from './components/ActivityBar'
import Sidebar from './components/Sidebar'
import EditorWorkspace from './components/EditorWorkspace'
import CopilotPanel from './components/CopilotPanel'
import './App.css'

export default function App() {
  // Navigation & Layout states
  const [activeNav, setActiveNav] = useState('explorer') // 'explorer' | 'archive' | 'agents'
  const [terminalOpen, setTerminalOpen] = useState(true)
  const [livePreview, setLivePreview] = useState(false)
  const [selectedFile, setSelectedFile] = useState('')

  // Backend & Pipeline execution state
  const [backendStatus, setBackendStatus] = useState('connecting')
  const [prompt, setPrompt] = useState('')
  const [isBuilding, setIsBuilding] = useState(false)
  const [isIterating, setIsIterating] = useState(false)
  const [errorMessage, setErrorMessage] = useState(null)

  const [pipelineState, setPipelineState] = useState({ state: 'idle' })
  const [plan, setPlan] = useState(null)
  const [triagePlan, setTriagePlan] = useState(null)
  const [files, setFiles] = useState({})
  const [readme, setReadme] = useState('')
  const [testingResult, setTestingResult] = useState(null)
  const [logs, setLogs] = useState([])
  const [currentProjectId, setCurrentProjectId] = useState(null)

  // Archived projects list
  const [projects, setProjects] = useState([])

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

  // 1. Initial Build Swarm Trigger
  const handleLaunchBuild = (inputPrompt) => {
    const targetPrompt = inputPrompt || prompt
    if (!targetPrompt.trim() || isBuilding || isIterating) return

    setIsBuilding(true)
    setErrorMessage(null)
    setPipelineState({ state: 'planning' })
    setFiles({})
    setReadme('')
    setTestingResult(null)
    setPlan(null)
    setTriagePlan(null)
    setLivePreview(false)
    setTerminalOpen(true)
    setLogs([`[Orchestrator] Initiating multi-agent swarm for prompt: "${targetPrompt}"`])

    const url = `/api/build/stream?prompt=${encodeURIComponent(targetPrompt)}`
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
        setFiles((prev) => {
          const updated = {
            ...prev,
            [payload.path]: {
              code: payload.code,
              language: payload.language,
              audit: payload.audit,
            },
          }
          if (!selectedFile || selectedFile === 'README.md') {
            setSelectedFile(payload.path)
          }
          return updated
        })
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

  // 2. Selective Iteration Trigger
  const handleLaunchIteration = (changePrompt) => {
    if (!currentProjectId || !changePrompt.trim() || isIterating || isBuilding) return

    setIsIterating(true)
    setErrorMessage(null)
    setPipelineState({ state: 'triaging', message: 'Orchestrator triaging request...' })
    setTerminalOpen(true)
    setLogs((prev) => [
      ...prev,
      `[Orchestrator] Triaging change request: "${changePrompt}"`,
    ])

    const url = `/api/projects/${currentProjectId}/iterate/stream?prompt=${encodeURIComponent(changePrompt)}`
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
      } catch (err) {}
    })

    eventSource.addEventListener('orchestrator_triage', (e) => {
      try {
        const payload = JSON.parse(e.data)
        setTriagePlan(payload.plan)
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
            audit: payload.audit || prev[payload.path]?.audit,
          },
        }))
        setSelectedFile(payload.path)
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
          setErrorMessage(payload.error || 'Iteration error')
        }
      } catch (err) {}
    })

    eventSource.addEventListener('done', () => {
      setIsIterating(false)
      eventSource.close()
      loadProjects()
    })

    eventSource.onerror = () => {
      setIsIterating(false)
      eventSource.close()
    }
  }

  // Load project from archive
  const handleLoadArchivedProject = async (projectId) => {
    try {
      const res = await fetch(`/api/projects/${projectId}`)
      if (res.ok) {
        const data = await res.json()
        setFiles(data.files || {})
        setReadme(data.readme || '')
        setCurrentProjectId(projectId)
        const keys = Object.keys(data.files || {})
        if (keys.length > 0) setSelectedFile(keys[0])
        setPlan({ project_name: projectId, summary: 'Loaded Project' })
        setPipelineState({ state: 'completed' })
        setActiveNav('explorer')
      }
    } catch (e) {
      console.error('Failed to load project:', e)
    }
  }

  const handleDownloadZip = () => {
    if (!currentProjectId) return
    window.open(`/api/projects/${currentProjectId}/download`, '_blank')
  }

  const handleNewProject = () => {
    setCurrentProjectId(null)
    setFiles({})
    setReadme('')
    setSelectedFile('')
    setPlan(null)
    setTriagePlan(null)
    setPipelineState({ state: 'idle' })
    setPrompt('')
  }

  const hasHtml = Boolean(files['index.html'] || Object.values(files).some((f) => f.language === 'html'))

  return (
    <div className="antigravity-studio-root">
      {/* 1. IDE Top Titlebar */}
      <TitleBar
        projectName={currentProjectId}
        backendStatus={backendStatus}
        onDownloadZip={handleDownloadZip}
        hasFiles={Object.keys(files).length > 0}
        livePreview={livePreview}
        onToggleLivePreview={() => setLivePreview(!livePreview)}
        hasHtml={hasHtml}
        onNewProject={handleNewProject}
      />

      {/* 2. Main Studio Workspace Layout */}
      <div className="ide-layout-body">
        {/* Activity Bar (48px left icon bar) */}
        <ActivityBar
          activeNav={activeNav}
          setActiveNav={setActiveNav}
          projectCount={projects.length}
          terminalOpen={terminalOpen}
          onToggleTerminal={() => setTerminalOpen(!terminalOpen)}
        />

        {/* Sidebar (240px Collapsible Explorer & Archive) */}
        <Sidebar
          activeNav={activeNav}
          files={files}
          selectedFile={selectedFile}
          onSelectFile={(path) => {
            setSelectedFile(path)
            setLivePreview(false)
          }}
          readme={readme}
          projectId={currentProjectId}
          projects={projects}
          onLoadProject={handleLoadArchivedProject}
          onDownloadZip={handleDownloadZip}
          onNewProject={handleNewProject}
        />

        {/* Center Editor Stage & Terminal Dock */}
        <EditorWorkspace
          files={files}
          selectedFile={selectedFile}
          onSelectFile={(path) => {
            setSelectedFile(path)
            setLivePreview(false)
          }}
          readme={readme}
          logs={logs}
          testingResult={testingResult}
          terminalOpen={terminalOpen}
          onToggleTerminal={() => setTerminalOpen(!terminalOpen)}
          livePreview={livePreview}
          onToggleLivePreview={() => setLivePreview(!livePreview)}
          onSelectSamplePrompt={(p) => setPrompt(p)}
        />

        {/* Right Copilot & Agent Swarm Panel */}
        <CopilotPanel
          pipelineState={pipelineState}
          isBuilding={isBuilding}
          isIterating={isIterating}
          onLaunchBuild={handleLaunchBuild}
          onLaunchIteration={handleLaunchIteration}
          prompt={prompt}
          setPrompt={setPrompt}
          triagePlan={triagePlan}
          projectId={currentProjectId}
          errorMessage={errorMessage}
        />
      </div>
    </div>
  )
}
