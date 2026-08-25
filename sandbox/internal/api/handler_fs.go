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
	FilePath string `json:"file_path"`
	Content  string `json:"content"`
}

type FileWriteResponse struct {
	Success bool   `json:"success"`
	Bytes   int    `json:"bytes"`
	Message string `json:"message,omitempty"`
}

type FileListRequest struct {
	DirPath string `json:"dir_path,omitempty"`
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

// 路径防越界校验
func resolveSafePath(baseWorkspace, relPath string) (string, error) {
	absBase, err := filepath.Abs(baseWorkspace)
	if err != nil {
		return "", err
	}
	cleanRel := filepath.Clean(relPath)
	target := filepath.Join(absBase, cleanRel)
	absTarget, err := filepath.Abs(target)
	if err != nil {
		return "", err
	}

	if !strings.HasPrefix(absTarget, absBase) {
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

		targetPath, err := resolveSafePath(workspaceDir, req.FilePath)
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

		targetPath, err := resolveSafePath(workspaceDir, req.FilePath)
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

		targetDir, err := resolveSafePath(workspaceDir, req.DirPath)
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

		targetPath, err := resolveSafePath(workspaceDir, filePath)
		if err != nil {
			http.Error(w, err.Error(), http.StatusForbidden)
			return
		}

		info, err := os.Stat(targetPath)
		if err != nil {
			if os.IsNotExist(err) {
				http.Error(w, fmt.Sprintf("file not found: %s", filePath), http.StatusNotFound)
			} else {
				http.Error(w, err.Error(), http.StatusInternalServerError)
			}
			return
		}

		if info.IsDir() {
			http.Error(w, "cannot serve directory directly", http.StatusBadRequest)
			return
		}

		// 跨域支持
		w.Header().Set("Access-Control-Allow-Origin", "*")

		// 支持强制下载模式
		if r.URL.Query().Get("download") == "true" || r.URL.Query().Get("download") == "1" {
			w.Header().Set("Content-Disposition", fmt.Sprintf("attachment; filename=%q", filepath.Base(targetPath)))
		}

		http.ServeFile(w, r, targetPath)
	}
}

