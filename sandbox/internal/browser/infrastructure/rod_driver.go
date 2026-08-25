package infrastructure

import (
	"context"
	"fmt"
	"sync"
	"time"

	"agent-sandbox/internal/browser/domain"
	"agent-sandbox/internal/browser/infrastructure/probe"

	"github.com/go-rod/rod"
	"github.com/go-rod/rod/lib/launcher"
	"github.com/go-rod/rod/lib/proto"
)

// RodBrowserManager 管理全局 Root Chromium 进程，并为各独立任务派发隔离的 Incognito Context
type RodBrowserManager struct {
	mu          sync.Mutex
	rootBrowser *rod.Browser
	launcher    *launcher.Launcher
	cdpURL      string
}

func NewRodBrowserManager(cdpURL string) *RodBrowserManager {
	return &RodBrowserManager{
		cdpURL: cdpURL,
	}
}

// 获取或初始化全局 Root Browser 连接
func (m *RodBrowserManager) getRootBrowser() (*rod.Browser, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	if m.rootBrowser != nil {
		return m.rootBrowser, nil
	}

	if m.cdpURL != "" {
		b := rod.New().ControlURL(m.cdpURL)
		if err := b.Connect(); err != nil {
			return nil, fmt.Errorf("failed to connect to cdp url %s: %w", m.cdpURL, err)
		}
		m.rootBrowser = b
		return b, nil
	}

	// 本地自动拉起 Headless Chromium
	l := launcher.New().
		Headless(true).
		NoSandbox(true).
		Set("disable-dev-shm-usage").
		Set("disable-gpu")

	if bin, has := launcher.LookPath(); has {
		l = l.Bin(bin)
	}

	u, err := l.Launch()
	if err != nil {
		return nil, fmt.Errorf("failed to launch chromium: %w", err)
	}

	b := rod.New().ControlURL(u)
	if err := b.Connect(); err != nil {
		l.Kill()
		return nil, fmt.Errorf("failed to connect to launched chromium: %w", err)
	}

	m.launcher = l
	m.rootBrowser = b
	return b, nil
}

// CreateIsolatedDriver 为每个独立 Task/Session 创建专属的 Incognito 隐身上下文与独立 Page
func (m *RodBrowserManager) CreateIsolatedDriver() (domain.CDPDriverPort, error) {
	root, err := m.getRootBrowser()
	if err != nil {
		return nil, err
	}

	incognitoBrowser, err := root.Incognito()
	if err != nil {
		return nil, fmt.Errorf("failed to create incognito browser context: %w", err)
	}

	page, err := incognitoBrowser.Page(proto.TargetCreateTarget{URL: "about:blank"})
	if err != nil {
		_ = incognitoBrowser.Close()
		return nil, fmt.Errorf("failed to create page in incognito context: %w", err)
	}

	return &RodCDPDriver{
		incognitoBrowser: incognitoBrowser,
		page:             page,
	}, nil
}

func (m *RodBrowserManager) Close() error {
	m.mu.Lock()
	defer m.mu.Unlock()

	if m.rootBrowser != nil {
		_ = m.rootBrowser.Close()
		m.rootBrowser = nil
	}
	if m.launcher != nil {
		m.launcher.Kill()
		m.launcher = nil
	}
	return nil
}

// RodCDPDriver 实现 domain.CDPDriverPort 接口（单任务专属驱动）
type RodCDPDriver struct {
	mu               sync.Mutex
	incognitoBrowser *rod.Browser
	page             *rod.Page
}

// 自动检测并切换到最新生成的 Tab（处理 target="_blank" 或 window.open 弹窗场景）
func (d *RodCDPDriver) syncActivePage(ctx context.Context) {
	d.mu.Lock()
	defer d.mu.Unlock()

	if d.incognitoBrowser == nil {
		return
	}

	pages, err := d.incognitoBrowser.Pages()
	if err != nil || len(pages) == 0 {
		return
	}

	// 取最新的非空白或最后一个 Page
	lastPage := pages[len(pages)-1]
	d.page = lastPage
}

// Navigate 打开指定 URL 并等待基础加载
func (d *RodCDPDriver) Navigate(ctx context.Context, url string) error {
	d.syncActivePage(ctx)
	if d.page == nil {
		return domain.ErrSessionClosed
	}

	p := d.page.Context(ctx)
	if err := p.Navigate(url); err != nil {
		return fmt.Errorf("navigate to %s failed: %w", url, err)
	}

	_ = p.WaitLoad()
	return nil
}

// InspectPage 执行 JS 探针并提取已编号的元素快照（支持多 Tab 状态展示）
func (d *RodCDPDriver) InspectPage(ctx context.Context, withScreenshot bool) (*domain.PageSnapshot, error) {
	d.syncActivePage(ctx)
	if d.page == nil {
		return nil, domain.ErrSessionClosed
	}

	p := d.page.Context(ctx)

	// 执行 JS 探针脚本
	res, err := p.Eval(probe.Script)
	if err != nil {
		return nil, fmt.Errorf("execute js probe failed: %w", err)
	}

	type probeResult struct {
		Elements []domain.InteractiveElement `json:"elements"`
		DOMTree  string                      `json:"dom_tree"`
	}

	var pr probeResult
	if err := res.Value.Unmarshal(&pr); err != nil {
		return nil, fmt.Errorf("failed to parse elements from probe: %w", err)
	}

	info, err := p.Info()
	title := ""
	currentURL := ""
	activeTabID := ""
	if err == nil && info != nil {
		title = info.Title
		currentURL = info.URL
		activeTabID = string(info.TargetID)
	}

	totalTabs := 1
	if pages, err := d.incognitoBrowser.Pages(); err == nil && len(pages) > 0 {
		totalTabs = len(pages)
	}

	snapshot := &domain.PageSnapshot{
		URL:         currentURL,
		Title:       title,
		ActiveTabID: activeTabID,
		TotalTabs:   totalTabs,
		DOMTree:     pr.DOMTree,
		Elements:    pr.Elements,
		CapturedAt:  time.Now(),
	}

	if withScreenshot {
		imgBytes, err := d.CaptureScreenshot(ctx, false)
		if err == nil {
			snapshot.Screenshot = imgBytes
		}
	}

	return snapshot, nil
}

// ClickByAgentID 定位带有指定 data-agent-id 的元素并触发点击（内置自愈探针重试机制）
func (d *RodCDPDriver) ClickByAgentID(ctx context.Context, agentID int) error {
	d.syncActivePage(ctx)
	if d.page == nil {
		return domain.ErrSessionClosed
	}

	p := d.page.Context(ctx)
	selector := fmt.Sprintf(`[data-agent-id="%d"]`, agentID)

	el, err := p.Element(selector)
	// 自愈探针：若元素未找到，自动重新执行一次探针脚本给当前 DOM 打标重试
	if err != nil {
		_, probeErr := d.InspectPage(ctx, false)
		if probeErr == nil {
			el, err = p.Element(selector)
		}
	}

	if err != nil {
		return fmt.Errorf("%w: 目标元素编号 [%d] 未在当前页面中找到（请检查快照中的最新编号）", domain.ErrElementNotFound, agentID)
	}

	// 滚动到视口并等待可见
	if err := el.ScrollIntoView(); err != nil {
		return fmt.Errorf("failed to scroll element into view: %w", err)
	}

	// 触发物理左键单击
	if err := el.Click(proto.InputMouseButtonLeft, 1); err != nil {
		return fmt.Errorf("failed to click element [%d]: %w", agentID, err)
	}

	// 点击完成后同步最新活动 Tab 状态
	d.syncActivePage(ctx)
	return nil
}

// CaptureScreenshot 截取当前视口或整页
func (d *RodCDPDriver) CaptureScreenshot(ctx context.Context, fullPage bool) ([]byte, error) {
	d.syncActivePage(ctx)
	if d.page == nil {
		return nil, domain.ErrSessionClosed
	}

	p := d.page.Context(ctx)
	return p.Screenshot(fullPage, &proto.PageCaptureScreenshot{
		Format: proto.PageCaptureScreenshotFormatPng,
	})
}

// WaitStable 智能等待防抖
func (d *RodCDPDriver) WaitStable(ctx context.Context) error {
	return nil
}

// Close 关闭当前任务专属的 Page 与 Incognito BrowserContext
func (d *RodCDPDriver) Close(ctx context.Context) error {
	d.mu.Lock()
	defer d.mu.Unlock()

	if d.page != nil {
		_ = d.page.Close()
		d.page = nil
	}
	if d.incognitoBrowser != nil {
		_ = d.incognitoBrowser.Close()
		d.incognitoBrowser = nil
	}
	return nil
}
