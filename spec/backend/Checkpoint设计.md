Checkpoint 需要记录三类信息：

① 执行进度（我跑到哪了）
  {
    task_id: "abc-123",
    user_id: "user-A",
    last_completed_step: 5,
    next_step_to_run: 6,
  }

② 执行上下文（LLM 需要知道什么）
  {
    conversation_history: [...],  ← 对话历史（可能很长，考虑摘要）
    tool_results: {...},          ← 已调用工具的结果
    variables: {...},             ← 任务中间变量（如"已找到10篇文章"）
  }

③ 幂等性保障（避免重复副作用）
  {
    completed_tool_calls: ["search#1", "email#3"],  ← 已执行过的工具
    idempotency_keys: {...}                          ← 每个副作用的唯一标识
  }
