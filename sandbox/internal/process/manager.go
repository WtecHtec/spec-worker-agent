package process

import (
	"errors"
	"os/exec"
	"sync"
	"syscall"
)

type ProcessManager struct {
	mu        sync.RWMutex
	processes map[string]*exec.Cmd
}

func NewProcessManager() *ProcessManager {
	return &ProcessManager{
		processes: make(map[string]*exec.Cmd),
	}
}

func (pm *ProcessManager) Register(execID string, cmd *exec.Cmd) {
	pm.mu.Lock()
	defer pm.mu.Unlock()
	pm.processes[execID] = cmd
}

func (pm *ProcessManager) Unregister(execID string) {
	pm.mu.Lock()
	defer pm.mu.Unlock()
	delete(pm.processes, execID)
}

func (pm *ProcessManager) Kill(execID string) error {
	pm.mu.Lock()
	cmd, exists := pm.processes[execID]
	pm.mu.Unlock()

	if !exists || cmd == nil || cmd.Process == nil {
		return errors.New("process not found or already terminated")
	}

	// 发送 SIGKILL 给负的 PID（整棵进程组/进程树），彻底终止所有派生的子孙进程
	pgid, err := syscall.Getpgid(cmd.Process.Pid)
	if err == nil {
		return syscall.Kill(-pgid, syscall.SIGKILL)
	}
	return cmd.Process.Kill()
}
