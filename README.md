# 🤖 CodeCrew — Autonomous Multi-Agent Engineering Swarm

[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-19+-61DAFB?logo=react&logoColor=black)](https://react.dev)
[![Vite](https://img.shields.io/badge/Vite-8+-646CFF?logo=vite&logoColor=white)](https://vite.dev)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)
[![Git Shield](https://img.shields.io/badge/Git%20Shield-Zero%20Leaks%20Verified-10b981?logo=git&logoColor=white)](#-security--github-safe-push-guide)

An industrial-grade multi-agent software engineering team where **each sub-agent operates as an isolated, top-tier specialist AI persona** (similar to elite Gemini / Claude reasoning models). 

CodeCrew transforms natural language prompts into complete, verified, multi-file software applications with **live line-by-line fact checking**, **zero dead code/bloat**, **multi-tier automated QA testing**, and a **modern React + FastAPI dashboard**.

---

## 🏛️ Architecture: Isolated Specialist Agent Swarm

Each agent possesses its own dedicated system instruction, reasoning persona, and domain standard:

```
[ User Request ]
       │
       ▼
🧠 [ 1. Principal Systems Architect (Planner) ]
       │  Deconstructs requirements, chooses tech stack, designs file dependency graph
       ▼
💻 [ 2. Staff Polyglot Engineer (Coder) ] (Parallel Waves)
       │  Writes surgical, zero-stub code synchronized across contracts
       ▼
🔍 [ 3. Code Auditor & Fact-Checker (Auditor) ]
       │  Line-by-line fact verification (standard libs & APIs), eliminates dead/unneeded code
       ▼
🧪 [ 4. QA Automation Architect (Tester) ]
       │  Multi-language syntax verification + PyTest suite execution in sandbox + contract audit
       ▼ (if issues found)
🛠️ [ 5. Root-Cause Triage Specialist (Debugger) ]
       │  Surgical minimal-diff patch without regressions ──► [ Re-Audited by Auditor ]
       ▼ (when all checks pass)
📝 [ 6. Lead Technical Writer (Reviewer) ]
       │  Generates executable README.md with exact setup and run commands
       ▼
💾 [ Generated Project on Disk + Zip Export ]
```

### 🧠 The Specialist Roster
1. **Principal Systems Architect (`planner_agent.py`)**:
   Deconstructs high-level concepts into minimal, robust architectural blueprints. Eliminates redundant abstractions before coding begins.
2. **Staff Polyglot Engineer (`coder_agent.py`)**:
   Deep domain mastery in Python, JavaScript/TypeScript, HTML/CSS, SQL, etc. Writes zero-bloat, production-ready code with exact cross-file contract synchronization.
3. **Code Auditor & Fact-Checker (`auditor_agent.py`)**:
   **Line-by-line fact and logic verification.** Confirms that every invoked function, library method, and parameter actually exists in real runtimes. Strips unused lines, dead code, and redundant comments.
4. **QA Automation Architect (`testing_agent.py`)**:
   Three-layer verification: language-specific syntax validation, live PyTest execution in isolated sandboxes, and whole-project contract review.
5. **Root-Cause Triage Specialist (`debugger_agent.py`)**:
   Minimal-diff philosophy: isolates exact failure points without touching working code or adding bloat.
6. **Lead Technical Writer (`reviewer_agent.py`)**:
   Authors clear, beginner-friendly, executable documentation.

---

## 🚀 Quick Start Guide

### 1. Environment Setup
Create and activate your Python virtual environment:
```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate
```

Install backend dependencies:
```bash
pip install -r requirements.txt
```

### 2. Configure Your API Key
Copy the template configuration file:
```bash
copy .env.example .env     # Windows
cp .env.example .env       # Linux / macOS
```
Edit `.env` and insert your Gemini API Key from [Google AI Studio](https://aistudio.google.com/):
```env
GEMINI_API_KEY=your_actual_key_here
GEMINI_MODEL=gemini-2.5-flash
```

> **Note**: Your `.env` file is protected by `.gitignore` and `verify_security.py` so it will **never** be pushed to GitHub.

### 3. Run Development Environment
You can launch both the **FastAPI Backend** and the **React Frontend** with a single command:
```bash
python run_dev.py
```
- **React Frontend Studio**: [http://localhost:5173](http://localhost:5173)
- **FastAPI Backend & API Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Production Build**: [http://127.0.0.1:8000](http://127.0.0.1:8000)

Alternatively, run each service independently:
- **Backend**: `uvicorn server:app --reload --port 8000`
- **Frontend**: `cd frontend && npm run dev`

---

## 🛡️ Security & GitHub Safe Push Guide

This repository has a built-in pre-push security verification script (`verify_security.py`) to guarantee **zero API keys, credentials, or private files are leaked to GitHub**.

### Step 1: Run the Security Audit
Before committing or pushing, run:
```bash
python verify_security.py
```
Expected output:
```text
[1/2] Checking Git tracking and ignored files...
  [OK] .env is properly ignored and not tracked by Git.
[2/2] Scanning codebase files for accidental secret leaks...
  [OK] No secrets or leaked keys detected across the project!

>>> SECURITY AUDIT PASSED: Safe to commit and push to GitHub.
```

### Step 2: Commit Your Code
```bash
git add .
git commit -m "feat: complete CodeCrew v2 with React, FastAPI, and Fact-Checking Specialist Agents"
```

### Step 3: Push to Your GitHub Repository
1. Create a new empty repository on [GitHub](https://github.com/new).
2. Connect and push your code:
```bash
git remote add origin https://github.com/<YOUR_USERNAME>/<YOUR_REPOSITORY_NAME>.git
git branch -M main
git push -u origin main
```

---

## 📁 Repository Structure
```
codecrew/
├── .env.example              # Sanitized configuration template (safe to commit)
├── .gitignore                # Bulletproof ignore rules (blocks .env, venv, caches, builds)
├── verify_security.py        # Automated pre-push secret scanner
├── requirements.txt          # Python dependencies (FastAPI, Uvicorn, SSE, PyTest, Gemini)
├── config.py                 # Centralized configuration loader
├── orchestrator.py           # Wave-based parallel multi-agent pipeline with live SSE streaming
├── server.py                 # FastAPI backend with REST & SSE endpoints
├── run_dev.py                # Concurrently launches FastAPI & React
│
├── agents/                   # Isolated Specialist AI Agents
│   ├── llm_client.py         # Unified LLM client with system instruction isolation
│   ├── planner_agent.py      # Principal Systems Architect
│   ├── coder_agent.py        # Staff Polyglot Engineer
│   ├── auditor_agent.py      # Code Auditor & Fact-Checker
│   ├── testing_agent.py      # QA Automation Architect (PyTest + Syntax + Contract QA)
│   ├── debugger_agent.py     # Root-Cause Triage Specialist
│   ├── reviewer_agent.py     # Lead Technical Writer
│   ├── language_utils.py     # Multi-language syntax checkers
│   └── code_utils.py         # Response parsing & code extraction
│
├── frontend/                 # Modern React 19 + Vite Web Application
│   ├── src/
│   │   ├── components/
│   │   │   ├── Navbar.jsx          # Status bar & Git Shield indicator
│   │   │   ├── AgentSwarm.jsx      # Live visualizer for all 6 specialist agents
│   │   │   ├── Workspace.jsx       # File tree, Code viewer, Fact-check inspector & Tests
│   │   │   └── ProjectArchive.jsx  # History of generated builds with zip download
│   │   ├── App.jsx                 # Real-time SSE streaming coordinator
│   │   ├── App.css                 # Sleek UI design tokens & micro-animations
│   │   └── index.css               # Modern typography & glassmorphism theme
│   └── vite.config.js              # Reverse proxy to FastAPI (:8000)
│
└── generated_projects/       # Destination for finished projects (ignored by git)
```

---

## 📄 License
MIT License. Created with ❤️ for autonomous AI software engineering.
