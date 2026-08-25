package api

import (
	"encoding/json"
	"net/http"

	"agent-sandbox/internal/browser/application"
	"agent-sandbox/internal/process"
)

func RegisterRoutes(mux *http.ServeMux, workspaceDir string, pm *process.ProcessManager, browserSvc *application.BrowserApplicationService) {
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]string{"status": "ok", "workspace": workspaceDir})
	})

	// Process & File APIs
	mux.HandleFunc("/exec", HandleExec(workspaceDir, pm))
	mux.HandleFunc("/exec/kill", HandleKill(pm))
	mux.HandleFunc("/fs/read", HandleFileRead(workspaceDir))
	mux.HandleFunc("/fs/write", HandleFileWrite(workspaceDir))
	mux.HandleFunc("/fs/list", HandleFileList(workspaceDir))
	mux.HandleFunc("/fs/raw", HandleFileRaw(workspaceDir))

	// Browser CDP Tools
	if browserSvc != nil {
		mux.HandleFunc("/tools/browser/open", HandleBrowserOpen(browserSvc))
		mux.HandleFunc("/tools/browser/close", HandleBrowserClose(browserSvc))
		mux.HandleFunc("/tools/browser/snapshot", HandleBrowserSnapshot(browserSvc))
		mux.HandleFunc("/tools/browser/click", HandleBrowserClick(browserSvc))
		mux.HandleFunc("/tools/browser/screenshot", HandleBrowserScreenshot(browserSvc))
		mux.HandleFunc("/tools/browser/execute", HandleBrowserExecute(browserSvc))
	}
}
