package domain

// ElementID 探针分配给元素的数字编号（用于 LLM 引用并触发点击/输入）
type ElementID int

// InteractiveElement 代表页面上识别出的一个可交互元素（值对象）
type InteractiveElement struct {
	ID          ElementID `json:"id"`
	TagName     string    `json:"tag_name"`               // DIV, BUTTON, INPUT, A, SELECT, TEXTAREA
	Text        string    `json:"text"`                   // 按钮名/文字内容/Aria-label
	Role        string    `json:"role,omitempty"`         // button, link, checkbox 等
	ContextText string    `json:"context_text,omitempty"` // 向上提取的卡片/列表容器上下文标题
	Placeholder string    `json:"placeholder,omitempty"`  // input 占位符
	Value       string    `json:"value,omitempty"`        // input/select 当前值
	Href        string    `json:"href,omitempty"`         // a 标签跳转链接
	IsDisabled  bool      `json:"is_disabled,omitempty"`  // 是否禁用状态
}
