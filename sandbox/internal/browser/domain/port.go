package domain

import (
	"context"
	"errors"
)

var (
	ErrSessionClosed   = errors.New("browser session is closed")
	ErrElementNotFound = errors.New("element not found with specified agent id")
	ErrActionTimeout   = errors.New("browser action timed out")
)

// CDPDriverPort 定义与底层 CDP 浏览器交互的抽象端口（领域层接口，与具体技术解耦）
type CDPDriverPort interface {
	// Navigate 打开指定网页并等待基础 DOM 就绪
	Navigate(ctx context.Context, url string) error

	// Close 关闭当前页面/浏览器
	Close(ctx context.Context) error

	// InspectPage 注入启发式探针，提取当前页面交互结构并可选截图
	InspectPage(ctx context.Context, withScreenshot bool) (*PageSnapshot, error)

	// ClickByAgentID 根据探针分配的数字编号物理点击元素
	ClickByAgentID(ctx context.Context, agentID int) error

	// CaptureScreenshot 截取当前视口或完整页面
	CaptureScreenshot(ctx context.Context, fullPage bool) ([]byte, error)

	// WaitStable 等待页面渲染防抖与网络空闲
	WaitStable(ctx context.Context) error
}
