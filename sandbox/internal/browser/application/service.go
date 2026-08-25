package application

import (
	"context"
	"encoding/base64"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"time"

	"agent-sandbox/internal/browser/domain"
	"agent-sandbox/internal/browser/infrastructure"
)

type BrowserApplicationService struct {
	sessionRepo  domain.SessionRepository
	browserMgr   *infrastructure.RodBrowserManager
	workspaceDir string // 沙箱工作空间根目录
}

func NewBrowserApplicationService(repo domain.SessionRepository, driverURL string, workspaceDir string) *BrowserApplicationService {
	if workspaceDir == "" {
		workspaceDir = "/workspace"
	}
	return &BrowserApplicationService{
		sessionRepo:  repo,
		browserMgr:   infrastructure.NewRodBrowserManager(driverURL),
		workspaceDir: workspaceDir,
	}
}

// 获取或惰性初始化 Session (每个 Session 拥有独立隔离的 Incognito Context)
func (s *BrowserApplicationService) getOrCreateSession(ctx context.Context, sessionID string) (*domain.BrowserSession, error) {
	if sessionID == "" {
		sessionID = "default"
	}

	return s.sessionRepo.GetOrCreate(ctx, sessionID, func() (*domain.BrowserSession, error) {
		driver, err := s.browserMgr.CreateIsolatedDriver()
		if err != nil {
			return nil, fmt.Errorf("failed to create isolated browser driver: %w", err)
		}
		return domain.NewBrowserSession(sessionID, driver), nil
	})
}

// 1. OpenPage
func (s *BrowserApplicationService) OpenPage(ctx context.Context, req OpenPageRequest) *BrowserToolResponse {
	log.Printf("[Sandbox][Browser] -> OpenPage req: session=%s url=%s timeout=%d", req.SessionID, req.URL, req.TimeoutSec)
	start := time.Now()
	timeout := 30 * time.Second
	if req.TimeoutSec > 0 {
		timeout = time.Duration(req.TimeoutSec) * time.Second
	}
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	session, err := s.getOrCreateSession(ctx, req.SessionID)
	if err != nil {
		log.Printf("[Sandbox][Browser] getOrCreateSession error: %v", err)
		return &BrowserToolResponse{Success: false, Error: err.Error()}
	}

	snapshot, err := session.OpenPage(ctx, req.URL)
	if err != nil {
		log.Printf("[Sandbox][Browser] session.OpenPage error: %v", err)
		return &BrowserToolResponse{Success: false, Error: err.Error()}
	}

	log.Printf("[Sandbox][Browser] <- OpenPage SUCCESS: title=%q tabs=%d elapsed=%v", snapshot.Title, snapshot.TotalTabs, time.Since(start))
	return &BrowserToolResponse{
		Success:     true,
		URL:         snapshot.URL,
		Title:       snapshot.Title,
		ActiveTabID: snapshot.ActiveTabID,
		TotalTabs:   snapshot.TotalTabs,
		Output:      fmt.Sprintf("成功打开网页: %s\n\n%s", snapshot.Title, snapshot.FormatForLLM()),
	}
}

// 2. ClosePage
func (s *BrowserApplicationService) ClosePage(ctx context.Context, req ClosePageRequest) *BrowserToolResponse {
	sessionID := req.SessionID
	if sessionID == "" {
		sessionID = "default"
	}
	log.Printf("[Sandbox][Browser] -> ClosePage req: session=%s", sessionID)

	if err := s.sessionRepo.Delete(ctx, sessionID); err != nil {
		log.Printf("[Sandbox][Browser] ClosePage error: %v", err)
		return &BrowserToolResponse{Success: false, Error: err.Error()}
	}

	log.Printf("[Sandbox][Browser] <- ClosePage SUCCESS: session=%s", sessionID)
	return &BrowserToolResponse{
		Success: true,
		Output:  "已成功关闭浏览器页面并销毁会话资源。",
	}
}

// 3. GetSnapshot
func (s *BrowserApplicationService) GetSnapshot(ctx context.Context, req GetSnapshotRequest) *BrowserToolResponse {
	log.Printf("[Sandbox][Browser] -> GetSnapshot req: session=%s withScreenshot=%v", req.SessionID, req.IncludeScreenshot)
	ctx, cancel := context.WithTimeout(ctx, 15*time.Second)
	defer cancel()

	session, err := s.getOrCreateSession(ctx, req.SessionID)
	if err != nil {
		log.Printf("[Sandbox][Browser] GetSnapshot getOrCreateSession error: %v", err)
		return &BrowserToolResponse{Success: false, Error: err.Error()}
	}

	snapshot, err := session.GetSnapshot(ctx, req.IncludeScreenshot)
	if err != nil {
		log.Printf("[Sandbox][Browser] GetSnapshot error: %v", err)
		return &BrowserToolResponse{Success: false, Error: err.Error()}
	}

	resp := &BrowserToolResponse{
		Success:     true,
		URL:         snapshot.URL,
		Title:       snapshot.Title,
		ActiveTabID: snapshot.ActiveTabID,
		TotalTabs:   snapshot.TotalTabs,
		Output:      snapshot.FormatForLLM(),
	}

	if len(snapshot.Screenshot) > 0 {
		resp.ScreenshotBase64 = base64.StdEncoding.EncodeToString(snapshot.Screenshot)
	}

	log.Printf("[Sandbox][Browser] <- GetSnapshot SUCCESS: session=%s title=%q elements=%d", req.SessionID, snapshot.Title, len(snapshot.Elements))
	return resp
}

// 4. Click
func (s *BrowserApplicationService) Click(ctx context.Context, req ClickRequest) *BrowserToolResponse {
	log.Printf("[Sandbox][Browser] -> Click req: session=%s element_id=%d", req.SessionID, req.ElementID)
	start := time.Now()
	ctx, cancel := context.WithTimeout(ctx, 20*time.Second)
	defer cancel()

	session, err := s.getOrCreateSession(ctx, req.SessionID)
	if err != nil {
		log.Printf("[Sandbox][Browser] Click getOrCreateSession error: %v", err)
		return &BrowserToolResponse{Success: false, Error: err.Error()}
	}

	snapshot, err := session.Click(ctx, domain.ElementID(req.ElementID))
	if err != nil {
		log.Printf("[Sandbox][Browser] Click element [%d] error: %v", req.ElementID, err)
		return &BrowserToolResponse{Success: false, Error: err.Error()}
	}

	log.Printf("[Sandbox][Browser] <- Click SUCCESS: element_id=%d new_title=%q elapsed=%v", req.ElementID, snapshot.Title, time.Since(start))
	return &BrowserToolResponse{
		Success:     true,
		URL:         snapshot.URL,
		Title:       snapshot.Title,
		ActiveTabID: snapshot.ActiveTabID,
		TotalTabs:   snapshot.TotalTabs,
		Output:      fmt.Sprintf("已成功点击编号 [%d] 元素！\n\n点击后的最新页面状态：\n%s", req.ElementID, snapshot.FormatForLLM()),
	}
}

// 5. Screenshot
func (s *BrowserApplicationService) Screenshot(ctx context.Context, req ScreenshotRequest) *BrowserToolResponse {
	log.Printf("[Sandbox][Browser] -> Screenshot req: session=%s full_page=%v save_path=%s", req.SessionID, req.FullPage, req.SavePath)
	start := time.Now()
	ctx, cancel := context.WithTimeout(ctx, 15*time.Second)
	defer cancel()

	session, err := s.getOrCreateSession(ctx, req.SessionID)
	if err != nil {
		log.Printf("[Sandbox][Browser] Screenshot getOrCreateSession error: %v", err)
		return &BrowserToolResponse{Success: false, Error: err.Error()}
	}

	imgBytes, err := session.Screenshot(ctx, req.FullPage)
	if err != nil {
		log.Printf("[Sandbox][Browser] Screenshot error: %v", err)
		return &BrowserToolResponse{Success: false, Error: err.Error()}
	}

	// 确定保存相对路径
	relPath := req.SavePath
	if relPath == "" {
		relPath = fmt.Sprintf("screenshots/screenshot_%s.png", time.Now().Format("20060102_150405_000"))
	}
	cleanRel := filepath.Clean(relPath)

	// 落地保存到沙箱工作区目录
	targetAbsFile := filepath.Join(s.workspaceDir, cleanRel)
	if err := os.MkdirAll(filepath.Dir(targetAbsFile), 0755); err == nil {
		_ = os.WriteFile(targetAbsFile, imgBytes, 0644)
	}

	baseURL := os.Getenv("SANDBOX_BASE_URL")
	if baseURL == "" {
		baseURL = "http://localhost:5050"
	}
	previewURL := fmt.Sprintf("%s/fs/raw?path=%s", baseURL, cleanRel)

	log.Printf("[Sandbox][Browser] <- Screenshot SUCCESS: saved=%s elapsed=%v", cleanRel, time.Since(start))
	return &BrowserToolResponse{
		Success:          true,
		Output:           fmt.Sprintf("页面截图获取成功！已保存至沙箱文件: %s (在线预览链接: %s)", cleanRel, previewURL),
		FilePath:         cleanRel,
		PreviewURL:       previewURL,
		ScreenshotBase64: base64.StdEncoding.EncodeToString(imgBytes),
	}
}

// ExecuteTool 通用统一工具分发入口（支持 MCP / ReAct 调度器）
func (s *BrowserApplicationService) ExecuteTool(ctx context.Context, req ExecuteToolRequest) *BrowserToolResponse {
	switch req.ToolName {
	case "browser_open_page", "open_page":
		url, _ := req.Arguments["url"].(string)
		return s.OpenPage(ctx, OpenPageRequest{SessionID: req.SessionID, URL: url})

	case "browser_close_page", "close_page":
		return s.ClosePage(ctx, ClosePageRequest{SessionID: req.SessionID})

	case "browser_get_snapshot", "get_snapshot":
		includeImg, _ := req.Arguments["include_screenshot"].(bool)
		return s.GetSnapshot(ctx, GetSnapshotRequest{SessionID: req.SessionID, IncludeScreenshot: includeImg})

	case "browser_click", "click":
		var elID int
		if f, ok := req.Arguments["element_id"].(float64); ok {
			elID = int(f)
		} else if i, ok := req.Arguments["element_id"].(int); ok {
			elID = i
		}
		return s.Click(ctx, ClickRequest{SessionID: req.SessionID, ElementID: elID})

	case "browser_screenshot", "screenshot":
		fullPage, _ := req.Arguments["full_page"].(bool)
		savePath, _ := req.Arguments["save_path"].(string)
		return s.Screenshot(ctx, ScreenshotRequest{SessionID: req.SessionID, FullPage: fullPage, SavePath: savePath})

	default:
		return &BrowserToolResponse{
			Success: false,
			Error:   fmt.Sprintf("unknown tool name: %s", req.ToolName),
		}
	}
}
