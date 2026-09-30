import * as vscode from 'vscode';
import * as http from 'http';
import * as path from 'path';
import { CodeCrewBackendManager } from './CodeCrewBackendManager';

export class CodeCrewSidebarProvider implements vscode.WebviewViewProvider {
    public static readonly viewType = 'codecrew.agentView';
    private _view?: vscode.WebviewView;

    constructor(
        private readonly _extensionUri: vscode.Uri,
        private readonly backendManager: CodeCrewBackendManager
    ) {}

    public resolveWebviewView(
        webviewView: vscode.WebviewView,
        context: vscode.WebviewViewResolveContext,
        _token: vscode.CancellationToken
    ) {
        this._view = webviewView;

        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [this._extensionUri],
        };

        webviewView.webview.html = this._getHtmlForWebview(webviewView.webview);

        webviewView.webview.onDidReceiveMessage(async (data) => {
            switch (data.type) {
                case 'ready': {
                    await this.syncState();
                    break;
                }
                case 'startServer': {
                    const ok = await this.backendManager.startServer();
                    if (ok) {
                        vscode.window.showInformationMessage('CodeCrew Engine Server started successfully!');
                    } else {
                        vscode.window.showErrorMessage('Could not start CodeCrew Engine. Check terminal or logs.');
                    }
                    await this.syncState();
                    break;
                }
                case 'refreshTelemetry': {
                    await this.syncState();
                    break;
                }
                case 'buildProject': {
                    await this.handleBuildProject(data.prompt);
                    break;
                }
                case 'applyToWorkspace': {
                    await this.handleApplyToWorkspace(data.files, data.projectName);
                    break;
                }
                case 'auditActiveFile': {
                    await this.handleAuditActiveFile();
                    break;
                }
                case 'generateTestsForActiveFile': {
                    await this.handleGenerateTests();
                    break;
                }
                case 'refactorSelection': {
                    await this.handleRefactorSelection(data.instruction);
                    break;
                }
                case 'debugActiveFile': {
                    await this.handleDebugActiveFile();
                    break;
                }
                case 'applyFileUpdate': {
                    await this.handleApplyFileUpdate(data.filePath, data.code);
                    break;
                }
                case 'openDiffPreview': {
                    await this.handleOpenDiff(data.filePath, data.originalCode, data.newCode);
                    break;
                }
            }
        });
    }

    public async syncState() {
        const isHealthy = await this.backendManager.checkHealth();
        const telemetry = isHealthy ? await this.backendManager.getModelTelemetry() : null;
        const agents = isHealthy ? await this.backendManager.getAgents() : [];

        const activeEditor = vscode.window.activeTextEditor;
        const activeFile = activeEditor ? {
            name: path.basename(activeEditor.document.fileName),
            path: activeEditor.document.fileName,
            language: activeEditor.document.languageId,
            lineCount: activeEditor.document.lineCount,
            hasSelection: !activeEditor.selection.isEmpty,
        } : null;

        this.postMessage({
            type: 'stateUpdate',
            payload: {
                isHealthy,
                telemetry,
                agents,
                activeFile,
                workspaceName: vscode.workspace.name || 'Workspace',
            },
        });
    }

    private postMessage(msg: any) {
        this._view?.webview.postMessage(msg);
    }

    private async handleBuildProject(prompt: string) {
        if (!prompt || prompt.trim().length < 2) {
            vscode.window.showWarningMessage('Please enter a descriptive project prompt.');
            return;
        }

        const isHealthy = await this.backendManager.ensureBackendRunning();
        if (!isHealthy) {
            vscode.window.showErrorMessage('CodeCrew Engine server is not running. Please start it first.');
            return;
        }

        this.postMessage({ type: 'buildStarted', prompt });

        const url = new URL('/api/build/stream', this.backendManager.getBackendUrl());
        url.searchParams.set('prompt', prompt);

        const req = http.get(url.toString(), (res) => {
            let buffer = '';
            res.on('data', (chunk) => {
                buffer += chunk.toString();
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                let currentEvent = 'message';
                for (const line of lines) {
                    if (line.startsWith('event:')) {
                        currentEvent = line.replace('event:', '').trim();
                    } else if (line.startsWith('data:')) {
                        const rawData = line.replace('data:', '').trim();
                        if (rawData) {
                            try {
                                const parsed = JSON.parse(rawData);
                                this.postMessage({
                                    type: 'sseEvent',
                                    event: currentEvent,
                                    data: parsed,
                                });

                                // Auto-write to workspace if completed and enabled
                                if (currentEvent === 'build_complete' || parsed.files) {
                                    const config = vscode.workspace.getConfiguration('codecrew');
                                    if (config.get<boolean>('autoWriteFiles', true) && parsed.files) {
                                        this.handleApplyToWorkspace(parsed.files, parsed.project_name || 'codecrew_project');
                                    }
                                }
                            } catch {
                                // Non-json SSE data
                            }
                        }
                    }
                }
            });

            res.on('end', () => {
                this.postMessage({ type: 'buildFinished' });
                this.syncState();
            });
        });

        req.on('error', (err) => {
            this.postMessage({ type: 'buildError', error: err.message });
        });
    }

    private async handleApplyToWorkspace(files: Record<string, any>, projectName: string) {
        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (!workspaceFolders || workspaceFolders.length === 0) {
            vscode.window.showWarningMessage('Open a workspace folder in VS Code to save generated files.');
            return;
        }

        const rootUri = workspaceFolders[0].uri;
        let writtenCount = 0;

        try {
            for (const [relPath, fileObj] of Object.entries(files)) {
                const code = typeof fileObj === 'string' ? fileObj : fileObj.code;
                const fileUri = vscode.Uri.joinPath(rootUri, relPath);
                
                // Ensure parent directories exist
                const parentDir = vscode.Uri.file(path.dirname(fileUri.fsPath));
                await vscode.workspace.fs.createDirectory(parentDir);
                
                const buffer = Buffer.from(code, 'utf8');
                await vscode.workspace.fs.writeFile(fileUri, buffer);
                writtenCount++;
            }

            vscode.window.showInformationMessage(`CodeCrew: Successfully wrote ${writtenCount} files into workspace!`);

            // Open the first main file or README
            const candidate = Object.keys(files).find(k => k.includes('main') || k.includes('app') || k.includes('index') || k.includes('README'));
            if (candidate) {
                const targetUri = vscode.Uri.joinPath(rootUri, candidate);
                const doc = await vscode.workspace.openTextDocument(targetUri);
                await vscode.window.showTextDocument(doc);
            }
        } catch (err: any) {
            vscode.window.showErrorMessage(`Error writing to workspace: ${err.message}`);
        }
    }

    public async handleAuditActiveFile() {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showWarningMessage('Please open a file in VS Code to audit.');
            return;
        }

        const document = editor.document;
        const code = document.getText();
        const filePath = document.fileName;
        const language = document.languageId;

        vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: `CodeCrew Auditor: Fact-checking ${path.basename(filePath)}...`,
            cancellable: false
        }, async () => {
            try {
                this.postMessage({ type: 'actionLoading', action: 'audit' });
                const res = await this.backendManager.auditCode(filePath, code, language, 'VS Code active document');
                this.postMessage({
                    type: 'auditResult',
                    filePath,
                    language,
                    originalCode: code,
                    result: res.result,
                });
            } catch (err: any) {
                vscode.window.showErrorMessage(`Audit error: ${err.message}`);
                this.postMessage({ type: 'actionError', error: err.message });
            }
        });
    }

    public async handleGenerateTests() {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showWarningMessage('Please open a file to generate tests for.');
            return;
        }

        const document = editor.document;
        const code = document.getText();
        const filePath = document.fileName;
        const language = document.languageId;

        vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: `CodeCrew QA Tester: Generating test suite for ${path.basename(filePath)}...`,
            cancellable: false
        }, async () => {
            try {
                this.postMessage({ type: 'actionLoading', action: 'test' });
                const res = await this.backendManager.testCode(filePath, code, language);
                
                // Write test file in workspace next to or in tests/
                const workspaceFolder = vscode.workspace.getWorkspaceFolder(document.uri);
                if (workspaceFolder) {
                    const testUri = vscode.Uri.joinPath(document.uri, '..', res.test_file);
                    await vscode.workspace.fs.writeFile(testUri, Buffer.from(res.code, 'utf8'));
                    const testDoc = await vscode.workspace.openTextDocument(testUri);
                    await vscode.window.showTextDocument(testDoc, vscode.ViewColumn.Beside);
                    vscode.window.showInformationMessage(`Generated QA Test Suite: ${res.test_file}`);
                }

                this.postMessage({
                    type: 'testResult',
                    testFile: res.test_file,
                    code: res.code,
                });
            } catch (err: any) {
                vscode.window.showErrorMessage(`Test generation failed: ${err.message}`);
                this.postMessage({ type: 'actionError', error: err.message });
            }
        });
    }

    public async handleRefactorSelection(customInstruction?: string) {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showWarningMessage('Please select code in the editor to refactor.');
            return;
        }

        const selection = editor.selection;
        const code = selection.isEmpty ? editor.document.getText() : editor.document.getText(selection);
        const language = editor.document.languageId;
        const instruction = customInstruction || 'Refactor for surgical economy, high performance, and zero bloat';

        vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: 'CodeCrew Polyglot Coder: Refactoring selected code...',
            cancellable: false
        }, async () => {
            try {
                this.postMessage({ type: 'actionLoading', action: 'refactor' });
                const res = await this.backendManager.refactorCode(editor.document.fileName, code, language, instruction);
                this.postMessage({
                    type: 'refactorResult',
                    filePath: editor.document.fileName,
                    originalCode: code,
                    refinedCode: res.code,
                    isSelection: !selection.isEmpty,
                });
            } catch (err: any) {
                vscode.window.showErrorMessage(`Refactoring error: ${err.message}`);
                this.postMessage({ type: 'actionError', error: err.message });
            }
        });
    }

    public async handleDebugActiveFile() {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
            vscode.window.showWarningMessage('Please open a file to debug.');
            return;
        }

        const document = editor.document;
        const diagnostics = vscode.languages.getDiagnostics(document.uri);
        const errorDescriptions = diagnostics.map(d => `Line ${d.range.start.line + 1}: ${d.message} [Severity: ${d.severity}]`).join('\n');

        if (!errorDescriptions) {
            vscode.window.showInformationMessage('No active VS Code diagnostics/errors found on this file. Asking Debugger for proactive verification...');
        }

        vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: `CodeCrew Debugger: Triaging root cause in ${path.basename(document.fileName)}...`,
            cancellable: false
        }, async () => {
            try {
                this.postMessage({ type: 'actionLoading', action: 'debug' });
                const res = await this.backendManager.debugCode(
                    document.fileName,
                    document.getText(),
                    document.languageId,
                    errorDescriptions || 'Analyze code for potential hidden runtime errors, memory leaks, and contract mismatches'
                );
                this.postMessage({
                    type: 'debugResult',
                    filePath: document.fileName,
                    originalCode: document.getText(),
                    fixedCode: res.code,
                    diagnostics: errorDescriptions,
                });
            } catch (err: any) {
                vscode.window.showErrorMessage(`Debugging failed: ${err.message}`);
                this.postMessage({ type: 'actionError', error: err.message });
            }
        });
    }

    public async handleApplyFileUpdate(filePath: string, newCode: string) {
        try {
            const uri = vscode.Uri.file(filePath);
            await vscode.workspace.fs.writeFile(uri, Buffer.from(newCode, 'utf8'));
            const doc = await vscode.workspace.openTextDocument(uri);
            await vscode.window.showTextDocument(doc);
            vscode.window.showInformationMessage(`Applied updates to ${path.basename(filePath)}!`);
        } catch (err: any) {
            vscode.window.showErrorMessage(`Could not apply updates: ${err.message}`);
        }
    }

    public async handleOpenDiff(filePath: string, originalCode: string, newCode: string) {
        try {
            const originalUri = vscode.Uri.parse(`codecrew-preview:original/${path.basename(filePath)}?${encodeURIComponent(originalCode)}`);
            const newUri = vscode.Uri.parse(`codecrew-preview:refined/${path.basename(filePath)}?${encodeURIComponent(newCode)}`);
            await vscode.commands.executeCommand('vscode.diff', originalUri, newUri, `CodeCrew Auditor: ${path.basename(filePath)} (Proposed Diff)`);
        } catch (e: any) {
            // Fallback: apply directly or notify
            vscode.window.showInformationMessage('Inspect proposed changes in the CodeCrew panel.');
        }
    }

    private _getHtmlForWebview(webview: vscode.Webview): string {
        const nonce = getNonce();
        return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CodeCrew Studio</title>
    <style>
        :root {
            --crew-bg: var(--vscode-sideBar-background, #0f172a);
            --crew-fg: var(--vscode-sideBar-foreground, #f8fafc);
            --crew-card: var(--vscode-editor-background, #1e293b);
            --crew-border: var(--vscode-panel-border, #334155);
            --crew-primary: var(--vscode-button-background, #3b82f6);
            --crew-primary-hover: var(--vscode-button-hoverBackground, #2563eb);
            --crew-accent: #8b5cf6;
            --crew-success: #10b981;
            --crew-warning: #f59e0b;
            --crew-danger: #ef4444;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: var(--vscode-font-family, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif);
            font-size: var(--vscode-font-size, 13px);
            color: var(--crew-fg);
            background-color: var(--crew-bg);
            padding: 12px;
            overflow-x: hidden;
        }
        
        .header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding-bottom: 12px;
            border-bottom: 1px solid var(--crew-border);
            margin-bottom: 12px;
        }
        .header-title {
            display: flex;
            align-items: center;
            gap: 8px;
            font-weight: 700;
            font-size: 14px;
            letter-spacing: 0.5px;
            background: linear-gradient(135deg, #60a5fa 0%, #a78bfa 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            font-size: 11px;
            padding: 3px 8px;
            border-radius: 9999px;
            background: rgba(16, 185, 129, 0.15);
            color: var(--crew-success);
            border: 1px solid rgba(16, 185, 129, 0.3);
            font-weight: 600;
        }
        .status-badge.offline {
            background: rgba(239, 68, 68, 0.15);
            color: var(--crew-danger);
            border-color: rgba(239, 68, 68, 0.3);
        }
        .dot {
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background-color: currentColor;
            box-shadow: 0 0 6px currentColor;
        }

        .tabs {
            display: flex;
            gap: 4px;
            background: rgba(0, 0, 0, 0.25);
            padding: 3px;
            border-radius: 8px;
            margin-bottom: 14px;
        }
        .tab-btn {
            flex: 1;
            padding: 6px 4px;
            font-size: 11px;
            text-align: center;
            background: transparent;
            border: none;
            color: var(--vscode-descriptionForeground, #94a3b8);
            border-radius: 6px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.2s;
        }
        .tab-btn.active {
            background: var(--crew-card);
            color: var(--crew-fg);
            box-shadow: 0 1px 3px rgba(0,0,0,0.3);
        }

        .tab-content { display: none; }
        .tab-content.active { display: block; }

        .card {
            background: var(--crew-card);
            border: 1px solid var(--crew-border);
            border-radius: 8px;
            padding: 10px;
            margin-bottom: 12px;
        }

        .card-header {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--vscode-descriptionForeground, #94a3b8);
            margin-bottom: 8px;
            font-weight: 700;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        /* Action Buttons */
        .btn-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 8px;
            margin-bottom: 12px;
        }
        .action-btn {
            display: flex;
            flex-direction: column;
            align-items: flex-start;
            padding: 9px 10px;
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid var(--crew-border);
            border-radius: 8px;
            color: var(--crew-fg);
            cursor: pointer;
            transition: all 0.2s ease;
            text-align: left;
        }
        .action-btn:hover {
            background: rgba(255, 255, 255, 0.08);
            border-color: #60a5fa;
            transform: translateY(-1px);
        }
        .action-btn .btn-icon { font-size: 16px; margin-bottom: 4px; }
        .action-btn .btn-label { font-weight: 600; font-size: 12px; }
        .action-btn .btn-desc { font-size: 10px; color: var(--vscode-descriptionForeground, #94a3b8); margin-top: 2px; }

        /* Build Prompt Form */
        .prompt-input {
            width: 100%;
            min-height: 75px;
            background: rgba(0, 0, 0, 0.25);
            border: 1px solid var(--crew-border);
            border-radius: 6px;
            color: var(--crew-fg);
            padding: 8px;
            font-family: inherit;
            font-size: 12px;
            resize: vertical;
            margin-bottom: 8px;
        }
        .prompt-input:focus {
            outline: none;
            border-color: #60a5fa;
            box-shadow: 0 0 0 1px #60a5fa;
        }
        .primary-btn {
            width: 100%;
            padding: 8px 12px;
            background: linear-gradient(135deg, #3b82f6 0%, #6366f1 100%);
            border: none;
            border-radius: 6px;
            color: #fff;
            font-weight: 600;
            font-size: 12px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            transition: opacity 0.2s;
        }
        .primary-btn:hover { opacity: 0.9; }
        .primary-btn:disabled { opacity: 0.5; cursor: not-allowed; }

        /* Agents list */
        .agent-item {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 8px;
            border-radius: 6px;
            background: rgba(255, 255, 255, 0.02);
            border: 1px solid rgba(255, 255, 255, 0.05);
            margin-bottom: 6px;
        }
        .agent-avatar {
            width: 28px;
            height: 28px;
            border-radius: 6px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 15px;
            background: rgba(255, 255, 255, 0.08);
        }
        .agent-details { flex: 1; min-width: 0; }
        .agent-name { font-weight: 600; font-size: 12px; }
        .agent-role { font-size: 10px; color: var(--vscode-descriptionForeground, #94a3b8); }

        /* Stream logs */
        .stream-box {
            max-height: 260px;
            overflow-y: auto;
            background: rgba(0, 0, 0, 0.35);
            border: 1px solid var(--crew-border);
            border-radius: 6px;
            padding: 8px;
            font-family: var(--vscode-editor-font-family, monospace);
            font-size: 11px;
            line-height: 1.5;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }
        .log-entry {
            padding: 4px 6px;
            border-radius: 4px;
            background: rgba(255, 255, 255, 0.03);
            border-left: 3px solid #60a5fa;
            word-break: break-word;
        }
        .log-entry.phase { border-left-color: var(--crew-accent); font-weight: 600; }
        .log-entry.audit { border-left-color: var(--crew-success); }
        .log-entry.qa { border-left-color: var(--crew-warning); }
        .log-entry.error { border-left-color: var(--crew-danger); color: #fca5a5; }

        /* Model telemetry badges */
        .model-chip {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 6px 8px;
            border-radius: 6px;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--crew-border);
            margin-bottom: 5px;
            font-size: 11px;
        }
        .model-chip .tag {
            font-size: 10px;
            padding: 1px 6px;
            border-radius: 999px;
            font-weight: 600;
        }
        .tag-active { background: rgba(16, 185, 129, 0.2); color: #34d399; }
        .tag-cooldown { background: rgba(245, 158, 11, 0.2); color: #fbbf24; }

        .active-file-strip {
            display: flex;
            align-items: center;
            gap: 6px;
            padding: 6px 8px;
            background: rgba(59, 130, 246, 0.1);
            border: 1px solid rgba(59, 130, 246, 0.25);
            border-radius: 6px;
            margin-bottom: 10px;
            font-size: 11px;
        }
        .active-file-name { font-weight: 600; color: #93c5fd; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

        .result-box {
            background: rgba(0, 0, 0, 0.3);
            border: 1px solid var(--crew-border);
            border-radius: 6px;
            padding: 8px;
            margin-top: 8px;
            font-size: 11px;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="header-title">
            <span>✨</span> CodeCrew Studio
        </div>
        <div id="statusBadge" class="status-badge">
            <span class="dot"></span>
            <span id="statusText">Checking...</span>
        </div>
    </div>

    <!-- Active Open File Indicator -->
    <div id="activeFileStrip" class="active-file-strip" style="display: none;">
        <span>📄</span>
        <span class="active-file-name" id="activeFileName">No file open</span>
    </div>

    <!-- Navigation Tabs -->
    <div class="tabs">
        <button class="tab-btn active" onclick="switchTab('actions')">Studio</button>
        <button class="tab-btn" onclick="switchTab('agents')">Crew</button>
        <button class="tab-btn" onclick="switchTab('models')">Models</button>
        <button class="tab-btn" onclick="switchTab('logs')">Live Stream</button>
    </div>

    <!-- TAB 1: STUDIO ACTIONS -->
    <div id="tab-actions" class="tab-content active">
        <!-- 1-Click File Actions -->
        <div class="card-header">
            <span>Active File Fast Actions</span>
        </div>
        <div class="btn-grid">
            <button class="action-btn" onclick="triggerAudit()">
                <div class="btn-icon">🔍</div>
                <div class="btn-label">Audit File</div>
                <div class="btn-desc">Fact-check & cut bloat</div>
            </button>
            <button class="action-btn" onclick="triggerTests()">
                <div class="btn-icon">🧪</div>
                <div class="btn-label">Generate Tests</div>
                <div class="btn-desc">QA test suite</div>
            </button>
            <button class="action-btn" onclick="triggerRefactor()">
                <div class="btn-icon">💻</div>
                <div class="btn-label">Refactor Code</div>
                <div class="btn-desc">Polyglot Staff Coder</div>
            </button>
            <button class="action-btn" onclick="triggerDebug()">
                <div class="btn-icon">🔧</div>
                <div class="btn-label">Surgical Debug</div>
                <div class="btn-desc">Fix diagnostics & errors</div>
            </button>
        </div>

        <!-- Full Autonomous Crew Builder -->
        <div class="card">
            <div class="card-header">
                <span>Autonomous Crew Generator</span>
            </div>
            <textarea id="promptInput" class="prompt-input" placeholder="Describe the app or feature to engineer (e.g. 'Build a high-performance REST API with authentication and SQLite')..."></textarea>
            <button id="btnBuild" class="primary-btn" onclick="startBuild()">
                <span>🚀</span> Deploy Agent Crew to Workspace
            </button>
        </div>

        <div id="actionResultContainer" style="display: none;">
            <div class="card-header">
                <span>Agent Output</span>
            </div>
            <div id="actionResultContent" class="result-box"></div>
        </div>
    </div>

    <!-- TAB 2: CREW AGENTS -->
    <div id="tab-agents" class="tab-content">
        <div class="card-header">
            <span>Autonomous Specialist Crew</span>
        </div>
        <div id="agentsList">
            <!-- Rendered dynamically -->
        </div>
    </div>

    <!-- TAB 3: MODEL ROTATION POOL -->
    <div id="tab-models" class="tab-content">
        <div class="card-header">
            <span>Gemini Free-Tier Telemetry</span>
            <button style="background: none; border: none; color: #60a5fa; cursor: pointer; font-size: 11px;" onclick="refreshTelemetry()">↻ Refresh</button>
        </div>
        <div id="modelsTelemetry">
            <!-- Rendered dynamically -->
        </div>
    </div>

    <!-- TAB 4: LIVE STREAM & LOGS -->
    <div id="tab-logs" class="tab-content">
        <div class="card-header">
            <span>Live Multi-Agent Stream</span>
            <button style="background: none; border: none; color: #94a3b8; cursor: pointer; font-size: 11px;" onclick="clearLogs()">Clear</button>
        </div>
        <div id="streamLogs" class="stream-box">
            <div class="log-entry">Waiting for agent activation...</div>
        </div>
    </div>

    <script nonce="${nonce}">
        const vscode = acquireVsCodeApi();
        let appState = {};
        let generatedFilesCache = null;

        function switchTab(tabId) {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            
            const btn = Array.from(document.querySelectorAll('.tab-btn')).find(b => b.getAttribute('onclick').includes(tabId));
            if (btn) btn.classList.add('active');
            
            const content = document.getElementById('tab-' + tabId);
            if (content) content.classList.add('active');
        }

        function appendLog(text, className = '') {
            const box = document.getElementById('streamLogs');
            const entry = document.createElement('div');
            entry.className = 'log-entry ' + className;
            entry.textContent = text;
            box.appendChild(entry);
            box.scrollTop = box.scrollHeight;
        }

        function clearLogs() {
            document.getElementById('streamLogs').innerHTML = '';
        }

        function updateUI(payload) {
            appState = payload;
            const badge = document.getElementById('statusBadge');
            const statusText = document.getElementById('statusText');

            if (payload.isHealthy) {
                badge.className = 'status-badge';
                const activeCount = payload.telemetry ? payload.telemetry.active_models : '6';
                statusText.textContent = 'Engine Online (' + activeCount + ' Models)';
            } else {
                badge.className = 'status-badge offline';
                statusText.textContent = 'Server Offline (Click to start)';
                badge.onclick = () => vscode.postMessage({ type: 'startServer' });
            }

            // Active File
            const activeStrip = document.getElementById('activeFileStrip');
            const activeName = document.getElementById('activeFileName');
            if (payload.activeFile) {
                activeStrip.style.display = 'flex';
                activeName.textContent = payload.activeFile.name + ' (' + payload.activeFile.language + ', ' + payload.activeFile.lineCount + ' lines)';
            } else {
                activeStrip.style.display = 'none';
            }

            // Agents
            if (payload.agents && payload.agents.length > 0) {
                const list = document.getElementById('agentsList');
                list.innerHTML = payload.agents.map(a => \`
                    <div class="agent-item">
                        <div class="agent-avatar" style="border-left: 3px solid \${a.color};">\${a.avatar}</div>
                        <div class="agent-details">
                            <div class="agent-name">\${a.name}</div>
                            <div class="agent-role">\${a.role}</div>
                        </div>
                    </div>
                \`).join('');
            }

            // Models Telemetry
            if (payload.telemetry && payload.telemetry.models) {
                const container = document.getElementById('modelsTelemetry');
                container.innerHTML = payload.telemetry.models.map(m => {
                    const tagClass = m.is_healthy ? 'tag tag-active' : 'tag tag-cooldown';
                    const tagLabel = m.is_healthy ? 'Ready' : 'Cooldown (' + m.cooldown_remaining_sec + 's)';
                    return \`
                        <div class="model-chip">
                            <div>
                                <span style="font-weight: 600;">\${m.name}</span>
                                <div style="font-size: 10px; color: #94a3b8;">Successes: \${m.success_count}</div>
                            </div>
                            <span class="\${tagClass}">\${tagLabel}</span>
                        </div>
                    \`;
                }).join('');
            }
        }

        function startBuild() {
            const prompt = document.getElementById('promptInput').value;
            if (!prompt) return;
            switchTab('logs');
            appendLog('🚀 Launching CodeCrew Autonomous Pipeline for: ' + prompt, 'phase');
            vscode.postMessage({ type: 'buildProject', prompt });
        }

        function triggerAudit() {
            vscode.postMessage({ type: 'auditActiveFile' });
        }

        function triggerTests() {
            vscode.postMessage({ type: 'generateTestsForActiveFile' });
        }

        function triggerRefactor() {
            const instruction = prompt('Refactor instruction (optional):', 'Refactor for surgical economy, high performance, and clean contracts');
            if (instruction !== null) {
                vscode.postMessage({ type: 'refactorSelection', instruction });
            }
        }

        function triggerDebug() {
            vscode.postMessage({ type: 'debugActiveFile' });
        }

        function refreshTelemetry() {
            vscode.postMessage({ type: 'refreshTelemetry' });
        }

        // Handle Extension Messages
        window.addEventListener('message', event => {
            const msg = event.data;
            switch (msg.type) {
                case 'stateUpdate':
                    updateUI(msg.payload);
                    break;
                case 'sseEvent':
                    handleSseEvent(msg.event, msg.data);
                    break;
                case 'auditResult':
                    showAuditResult(msg);
                    break;
                case 'testResult':
                    appendLog('✅ Generated test suite: ' + msg.testFile, 'qa');
                    break;
                case 'refactorResult':
                    showRefactorResult(msg);
                    break;
                case 'debugResult':
                    showDebugResult(msg);
                    break;
                case 'actionLoading':
                    appendLog('⏳ Running ' + msg.action + ' agent...', 'phase');
                    break;
                case 'actionError':
                    appendLog('❌ Error: ' + msg.error, 'error');
                    break;
            }
        });

        function handleSseEvent(eventType, data) {
            if (eventType === 'phase_change') {
                appendLog('🔄 [' + (data.phase || 'PIPELINE') + '] ' + (data.message || ''), 'phase');
            } else if (eventType === 'plan_created') {
                appendLog('🧠 Plan generated with ' + (data.plan?.files?.length || 0) + ' files.', 'phase');
            } else if (eventType === 'file_generating') {
                appendLog('💻 Polyglot Coder generating: ' + data.path);
            } else if (eventType === 'file_audited') {
                const res = data.audit_result || {};
                appendLog('🔍 Auditor fact-checked ' + data.path + ' (Passed: ' + res.fact_check_passed + ', Removed: ' + (res.unnecessary_lines_removed || 0) + ' lines)', 'audit');
            } else if (eventType === 'qa_testing') {
                appendLog('🧪 QA Testing: ' + (data.message || 'Verifying contracts & syntax'), 'qa');
            } else if (eventType === 'build_complete') {
                appendLog('🎉 Autonomous Crew Complete! Project saved to workspace.', 'phase');
            } else {
                appendLog('ℹ️ ' + JSON.stringify(data));
            }
        }

        function showAuditResult(msg) {
            switchTab('actions');
            const res = msg.result || {};
            const container = document.getElementById('actionResultContainer');
            const content = document.getElementById('actionResultContent');
            container.style.display = 'block';
            content.innerHTML = \`
                <div style="font-weight: 600; color: #10b981; margin-bottom: 4px;">✅ Auditor Fact-Check Complete</div>
                <div>Lines Analyzed: <strong>\${res.lines_analyzed || 'N/A'}</strong></div>
                <div>Bloat Lines Removed: <strong style="color: #f59e0b;">\${res.unnecessary_lines_removed || 0}</strong></div>
                <div style="margin-top: 6px; color: #94a3b8;">\${res.audit_notes || 'Clean and verified'}</div>
                <div style="display: flex; gap: 6px; margin-top: 8px;">
                    <button class="primary-btn" style="flex: 1; padding: 5px;" onclick="applyFileUpdate('\${msg.filePath.replace(/\\\\/g, '\\\\\\\\')}', decodeURIComponent('\${encodeURIComponent(res.refined_code || msg.originalCode)}'))">Accept & Save</button>
                    <button class="action-btn" style="padding: 5px 10px;" onclick="openDiff('\${msg.filePath.replace(/\\\\/g, '\\\\\\\\')}', decodeURIComponent('\${encodeURIComponent(msg.originalCode)}'), decodeURIComponent('\${encodeURIComponent(res.refined_code || msg.originalCode)}'))">Diff</button>
                </div>
            \`;
        }

        function showRefactorResult(msg) {
            switchTab('actions');
            const container = document.getElementById('actionResultContainer');
            const content = document.getElementById('actionResultContent');
            container.style.display = 'block';
            content.innerHTML = \`
                <div style="font-weight: 600; color: #60a5fa; margin-bottom: 4px;">💻 Polyglot Coder Refactored</div>
                <div style="display: flex; gap: 6px; margin-top: 8px;">
                    <button class="primary-btn" style="flex: 1; padding: 5px;" onclick="applyFileUpdate('\${msg.filePath.replace(/\\\\/g, '\\\\\\\\')}', decodeURIComponent('\${encodeURIComponent(msg.refinedCode)}'))">Apply Changes</button>
                </div>
            \`;
        }

        function showDebugResult(msg) {
            switchTab('actions');
            const container = document.getElementById('actionResultContainer');
            const content = document.getElementById('actionResultContent');
            container.style.display = 'block';
            content.innerHTML = \`
                <div style="font-weight: 600; color: #ef4444; margin-bottom: 4px;">🔧 Debugger Fix Proposed</div>
                <div style="font-size: 10px; color: #94a3b8; margin-bottom: 6px;">\${msg.diagnostics || 'Surgical patch generated'}</div>
                <button class="primary-btn" style="width: 100%; padding: 5px;" onclick="applyFileUpdate('\${msg.filePath.replace(/\\\\/g, '\\\\\\\\')}', decodeURIComponent('\${encodeURIComponent(msg.fixedCode)}'))">Apply Bug Fix</button>
            \`;
        }

        function applyFileUpdate(filePath, code) {
            vscode.postMessage({ type: 'applyFileUpdate', filePath, code });
        }

        function openDiff(filePath, originalCode, newCode) {
            vscode.postMessage({ type: 'openDiffPreview', filePath, originalCode, newCode });
        }

        // Request initial state on load
        vscode.postMessage({ type: 'ready' });
    </script>
</body>
</html>`;
    }
}

function getNonce() {
    let text = '';
    const possible = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    for (let i = 0; i < 32; i++) {
        text += possible.charAt(Math.floor(Math.random() * possible.length));
    }
    return text;
}
