package api

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"os/exec"
	"strings"
	"syscall"
	"time"

	"agent-sandbox/internal/process"
)

type ExecRequest struct {
	ExecID  string `json:"exec_id,omitempty"`
	Command string `json:"command"`
	Cwd     string `json:"cwd,omitempty"`
	Timeout int    `json:"timeout,omitempty"` // 秒数，默认 60s
}

type ExecResponse struct {
	ExecID      string `json:"exec_id"`
	ExitCode    int    `json:"exit_code"`
	Stdout      string `json:"stdout"`
	Stderr      string `json:"stderr"`
	Combined    string `json:"combined"`
	DurationMs  int64  `json:"duration_ms"`
	IsTruncated bool   `json:"is_truncated"`
	IsTimeout   bool   `json:"is_timeout"`
	IsError     bool   `json:"is_error"`
	Message     string `json:"message,omitempty"`
}

func HandleExec(workspaceDir string, pm *process.ProcessManager) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req ExecRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}

		if req.Command == "" {
			http.Error(w, "command is required", http.StatusBadRequest)
			return
		}

		if req.ExecID == "" {
			req.ExecID = fmt.Sprintf("exec_%d", time.Now().UnixNano())
		}

		timeout := 60 * time.Second
		if req.Timeout > 0 {
			timeout = time.Duration(req.Timeout) * time.Second
		}

		workDir := workspaceDir
		if req.Cwd != "" {
			safeCwd, err := resolveSafePath(workspaceDir, req.Cwd)
			if err != nil {
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusForbidden)
				json.NewEncoder(w).Encode(ExecResponse{IsError: true, Message: err.Error()})
				return
			}
			workDir = safeCwd
		}

		ctx, cancel := context.WithTimeout(context.Background(), timeout)
		defer cancel()

		cmd := exec.CommandContext(ctx, "bash", "-c", req.Command)
		cmd.Dir = workDir

		// 设置独立进程组（Setpgid: true），方便通过 -PID 强杀整棵子进程树
		cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}

		var stdoutBuf, stderrBuf bytes.Buffer
		cmd.Stdout = &stdoutBuf
		cmd.Stderr = &stderrBuf

		startTime := time.Now()
		if err := cmd.Start(); err != nil {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusInternalServerError)
			json.NewEncoder(w).Encode(ExecResponse{
				ExecID:  req.ExecID,
				IsError: true,
				Message: fmt.Sprintf("failed to start process: %s", err.Error()),
			})
			return
		}

		pm.Register(req.ExecID, cmd)
		defer pm.Unregister(req.ExecID)

		err := cmd.Wait()
		durationMs := time.Since(startTime).Milliseconds()

		exitCode := 0
		isTimeout := false
		if err != nil {
			if ctx.Err() == context.DeadlineExceeded {
				isTimeout = true
				exitCode = -1
				_ = pm.Kill(req.ExecID)
			} else if exitErr, ok := err.(*exec.ExitError); ok {
				exitCode = exitErr.ExitCode()
			} else {
				exitCode = -1
			}
		}

		stdout := stdoutBuf.String()
		stderr := stderrBuf.String()

		combined := ""
		if stdout != "" {
			combined += "[stdout]\n" + stdout + "\n"
		}
		if stderr != "" {
			combined += "[stderr]\n" + stderr + "\n"
		}
		if strings.TrimSpace(combined) == "" {
			combined = fmt.Sprintf("(命令执行成功，退出码: %d，无标准输出)", exitCode)
		}

		isTruncated := false
		if len(combined) > 4000 {
			head := combined[:1500]
			tail := combined[len(combined)-2000:]
			combined = fmt.Sprintf("%s\n\n... [沙箱输出过长已自动截断，省略中间部分] ...\n\n%s", head, tail)
			isTruncated = true
		}

		resp := ExecResponse{
			ExecID:      req.ExecID,
			ExitCode:    exitCode,
			Stdout:      stdout,
			Stderr:      stderr,
			Combined:    strings.TrimSpace(combined),
			DurationMs:  durationMs,
			IsTruncated: isTruncated,
			IsTimeout:   isTimeout,
			IsError:     exitCode != 0,
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp)
	}
}

func HandleKill(pm *process.ProcessManager) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req struct {
			ExecID string `json:"exec_id"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil || req.ExecID == "" {
			http.Error(w, "exec_id is required", http.StatusBadRequest)
			return
		}

		if err := pm.Kill(req.ExecID); err != nil {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusNotFound)
			json.NewEncoder(w).Encode(map[string]any{"success": false, "message": err.Error()})
			return
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]any{"success": true, "message": "process terminated"})
	}
}
