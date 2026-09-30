import * as vscode from 'vscode';
import { CodeCrewBackendManager } from './CodeCrewBackendManager';
import { CodeCrewSidebarProvider } from './CodeCrewSidebarProvider';

export function activate(context: vscode.ExtensionContext) {
    const backendManager = new CodeCrewBackendManager();
    const sidebarProvider = new CodeCrewSidebarProvider(context.extensionUri, backendManager);

    // Register Webview View
    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider(
            CodeCrewSidebarProvider.viewType,
            sidebarProvider
        )
    );

    // Status Bar Item
    const statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.command = 'codecrew.openSidebar';
    statusBarItem.text = '$(sparkle) CodeCrew AI';
    statusBarItem.tooltip = 'CodeCrew Multi-Agent Engineering Studio';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    // Auto-update status bar with model pool health
    const updateStatusBar = async () => {
        const isHealthy = await backendManager.checkHealth();
        if (isHealthy) {
            const telemetry = await backendManager.getModelTelemetry();
            const count = telemetry?.active_models ?? 6;
            statusBarItem.text = `$(sparkle) CodeCrew: Online (${count} Models)`;
            statusBarItem.backgroundColor = undefined;
        } else {
            statusBarItem.text = `$(circle-slash) CodeCrew: Offline`;
            statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');
        }
    };
    updateStatusBar();
    const statusTimer = setInterval(updateStatusBar, 15000);
    context.subscriptions.push({ dispose: () => clearInterval(statusTimer) });

    // Track active editor document changes to keep sidebar synced
    context.subscriptions.push(
        vscode.window.onDidChangeActiveTextEditor(() => {
            sidebarProvider.syncState();
        })
    );

    // Register Commands
    context.subscriptions.push(
        vscode.commands.registerCommand('codecrew.openSidebar', async () => {
            await vscode.commands.executeCommand('workbench.view.extension.codecrew-sidebar');
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('codecrew.auditFile', async () => {
            await sidebarProvider.handleAuditActiveFile();
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('codecrew.generateTests', async () => {
            await sidebarProvider.handleGenerateTests();
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('codecrew.refactorSelection', async () => {
            await sidebarProvider.handleRefactorSelection();
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('codecrew.debugWithCrew', async () => {
            await sidebarProvider.handleDebugActiveFile();
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('codecrew.startServer', async () => {
            const ok = await backendManager.startServer();
            if (ok) {
                vscode.window.showInformationMessage('CodeCrew Backend Engine is running!');
            }
            sidebarProvider.syncState();
            updateStatusBar();
        })
    );

    context.subscriptions.push(
        vscode.commands.registerCommand('codecrew.checkModelHealth', async () => {
            const telemetry = await backendManager.getModelTelemetry();
            if (telemetry) {
                const healthy = telemetry.models.filter(m => m.is_healthy).map(m => m.name).join(', ');
                vscode.window.showInformationMessage(`CodeCrew Models Active: ${telemetry.active_models}/${telemetry.total_models}. Ready: ${healthy}`);
            } else {
                vscode.window.showWarningMessage('CodeCrew Engine is offline. Start the server first.');
            }
        })
    );

    // Ensure backend is running if configured
    backendManager.ensureBackendRunning().then(() => {
        updateStatusBar();
        sidebarProvider.syncState();
    });
}

export function deactivate() {
    // Cleanup if needed
}
