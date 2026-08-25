package test

import (
	"context"
	_ "embed"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"agent-sandbox/internal/browser/infrastructure"
)

//go:embed fixtures/test_page.html
var testPageHTML string

func TestP0_BrowserProbeAndClick(t *testing.T) {
	// 1. 启动本地 Mock HTTP 服务器托管测试页面
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		_, _ = w.Write([]byte(testPageHTML))
	}))
	defer ts.Close()

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	// 2. 初始化 Go-rod CDP Driver (通过 RodBrowserManager 派发隔离会话)
	mgr := infrastructure.NewRodBrowserManager("")
	defer func() {
		_ = mgr.Close()
	}()

	driver, err := mgr.CreateIsolatedDriver()
	if err != nil {
		t.Fatalf("failed to create isolated chromium driver: %v", err)
	}
	defer func() {
		_ = driver.Close(context.Background())
	}()

	// 3. 访问测试页面
	if err := driver.Navigate(ctx, ts.URL); err != nil {
		t.Fatalf("failed to navigate to test server: %v", err)
	}

	// 4. 执行探针扫描并提取页面快照
	snapshot, err := driver.InspectPage(ctx, true)
	if err != nil {
		t.Fatalf("failed to inspect page: %v", err)
	}

	t.Logf("Snapshot title: %s, elements count: %d", snapshot.Title, len(snapshot.Elements))
	t.Logf("LLM Formatted Output:\n%s", snapshot.FormatForLLM())

	if len(snapshot.Elements) < 3 {
		t.Fatalf("expected at least 3 interactive elements, got %d", len(snapshot.Elements))
	}

	// 5. 验证是否准确识别了 input 与可点击 div，并且提取了父级上下文
	var cartBtnID int
	foundCartBtn := false
	for _, el := range snapshot.Elements {
		if strings.Contains(el.Text, "加入购物车") {
			foundCartBtn = true
			cartBtnID = int(el.ID)
			if !strings.Contains(el.ContextText, "Apple M4 Mac Mini") {
				t.Errorf("expected context text to contain 'Apple M4 Mac Mini', got: %q", el.ContextText)
			}
		}
	}

	if !foundCartBtn {
		t.Fatalf("failed to find '加入购物车' div button in scanned elements")
	}

	// 6. 执行点击加入购物车 (按 Agent ID 点击)
	t.Logf("Triggering click on element ID: %d", cartBtnID)
	if err := driver.ClickByAgentID(ctx, cartBtnID); err != nil {
		t.Fatalf("failed to click cart button by ID %d: %v", cartBtnID, err)
	}

	// 7. 再次点击，让购物车累加到 2
	if err := driver.ClickByAgentID(ctx, cartBtnID); err != nil {
		t.Fatalf("failed to click cart button 2nd time: %v", err)
	}

	// 8. 截图测试
	screenshot, err := driver.CaptureScreenshot(ctx, false)
	if err != nil {
		t.Fatalf("failed to capture screenshot: %v", err)
	}
	if len(screenshot) == 0 {
		t.Fatalf("screenshot byte slice is empty")
	}
	t.Logf("Screenshot captured successfully, size: %d bytes", len(screenshot))
}
