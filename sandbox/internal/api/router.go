package api

import (
	"encoding/json"
	"net/http"

	"agent-sandbox/internal/process"
)

func RegisterRoutes(mux *http.ServeMux, workspaceDir string, pm *process.ProcessManager) {
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]string{"status": "ok", "workspace": workspaceDir})
	})

	mux.HandleFunc("/exec", HandleExec(workspaceDir, pm))
	mux.HandleFunc("/exec/kill", HandleKill(pm))
	mux.HandleFunc("/fs/read", HandleFileRead(workspaceDir))
	mux.HandleFunc("/fs/write", HandleFileWrite(workspaceDir))
	mux.HandleFunc("/fs/list", HandleFileList(workspaceDir))
	mux.HandleFunc("/fs/raw", HandleFileRaw(workspaceDir))
}
