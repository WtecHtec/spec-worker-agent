package api

import (
	"encoding/json"
	"net/http"

	"agent-sandbox/internal/browser/application"
)

func writeJSON(w http.ResponseWriter, status int, v interface{}) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

// HandleBrowserOpen 对应 tool: browser_open_page
func HandleBrowserOpen(svc *application.BrowserApplicationService) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
			return
		}

		var req application.OpenPageRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeJSON(w, http.StatusBadRequest, application.BrowserToolResponse{Success: false, Error: "invalid JSON body"})
			return
		}

		resp := svc.OpenPage(r.Context(), req)
		if !resp.Success {
			writeJSON(w, http.StatusInternalServerError, resp)
			return
		}
		writeJSON(w, http.StatusOK, resp)
	}
}

// HandleBrowserClose 对应 tool: browser_close_page
func HandleBrowserClose(svc *application.BrowserApplicationService) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
			return
		}

		var req application.ClosePageRequest
		_ = json.NewDecoder(r.Body).Decode(&req)

		resp := svc.ClosePage(r.Context(), req)
		writeJSON(w, http.StatusOK, resp)
	}
}

// HandleBrowserSnapshot 对应 tool: browser_get_snapshot
func HandleBrowserSnapshot(svc *application.BrowserApplicationService) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
			return
		}

		var req application.GetSnapshotRequest
		_ = json.NewDecoder(r.Body).Decode(&req)

		resp := svc.GetSnapshot(r.Context(), req)
		if !resp.Success {
			writeJSON(w, http.StatusInternalServerError, resp)
			return
		}
		writeJSON(w, http.StatusOK, resp)
	}
}

// HandleBrowserClick 对应 tool: browser_click
func HandleBrowserClick(svc *application.BrowserApplicationService) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
			return
		}

		var req application.ClickRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeJSON(w, http.StatusBadRequest, application.BrowserToolResponse{Success: false, Error: "invalid JSON body"})
			return
		}

		resp := svc.Click(r.Context(), req)
		if !resp.Success {
			writeJSON(w, http.StatusInternalServerError, resp)
			return
		}
		writeJSON(w, http.StatusOK, resp)
	}
}

// HandleBrowserScreenshot 对应 tool: browser_screenshot
func HandleBrowserScreenshot(svc *application.BrowserApplicationService) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
			return
		}

		var req application.ScreenshotRequest
		_ = json.NewDecoder(r.Body).Decode(&req)

		resp := svc.Screenshot(r.Context(), req)
		if !resp.Success {
			writeJSON(w, http.StatusInternalServerError, resp)
			return
		}
		writeJSON(w, http.StatusOK, resp)
	}
}

// HandleBrowserExecute 通用工具分发入口（支持 ReAct / MCP Tool 动态调用）
func HandleBrowserExecute(svc *application.BrowserApplicationService) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method Not Allowed", http.StatusMethodNotAllowed)
			return
		}

		var req application.ExecuteToolRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeJSON(w, http.StatusBadRequest, application.BrowserToolResponse{Success: false, Error: "invalid JSON body"})
			return
		}

		resp := svc.ExecuteTool(r.Context(), req)
		if !resp.Success {
			writeJSON(w, http.StatusInternalServerError, resp)
			return
		}
		writeJSON(w, http.StatusOK, resp)
	}
}
