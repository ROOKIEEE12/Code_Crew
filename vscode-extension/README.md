# CodeCrew - Multi-Agent Autonomous Studio for VS Code

Bring the full power of **CodeCrew's autonomous software engineering team** directly inside Visual Studio Code. Instead of context switching to external web apps or rebuilding an IDE, CodeCrew lives directly in your VS Code sidebar, status bar, and editor context menus.

---

## 🚀 Key Features

### 1. Dedicated Multi-Agent Crew
- **🧠 Principal Systems Architect (Planner Agent)**: Deconstructs features into atomic specifications, contracts, and dependency graphs.
- **💻 Senior Staff Polyglot Engineer (Coder Agent)**: Writes production-ready code with surgical economy and zero bloat.
- **🔍 Principal Code Auditor & Fact-Checker (Auditor Agent)**: Line-by-line verification, API validation, eliminates dead code.
- **🧪 QA Automation Architect (Testing Agent)**: Multi-tier syntax verification, PyTest execution, and automated test generation.
- **🔧 Autonomous Runtime Debugger (Debugger Agent)**: Surgical root-cause fixing with minimal diffs.
- **📝 Lead Technical Writer (Reviewer Agent)**: Runnable documentation and architectural guides.

### 2. Gemini Multi-Model Free-Tier Pool
- Live telemetry monitor directly in the sidebar.
- Automatic failover across free models: `gemini-3.8-flash`, `gemini-3.7-flash`, `gemini-3.6-flash`, `gemini-3.5-flash-lite`, and Pro variants.
- Real-time cooldown tracking and zero-rate-limit stall protection.

### 3. Native VS Code Integration
- **Activity Bar View**: Interactive CodeCrew Studio panel.
- **1-Click File Actions**:
  - `Audit Active File`: Fact-checks code and eliminates unnecessary lines.
  - `Generate Tests`: Automatically writes QA unit tests into your project.
  - `Refactor Selected Code`: Staff-level code refactoring directly on your cursor selection.
  - `Surgical Debug`: Uses VS Code diagnostics/errors to automatically fix bugs.
- **Direct Workspace Output**: Generated full-stack projects are written directly into your open workspace folder.

---

## 🛠️ Getting Started

### Prerequisites
- Python 3.10+ installed
- Gemini API key set in `.env` (`GEMINI_API_KEY=your_key` or `GEMINI_API_KEYS=key1,key2`)

### Running the Extension in VS Code
1. Open this repository in VS Code.
2. Build the extension:
   ```bash
   cd vscode-extension
   npm run build
   ```
3. Press `F5` (or go to **Run & Debug** -> **Run Extension**) to launch an Extension Development Host window with CodeCrew preloaded!
4. Or package and install the `.vsix`:
   ```bash
   npm run package
   code --install-extension codecrew-extension-1.0.0.vsix
   ```
