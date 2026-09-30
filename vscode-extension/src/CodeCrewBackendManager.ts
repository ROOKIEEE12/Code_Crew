import * as vscode from 'vscode';
import * as cp from 'child_process';
import * as path from 'path';
import * as http from 'http';
import * as fs from 'fs';

export interface AgentStatus {
    id: string;
    name: string;
    role: string;
    avatar: string;
    description: string;
    color: string;
}

export interface ModelTelemetry {
    active_models: number;
    total_models: number;
    keys_configured: number;
    models: Array<{
        name: string;
        is_healthy: boolean;
        cooldown_remaining_sec: number;
        consecutive_failures: number;
        success_count: number;
    }>;
}

export class CodeCrewBackendManager {
    private serverProcess: cp.ChildProcess | null = null;
    private outputChannel: vscode.OutputChannel;

    constructor() {
        this.outputChannel = vscode.window.createOutputChannel('CodeCrew Server');
    }

    public getBackendUrl(): string {
        const config = vscode.workspace.getConfiguration('codecrew');
        return config.get<string>('backendUrl', 'http://127.0.0.1:8000');
    }

    public async checkHealth(): Promise<boolean> {
        return new Promise((resolve) => {
            const url = new URL('/api/health', this.getBackendUrl());
            const req = http.get(url.toString(), { timeout: 1500 }, (res) => {
                resolve(res.statusCode === 200);
            });
            req.on('error', () => resolve(false));
            req.on('timeout', () => {
                req.destroy();
                resolve(false);
            });
        });
    }

    public async ensureBackendRunning(workspaceRoot?: string): Promise<boolean> {
        const isHealthy = await this.checkHealth();
        if (isHealthy) {
            return true;
        }

        const config = vscode.workspace.getConfiguration('codecrew');
        const autoStart = config.get<boolean>('autoStartServer', true);
        if (!autoStart) {
            return false;
        }

        return this.startServer(workspaceRoot);
    }

    public async startServer(workspaceRoot?: string): Promise<boolean> {
        const root = workspaceRoot || vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
        if (!root) {
            return false;
        }

        const serverPy = path.join(root, 'server.py');
        if (!fs.existsSync(serverPy)) {
            return false;
        }

        // Locate Python executable (check venv first)
        let pythonPath = 'python';
        const venvWin = path.join(root, 'venv', 'Scripts', 'python.exe');
        const venvUnix = path.join(root, 'venv', 'bin', 'python');
        if (fs.existsSync(venvWin)) {
            pythonPath = venvWin;
        } else if (fs.existsSync(venvUnix)) {
            pythonPath = venvUnix;
        }

        this.outputChannel.appendLine(`🚀 Starting CodeCrew Backend: ${pythonPath} server.py in ${root}`);
        this.outputChannel.show(true);

        try {
            this.serverProcess = cp.spawn(pythonPath, ['-m', 'uvicorn', 'server:app', '--host', '127.0.0.1', '--port', '8000'], {
                cwd: root,
                shell: true,
                env: { ...process.env, PYTHONUNBUFFERED: '1' },
            });

            this.serverProcess.stdout?.on('data', (d) => this.outputChannel.append(d.toString()));
            this.serverProcess.stderr?.on('data', (d) => this.outputChannel.append(d.toString()));

            // Poll for up to 10 seconds for health check
            for (let i = 0; i < 20; i++) {
                await new Promise((r) => setTimeout(r, 500));
                if (await this.checkHealth()) {
                    this.outputChannel.appendLine('✅ CodeCrew Server is ready!');
                    return true;
                }
            }
        } catch (err: any) {
            this.outputChannel.appendLine(`❌ Failed to start server: ${err?.message || err}`);
        }

        return false;
    }

    public async getModelTelemetry(): Promise<ModelTelemetry | null> {
        try {
            const res = await this.fetchJson('/api/models/status');
            return res as ModelTelemetry;
        } catch {
            return null;
        }
    }

    public async getAgents(): Promise<AgentStatus[]> {
        try {
            const res = await this.fetchJson('/api/agents');
            return res.agents || [];
        } catch {
            return [];
        }
    }

    public async auditCode(path: string, code: string, language: string, description: string): Promise<any> {
        return this.postJson('/api/agent/audit', { path, code, language, description });
    }

    public async testCode(path: string, code: string, language: string): Promise<any> {
        return this.postJson('/api/agent/test', { path, code, language });
    }

    public async refactorCode(path: string, code: string, language: string, instruction: string): Promise<any> {
        return this.postJson('/api/agent/refactor', { path, code, language, instruction });
    }

    public async debugCode(path: string, code: string, language: string, error: string): Promise<any> {
        return this.postJson('/api/agent/debug', { path, code, language, error });
    }

    public async explainCode(path: string, code: string, language: string): Promise<any> {
        return this.postJson('/api/agent/explain', { path, code, language });
    }

    public async getProjectDetails(projectId: string): Promise<any> {
        return this.fetchJson(`/api/projects/${projectId}`);
    }

    public stopServer() {
        if (this.serverProcess) {
            this.serverProcess.kill();
            this.serverProcess = null;
        }
    }

    private async fetchJson(apiPath: string): Promise<any> {
        return new Promise((resolve, reject) => {
            const url = new URL(apiPath, this.getBackendUrl());
            http.get(url.toString(), (res) => {
                let data = '';
                res.on('data', (c) => (data += c));
                res.on('end', () => {
                    try {
                        resolve(JSON.parse(data));
                    } catch (e) {
                        reject(e);
                    }
                });
            }).on('error', reject);
        });
    }

    private async postJson(apiPath: string, payload: any): Promise<any> {
        return new Promise((resolve, reject) => {
            const url = new URL(apiPath, this.getBackendUrl());
            const postData = JSON.stringify(payload);
            const req = http.request(
                url.toString(),
                {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Content-Length': Buffer.byteLength(postData),
                    },
                },
                (res) => {
                    let data = '';
                    res.on('data', (c) => (data += c));
                    res.on('end', () => {
                        try {
                            resolve(JSON.parse(data));
                        } catch (e) {
                            reject(new Error(`Server error: ${data}`));
                        }
                    });
                }
            );
            req.on('error', reject);
            req.write(postData);
            req.end();
        });
    }
}
