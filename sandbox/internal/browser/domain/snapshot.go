package domain

import (
	"fmt"
	"strings"
	"time"
)

// PageSnapshot 某一时刻页面的完整感知快照（不可变值对象）
type PageSnapshot struct {
	URL         string               `json:"url"`
	Title       string               `json:"title"`
	ActiveTabID string               `json:"active_tab_id,omitempty"` // 当前激活的 Tab ID
	TotalTabs   int                  `json:"total_tabs,omitempty"`    // 当前浏览器上下文共打开的标签页数量
	DOMTree     string               `json:"dom_tree,omitempty"`      // 带有完整层级缩进的语义化 DOM 结构树
	Elements    []InteractiveElement `json:"elements"`
	Screenshot  []byte               `json:"screenshot,omitempty"`    // 可选的 PNG Base64
	CapturedAt  time.Time            `json:"captured_at"`
}

// FormatForLLM 将快照转换为 LLM 最易读且具备完整层级上下文的 Markdown 结构
func (s *PageSnapshot) FormatForLLM() string {
	var sb strings.Builder

	tabInfo := ""
	if s.TotalTabs > 1 {
		tabInfo = fmt.Sprintf(" (标签页 %s / 共 %d 个)", s.ActiveTabID, s.TotalTabs)
	}
	sb.WriteString(fmt.Sprintf("页面状态: %s%s\nURL: %s\n", s.Title, tabInfo, s.URL))

	// 优先呈现完整的语义 DOM 树
	if s.DOMTree != "" {
		sb.WriteString("\n[页面语义 DOM 结构与已编号元素树]:\n")
		sb.WriteString(s.DOMTree)
		sb.WriteString("\n")
		return sb.String()
	}

	sb.WriteString("\n[当前视口可见的可交互元素]:\n")
	if len(s.Elements) == 0 {
		sb.WriteString("(当前页面视口内未检测到可交互的按钮、链接或表单元素)\n")
		return sb.String()
	}

	lastContext := ""
	for _, el := range s.Elements {
		if el.ContextText != "" && el.ContextText != lastContext {
			sb.WriteString(fmt.Sprintf("\n# 容器: \"%s\"\n", el.ContextText))
			lastContext = el.ContextText
		}

		extra := ""
		if el.Placeholder != "" {
			extra += fmt.Sprintf(" placeholder=%q", el.Placeholder)
		}
		if el.Value != "" {
			extra += fmt.Sprintf(" value=%q", el.Value)
		}
		if el.Href != "" {
			extra += fmt.Sprintf(" -> %s", el.Href)
		}
		if el.IsDisabled {
			extra += " [已禁用]"
		}

		sb.WriteString(fmt.Sprintf("- [%d] (%s) %q%s\n", el.ID, el.TagName, el.Text, extra))
	}

	return sb.String()
}
