# Agent Runtime HITL 人机协同与安全审批机制设计规范

## 1. 架构目标与协同流程

Human-In-The-Loop (HITL) 允许自主智能体在遇到**信息模糊、高危系统变更或特定业务审批**时，主动或被动安全挂起（Suspend），交由人类做出决策后无缝恢复执行（Resume）。

```
Agent Node (LLM 输出 tool_calls)
      │
      ▼
Tools Node 拦截与派发
      │
  [安全审计与决策判断]
      ├── 1. 主动表单申请: tool == "hitl_request_input"
      └── 2. 高危操作拦截: tool == "sandbox_bash" 且入参命中 rm -rf/kill
      │
      ▼
调用官方 interrupt(payload) ──> 图执行挂起，Checkpointer 冻结快照
      │
      ▼ (通过 SSE 抛出 event: interrupt)
前端弹出结构化审批卡片 (<HitlFormCard />)
      │
      ▼ 用户填写并提交
前端调用 stream.submit(null, { command: { resume: decision } })
      │
      ▼
Tools Node 接收人类决策:
      ├── 批准: 继续真实执行工具，并在 ToolMessage 中追加【HITL安全审计留痕】
      └── 拒绝: 拦截执行，向 ToolMessage 注入人类拒绝理由并安全回退
      │
      ▼
回流至 Agent Node，继续后续推理
```

---

## 2. 触发形态设计

### 2.1 主动交互型（`hitl_request_input` 工具）
定义于 [src/tools/hitl.py]( /agent-runtime/src/tools/hitl.py)：
- **入参格式**：
  ```json
  {
    "title": "生产环境部署确认",
    "description": "智能体准备向生产集群更新服务，请确认配置",
    "risk_level": "high",
    "form_fields": [
      { "name": "cluster", "label": "目标集群", "type": "select", "options": ["prod-us", "prod-eu"] },
      { "name": "confirm_deploy", "label": "确认发布", "type": "boolean" }
    ]
  }
  ```
- **执行逻辑**：直接触发 `interrupt(...)`，挂起图等待人类填写表单并提交。

### 2.2 被动安全防御型（高危操作拦截）
定义于 [src/nodes/tools_node.py]( /agent-runtime/src/nodes/tools_node.py)：
- **拦截策略**：
  对 `sandbox_bash`（命令执行）、数据库删除操作等，自动进行正则安全匹配（如 `rm -rf`, `mkfs`, `kill -9`）；
- **动态生成审批单**：
  若命中高危特征，自动生成 `risk_level="critical"` 的人机确认中断，严防智能体脱缰。

---

## 3. 结构化安全审计留痕（Audit Trail）

每次人类介入（无论是表单填写还是审批批准/拒绝），[tools_node.py]( /agent-runtime/src/nodes/tools_node.py) 均在 `ToolMessage` 头部显式持久化写入结构化留痕文本：
```markdown
【HITL安全审计留痕】
- 授权审批主题: 生产环境部署确认
- 人类决策数据: {"confirm_deploy": true, "cluster": "prod-us"}
- 安全执行结果: 已获得人工显式授权，允许工具执行
```
- **价值**：完整的决策数据、审批时间与人类输入被永久保存于 LangGraph Checkpoint 状态历史中，供合规审计与事后追溯。

---

## 4. 前端交互与恢复协议

1. **协议捕获**：
   在前端 [useLangGraphStream.ts]( /frontend/src/hooks/useLangGraphStream.ts) 中自动提取 `stream.interrupt.action_requests`；
2. **表单呈现**：
   通过 [HitlFormCard.tsx]( /frontend/src/components/chat/HitlFormCard.tsx) 动态根据 `form_fields` 渲染对应输入框、选择器与开关；
3. **恢复调用**：
   提交时调用 `resume(formData)`，底层通过官方 SDK 发送 `command.resume` 恢复执行，零额外业务轮询。
