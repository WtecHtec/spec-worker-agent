from typing import Annotated, Any
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """
    LangGraph Agent 核心状态：
    - messages: 完整对话与多轮工具调用消息列表（通过 add_messages 实现幂等增量追加，保持全量不删除，用于前端渲染）
    - summary: 提炼滚动的历史阶段性成果与对话中期记忆摘要
    - active_cut_index: 送入 LLM 推理的近期上下文起始游标（0 代表全量未截断）
    - pending_hitl: 当前待人类处理的 HITL 交互表单元数据（标题、描述、单选/多选/输入字段等）
    - hitl_decision: 用户提交的审批或表单结果
    """
    messages: Annotated[list[BaseMessage], add_messages]
    summary: str
    active_cut_index: int
    pending_hitl: dict[str, Any] | None
    hitl_decision: dict[str, Any] | None
