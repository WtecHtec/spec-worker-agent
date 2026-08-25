package application

// BrowserToolResponse 标准的浏览器工具执行返回（供 LLM 消费）
type BrowserToolResponse struct {
	Success          bool   `json:"success"`
	Output           string `json:"output,omitempty"`            // 格式化后的 Observation 文本 (包含已编号结构)
	ScreenshotBase64 string `json:"screenshot_base64,omitempty"` // 可选截图 Base64 数据
	FilePath         string `json:"file_path,omitempty"`         // 沙箱内部保存的相对文件路径 (如 screenshots/shot_1.png)
	PreviewURL       string `json:"preview_url,omitempty"`       // 原生在线预览/下载 URL (如 /fs/raw?path=...)
	Error            string `json:"error,omitempty"`             // 错误信息（如果有）
	URL              string `json:"url,omitempty"`               // 当前页面 URL
	Title            string `json:"title,omitempty"`             // 当前页面标题
	ActiveTabID      string `json:"active_tab_id,omitempty"`      // 当前激活的 Tab ID
	TotalTabs        int    `json:"total_tabs,omitempty"`        // 当前会话打开的标签页数量
}

type OpenPageRequest struct {
	SessionID  string `json:"session_id,omitempty"`
	URL        string `json:"url"`
	TimeoutSec int    `json:"timeout_sec,omitempty"`
}

type ClosePageRequest struct {
	SessionID string `json:"session_id,omitempty"`
}

type GetSnapshotRequest struct {
	SessionID         string `json:"session_id,omitempty"`
	IncludeScreenshot bool   `json:"include_screenshot,omitempty"`
}

type ClickRequest struct {
	SessionID string `json:"session_id,omitempty"`
	ElementID int    `json:"element_id"`
}

type ScreenshotRequest struct {
	SessionID string `json:"session_id,omitempty"`
	FullPage  bool   `json:"full_page,omitempty"`
	SavePath  string `json:"save_path,omitempty"` // 自定义保存的相对路径（如 screenshots/home.png）
}

type ExecuteToolRequest struct {
	SessionID string                 `json:"session_id,omitempty"`
	ToolName  string                 `json:"tool_name"`
	Arguments map[string]interface{} `json:"arguments"`
}
