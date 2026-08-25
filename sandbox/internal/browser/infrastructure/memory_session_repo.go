package infrastructure

import (
	"context"
	"fmt"
	"sync"

	"agent-sandbox/internal/browser/domain"
)

// MemorySessionRepository 基于内存并发安全的 Session 仓储实现
type MemorySessionRepository struct {
	mu       sync.RWMutex
	sessions map[string]*domain.BrowserSession
}

func NewMemorySessionRepository() *MemorySessionRepository {
	return &MemorySessionRepository{
		sessions: make(map[string]*domain.BrowserSession),
	}
}

func (r *MemorySessionRepository) Get(ctx context.Context, id string) (*domain.BrowserSession, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()

	s, ok := r.sessions[id]
	if !ok {
		return nil, fmt.Errorf("browser session %q not found", id)
	}
	return s, nil
}

func (r *MemorySessionRepository) Save(ctx context.Context, session *domain.BrowserSession) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	r.sessions[session.ID()] = session
	return nil
}

func (r *MemorySessionRepository) Delete(ctx context.Context, id string) error {
	r.mu.Lock()
	defer r.mu.Unlock()

	if s, ok := r.sessions[id]; ok {
		_ = s.ClosePage(ctx)
		delete(r.sessions, id)
	}
	return nil
}

func (r *MemorySessionRepository) GetOrCreate(ctx context.Context, id string, factory func() (*domain.BrowserSession, error)) (*domain.BrowserSession, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	if s, ok := r.sessions[id]; ok {
		return s, nil
	}

	newSession, err := factory()
	if err != nil {
		return nil, err
	}

	r.sessions[id] = newSession
	return newSession, nil
}
