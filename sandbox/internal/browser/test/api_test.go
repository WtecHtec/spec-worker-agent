package test

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"agent-sandbox/internal/api"
	"agent-sandbox/internal/browser/application"
	"agent-sandbox/internal/browser/infrastructure"
	"agent-sandbox/internal/process"
)

func TestP1_BrowserToolsHTTPAPI(t *testing.T) {
	// 1. 启动 Web 页面 Mock 服务
	webServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		_, _ = w.Write([]byte(testPageHTML))
	}))
	defer webServer.Close()

	// 2. 启动 Sandbox API 服务
	tmpDir := t.TempDir()
	pm := process.NewProcessManager()
	repo := infrastructure.NewMemorySessionRepository()
	svc := application.NewBrowserApplicationService(repo, "", tmpDir)

	mux := http.NewServeMux()
	api.RegisterRoutes(mux, tmpDir, pm, svc)
	sandboxServer := httptest.NewServer(mux)
	defer sandboxServer.Close()

	client := sandboxServer.Client()

	// 辅助发送 JSON POST 请求
	postJSON := func(endpoint string, payload interface{}) application.BrowserToolResponse {
		body, _ := json.Marshal(payload)
		resp, err := client.Post(sandboxServer.URL+endpoint, "application/json", bytes.NewReader(body))
		if err != nil {
			t.Fatalf("failed to post to %s: %v", endpoint, err)
		}
		defer resp.Body.Close()

		var result application.BrowserToolResponse
		if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
			t.Fatalf("failed to decode response from %s: %v", endpoint, err)
		}
		return result
	}

	// Tool 1: browser_open_page
	t.Run("1_OpenPage", func(t *testing.T) {
		res := postJSON("/tools/browser/open", map[string]interface{}{
			"session_id": "test-session-1",
			"url":        webServer.URL,
		})

		if !res.Success {
			t.Fatalf("expected success=true, got error: %s", res.Error)
		}
		if !strings.Contains(res.Output, "P0 浏览器自动化测试页面") {
			t.Errorf("output missing page title, got:\n%s", res.Output)
		}
		if !strings.Contains(res.Output, "加入购物车") {
			t.Errorf("output missing cart button, got:\n%s", res.Output)
		}
		t.Logf("[Tool 1 OpenPage OK] Output preview:\n%s", res.Output)
	})

	// Tool 2: browser_click (按编号点击加入购物车)
	t.Run("2_ClickCartButton", func(t *testing.T) {
		res := postJSON("/tools/browser/click", map[string]interface{}{
			"session_id": "test-session-1",
			"element_id": 3,
		})

		if !res.Success {
			t.Fatalf("click failed: %s", res.Error)
		}
		if !strings.Contains(res.Output, "已成功点击编号 [3] 元素") {
			t.Errorf("unexpected output after click: %s", res.Output)
		}
		t.Logf("[Tool 2 Click OK] Output preview:\n%s", res.Output)
	})

	// Tool 3: browser_get_snapshot
	t.Run("3_GetSnapshot", func(t *testing.T) {
		res := postJSON("/tools/browser/snapshot", map[string]interface{}{
			"session_id": "test-session-1",
		})

		if !res.Success {
			t.Fatalf("snapshot failed: %s", res.Error)
		}
		if !strings.Contains(res.Output, "Apple M4 Mac Mini") {
			t.Errorf("snapshot missing container context: %s", res.Output)
		}
		t.Logf("[Tool 3 Snapshot OK]")
	})

	// Tool 4: browser_screenshot
	t.Run("4_Screenshot", func(t *testing.T) {
		res := postJSON("/tools/browser/screenshot", map[string]interface{}{
			"session_id": "test-session-1",
			"full_page":  false,
			"save_path":  "screenshots/custom_shot.png",
		})

		if !res.Success {
			t.Fatalf("screenshot failed: %s", res.Error)
		}
		if len(res.ScreenshotBase64) == 0 {
			t.Errorf("screenshot base64 string is empty")
		}
		if res.FilePath != "screenshots/custom_shot.png" {
			t.Errorf("expected file_path to be 'screenshots/custom_shot.png', got: %s", res.FilePath)
		}
		if !strings.Contains(res.PreviewURL, "/fs/raw?path=") {
			t.Errorf("expected preview_url to contain '/fs/raw?path=', got: %s", res.PreviewURL)
		}
		t.Logf("[Tool 4 Screenshot OK] File: %s, Preview: %s, Base64 len: %d", res.FilePath, res.PreviewURL, len(res.ScreenshotBase64))
	})

	// Tool 5: 通用 ExecuteTool 分发接口 (测试 ReAct/MCP 单入口调用)
	t.Run("5_GenericExecuteDispatcher", func(t *testing.T) {
		res := postJSON("/tools/browser/execute", map[string]interface{}{
			"session_id": "test-session-1",
			"tool_name":  "browser_click",
			"arguments": map[string]interface{}{
				"element_id": 3,
			},
		})

		if !res.Success {
			t.Fatalf("generic execute failed: %s", res.Error)
		}
		t.Logf("[Tool 5 Execute Dispatcher OK]")
	})

	// Tool 6: browser_close_page
	t.Run("6_ClosePage", func(t *testing.T) {
		res := postJSON("/tools/browser/close", map[string]interface{}{
			"session_id": "test-session-1",
		})

		if !res.Success {
			t.Fatalf("close failed: %s", res.Error)
		}
		t.Logf("[Tool 6 ClosePage OK]")
	})
}
