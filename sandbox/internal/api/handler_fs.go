package api

import (
	"bufio"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"
)

type FileReadRequest struct {
	SessionID string `json:"session_id,omitempty"`
	FilePath  string `json:"file_path"`
	StartLine int    `json:"start_line,omitempty"`
	EndLine   int    `json:"end_line,omitempty"`
}

type FileReadResponse struct {
	Content    string `json:"content"`
	TotalLines int    `json:"total_lines"`
	IsError    bool   `json:"is_error"`
	Message    string `json:"message,omitempty"`
}

type FileWriteRequest struct {
	SessionID string `json:"session_id,omitempty"`
	FilePath  string `json:"file_path"`
	Content   string `json:"content"`
}

type FileWriteResponse struct {
	Success bool   `json:"success"`
	Bytes   int    `json:"bytes"`
	Message string `json:"message,omitempty"`
}

type FileListRequest struct {
	SessionID string `json:"session_id,omitempty"`
	DirPath   string `json:"dir_path,omitempty"`
}

type FileItem struct {
	Name  string `json:"name"`
	IsDir bool   `json:"is_dir"`
	Size  int64  `json:"size"`
}

type FileListResponse struct {
	Files   []FileItem `json:"files"`
	Message string     `json:"message,omitempty"`
}

// 路径防越界校验（支持基于 session_id 进行会话目录物理隔离）
func resolveSafePath(baseWorkspace, relPath string, sessionID ...string) (string, error) {
	absBase, err := filepath.Abs(baseWorkspace)
	if err != nil {
		return "", err
	}

	targetBase := absBase
	if len(sessionID) > 0 && strings.TrimSpace(sessionID[0]) != "" {
		targetBase = filepath.Join(absBase, "sessions", strings.TrimSpace(sessionID[0]))
	}

	cleanRel := filepath.Clean(relPath)
	target := filepath.Join(targetBase, cleanRel)
	absTarget, err := filepath.Abs(target)
	if err != nil {
		return "", err
	}

	if !strings.HasPrefix(absTarget, targetBase) {
		return "", fmt.Errorf("permission denied: path traversal out of workspace [%s]", relPath)
	}
	return absTarget, nil
}

func HandleFileRead(workspaceDir string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req FileReadRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}

		targetPath, err := resolveSafePath(workspaceDir, req.FilePath, req.SessionID)
		if err != nil {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusForbidden)
			json.NewEncoder(w).Encode(FileReadResponse{IsError: true, Message: err.Error()})
			return
		}

		file, err := os.Open(targetPath)
		if err != nil {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusNotFound)
			json.NewEncoder(w).Encode(FileReadResponse{IsError: true, Message: fmt.Sprintf("file not found: %s", req.FilePath)})
			return
		}
		defer file.Close()

		var lines []string
		scanner := bufio.NewScanner(file)
		for scanner.Scan() {
			lines = append(lines, scanner.Text())
		}

		totalLines := len(lines)
		s := 1
		if req.StartLine > 0 {
			s = req.StartLine
		}
		e := totalLines
		if req.EndLine > 0 && req.EndLine <= totalLines {
			e = req.EndLine
		}

		if s > totalLines && totalLines > 0 {
			w.Header().Set("Content-Type", "application/json")
			json.NewEncoder(w).Encode(FileReadResponse{
				IsError: true,
				Message: fmt.Sprintf("start_line %d exceeds total lines %d", s, totalLines),
			})
			return
		}

		var selected []string
		if totalLines > 0 {
			for i := s - 1; i < e && i < totalLines; i++ {
				selected = append(selected, fmt.Sprintf("%4d | %s", i+1, lines[i]))
			}
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(FileReadResponse{
			Content:    strings.Join(selected, "\n"),
			TotalLines: totalLines,
			IsError:    false,
		})
	}
}

func HandleFileWrite(workspaceDir string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req FileWriteRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}

		targetPath, err := resolveSafePath(workspaceDir, req.FilePath, req.SessionID)
		if err != nil {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusForbidden)
			json.NewEncoder(w).Encode(FileWriteResponse{Success: false, Message: err.Error()})
			return
		}

		if err := os.MkdirAll(filepath.Dir(targetPath), 0755); err != nil {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusInternalServerError)
			json.NewEncoder(w).Encode(FileWriteResponse{Success: false, Message: err.Error()})
			return
		}

		if err := os.WriteFile(targetPath, []byte(req.Content), 0644); err != nil {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusInternalServerError)
			json.NewEncoder(w).Encode(FileWriteResponse{Success: false, Message: err.Error()})
			return
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(FileWriteResponse{
			Success: true,
			Bytes:   len([]byte(req.Content)),
			Message: fmt.Sprintf("successfully wrote %s (%d bytes)", req.FilePath, len(req.Content)),
		})
	}
}

func HandleFileList(workspaceDir string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		var req FileListRequest
		_ = json.NewDecoder(r.Body).Decode(&req)

		targetDir, err := resolveSafePath(workspaceDir, req.DirPath, req.SessionID)
		if err != nil {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusForbidden)
			json.NewEncoder(w).Encode(FileListResponse{Message: err.Error()})
			return
		}

		entries, err := os.ReadDir(targetDir)
		if err != nil {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusInternalServerError)
			json.NewEncoder(w).Encode(FileListResponse{Message: err.Error()})
			return
		}

		var files []FileItem
		for _, entry := range entries {
			info, _ := entry.Info()
			size := int64(0)
			if info != nil {
				size = info.Size()
			}
			files = append(files, FileItem{
				Name:  entry.Name(),
				IsDir: entry.IsDir(),
				Size:  size,
			})
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(FileListResponse{Files: files})
	}
}

// HandleFileRaw 提供原生文件二进制/文本流输出，支持浏览器直接 URL 访问预览与下载
func HandleFileRaw(workspaceDir string) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		// 跨域支持 (必须在最前面处理以支持 OPTIONS 预检)
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Header().Set("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "*")
		w.Header().Set("Cross-Origin-Resource-Policy", "cross-origin")

		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusOK)
			return
		}

		if r.Method != http.MethodGet && r.Method != http.MethodHead {
			http.Error(w, "Method not allowed", http.StatusMethodNotAllowed)
			return
		}

		filePath := r.URL.Query().Get("path")
		if filePath == "" {
			filePath = r.URL.Query().Get("file_path")
		}
		if filePath == "" {
			http.Error(w, "query parameter 'path' is required", http.StatusBadRequest)
			return
		}

		sessionID := r.URL.Query().Get("session_id")
		targetPath, err := resolveSafePath(workspaceDir, filePath, sessionID)
		if err != nil {
			http.Error(w, err.Error(), http.StatusForbidden)
			return
		}

		info, err := os.Stat(targetPath)
		if err != nil {
			// 若按 session_id 未找到文件，尝试回退到工作区根目录检索（兼容历史会话数据）
			if os.IsNotExist(err) && sessionID != "" {
				fallbackPath, fallbackErr := resolveSafePath(workspaceDir, filePath)
				if fallbackErr == nil {
					if fbInfo, fbErr := os.Stat(fallbackPath); fbErr == nil && !fbInfo.IsDir() {
						targetPath = fallbackPath
						info = fbInfo
						err = nil
					}
				}
			}

			if err != nil {
				if os.IsNotExist(err) {
					http.Error(w, fmt.Sprintf("file not found: %s", filePath), http.StatusNotFound)
				} else {
					http.Error(w, err.Error(), http.StatusInternalServerError)
				}
				return
			}
		}

		if info.IsDir() {
			http.Error(w, "cannot serve directory directly", http.StatusBadRequest)
			return
		}

		// 支持强制下载模式
		if r.URL.Query().Get("download") == "true" || r.URL.Query().Get("download") == "1" {
			w.Header().Set("Content-Disposition", fmt.Sprintf("attachment; filename=%q", filepath.Base(targetPath)))
		}

		// 对代码及文本文件自动适配标准 Content-Type，防止浏览器拒绝预览或强制下载
		ext := strings.ToLower(filepath.Ext(targetPath))
		switch ext {
		case ".jsx", ".tsx", ".ts", ".js", ".mjs", ".cjs":
			w.Header().Set("Content-Type", "text/javascript; charset=utf-8")
		case ".json":
			w.Header().Set("Content-Type", "application/json; charset=utf-8")
		case ".py", ".sh", ".bash", ".zsh", ".yaml", ".yml", ".md", ".txt", ".env", ".log":
			w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		case ".css":
			w.Header().Set("Content-Type", "text/css; charset=utf-8")
		case ".html", ".htm":
			w.Header().Set("Content-Type", "text/html; charset=utf-8")
		case ".svg":
			w.Header().Set("Content-Type", "image/svg+xml")
		}

		http.ServeFile(w, r, targetPath)
	}
}

