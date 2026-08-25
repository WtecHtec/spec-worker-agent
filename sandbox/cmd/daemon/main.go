package main

import (
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"

	"agent-sandbox/internal/api"
	"agent-sandbox/internal/browser/application"
	"agent-sandbox/internal/browser/infrastructure"
	"agent-sandbox/internal/process"
)

func main() {
	port := os.Getenv("SANDBOX_PORT")
	if port == "" {
		port = "5050"
	}

	workspaceDir := os.Getenv("SANDBOX_WORKSPACE")
	if workspaceDir == "" {
		workspaceDir = "/workspace"
	}

	absWorkspace, err := filepath.Abs(workspaceDir)
	if err != nil {
		log.Fatalf("failed to resolve workspace directory: %v", err)
	}

	if err := os.MkdirAll(absWorkspace, 0755); err != nil {
		log.Fatalf("failed to create workspace directory: %v", err)
	}

	pm := process.NewProcessManager()
	browserRepo := infrastructure.NewMemorySessionRepository()
	cdpURL := os.Getenv("CDP_REMOTE_URL") // 可选外部 CDP 地址
	browserSvc := application.NewBrowserApplicationService(browserRepo, cdpURL, absWorkspace)

	mux := http.NewServeMux()
	api.RegisterRoutes(mux, absWorkspace, pm, browserSvc)

	addr := fmt.Sprintf("0.0.0.0:%s", port)
	log.Printf("[Sandbox Daemon] listening on %s, workspace: %s\n", addr, absWorkspace)

	if err := http.ListenAndServe(addr, mux); err != nil {
		log.Fatalf("[Sandbox Daemon] server failed: %v", err)
	}
}
