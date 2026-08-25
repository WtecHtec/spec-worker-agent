package domain

import "context"

// SessionRepository 领域仓储接口：定义会话生命周期的存取抽象
type SessionRepository interface {
	// Get 获取指定 ID 的会话实例
	Get(ctx context.Context, id string) (*BrowserSession, error)

	// Save 保存或更新会话
	Save(ctx context.Context, session *BrowserSession) error

	// Delete 移除并销毁会话
	Delete(ctx context.Context, id string) error

	// GetOrCreate 获取已有会话，不存在则自动通过 factory 创建并保存
	GetOrCreate(ctx context.Context, id string, factory func() (*BrowserSession, error)) (*BrowserSession, error)
}
