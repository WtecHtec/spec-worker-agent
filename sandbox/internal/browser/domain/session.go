package domain

import (
	"context"
	"fmt"
	"sync"
)

// BrowserSession 浏览器会话聚合根（管理会话生命周期、状态机与快照流转）
type BrowserSession struct {
	mu           sync.Mutex
	id           string
	driver       CDPDriverPort
	isOpen       bool
	currentURL   string
	lastSnapshot *PageSnapshot
}

// NewBrowserSession 创建一个新的浏览器会话实例
func NewBrowserSession(id string, driver CDPDriverPort) *BrowserSession {
	return &BrowserSession{
		id:     id,
		driver: driver,
		isOpen: false,
	}
}

func (s *BrowserSession) ID() string {
	return s.id
}

func (s *BrowserSession) IsOpen() bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.isOpen
}

func (s *BrowserSession) CurrentURL() string {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.currentURL
}

func (s *BrowserSession) LastSnapshot() *PageSnapshot {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.lastSnapshot
}

// OpenPage 核心领域行为：打开指定网址并自动提取初始感知快照
func (s *BrowserSession) OpenPage(ctx context.Context, url string) (*PageSnapshot, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if err := s.driver.Navigate(ctx, url); err != nil {
		return nil, fmt.Errorf("failed to open page %s: %w", url, err)
	}

	s.isOpen = true
	s.currentURL = url

	// 自动执行初始探针提取
	snapshot, err := s.driver.InspectPage(ctx, false)
	if err != nil {
		return nil, fmt.Errorf("failed to inspect page after navigation: %w", err)
	}

	s.lastSnapshot = snapshot
	return snapshot, nil
}

// ClosePage 核心领域行为：关闭当前页面并释放底层资源
func (s *BrowserSession) ClosePage(ctx context.Context) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if !s.isOpen {
		return nil
	}

	if err := s.driver.Close(ctx); err != nil {
		return fmt.Errorf("failed to close browser session: %w", err)
	}

	s.isOpen = false
	s.lastSnapshot = nil
	s.currentURL = ""
	return nil
}

// GetSnapshot 核心领域行为：主动感知并刷新当前页面快照
func (s *BrowserSession) GetSnapshot(ctx context.Context, includeScreenshot bool) (*PageSnapshot, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if !s.isOpen {
		return nil, ErrSessionClosed
	}

	snapshot, err := s.driver.InspectPage(ctx, includeScreenshot)
	if err != nil {
		return nil, fmt.Errorf("failed to extract page snapshot: %w", err)
	}

	s.lastSnapshot = snapshot
	return snapshot, nil
}

// Click 核心领域行为：点击指定编号并重新感知新页面状态
func (s *BrowserSession) Click(ctx context.Context, elementID ElementID) (*PageSnapshot, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if !s.isOpen {
		return nil, ErrSessionClosed
	}

	if err := s.driver.ClickByAgentID(ctx, int(elementID)); err != nil {
		return nil, fmt.Errorf("failed to click element [%d]: %w", elementID, err)
	}

	// 触发智能等待（网络空闲/DOM稳定）
	_ = s.driver.WaitStable(ctx)

	// 刷新快照
	snapshot, err := s.driver.InspectPage(ctx, false)
	if err != nil {
		return nil, fmt.Errorf("failed to refresh snapshot after click: %w", err)
	}

	s.lastSnapshot = snapshot
	return snapshot, nil
}

// Screenshot 核心领域行为：对当前页面进行截图
func (s *BrowserSession) Screenshot(ctx context.Context, fullPage bool) ([]byte, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if !s.isOpen {
		return nil, ErrSessionClosed
	}

	return s.driver.CaptureScreenshot(ctx, fullPage)
}
