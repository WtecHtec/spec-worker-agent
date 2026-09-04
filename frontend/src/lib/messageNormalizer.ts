/**
 * LangGraph 官方消息协议工业级归一化器 (Message Normalizer)
 * 彻底消除官方协议中历史快照与流式切片命名双轨制（如 type: "ai" vs "AIMessageChunk"）带来的割裂
 */

export type NormalizedRole = "user" | "agent" | "tool" | "system";

export interface NormalizedStep {
  toolCallId: string;
  toolName: string;
  args: Record<string, any>;
  output?: string;
  thought?: string;
}

export interface NormalizedTurn {
  id: string;
  role: NormalizedRole;
  content: string;
  steps?: NormalizedStep[];
  tool_calls?: any[];
  created_at?: string;
  rawMessages: any[];
}

/**
 * 统一归一化消息角色
 */
export function normalizeRole(msg: any): NormalizedRole {
  if (!msg) return "agent";
  const raw = String(msg.type || msg.role || "").toLowerCase().trim();

  // 1. 用户消息族
  if (
    raw === "human" ||
    raw === "user" ||
    raw === "humanmessage" ||
    raw === "humanmessagechunk"
  ) {
    return "user";
  }

  // 2. 工具产出族
  if (
    raw === "tool" ||
    raw === "toolmessage" ||
    raw === "toolmessagechunk"
  ) {
    return "tool";
  }

  // 3. 系统配置族
  if (
    raw === "system" ||
    raw === "systemmessage"
  ) {
    return "system";
  }

  // 4. Agent 回答族（兼容静态与流式 AIMessageChunk）
  return "agent";
}

/**
 * 统一提取消息文本内容（兼容复杂多模态与分片结构）
 */
export function extractMessageText(msg: any): string {
  if (!msg) return "";
  if (typeof msg.content === "string") return msg.content;
  if (msg.content && typeof msg.content === "object") {
    if (typeof msg.content.text === "string") return msg.content.text;
    if (Array.isArray(msg.content)) {
      return msg.content
        .map((part: any) => {
          if (typeof part === "string") return part;
          if (part && typeof part === "object") {
            return part.text || part.output || "";
          }
          return "";
        })
        .join("");
    }
  }
  return "";
}

/**
 * 将平铺的原始 LangGraph 消息流按照任务交互轮次（Turn）聚合
 * 将 AIMessage(tool_calls)、ToolMessage(output) 以及后续总结归并入同一张 Agent 卡片
 */
export function groupMessagesIntoTurns(rawMessages: any[]): NormalizedTurn[] {
  if (!Array.isArray(rawMessages)) return [];

  const turns: NormalizedTurn[] = [];
  let currentAgentTurn: NormalizedTurn | null = null;

  for (let i = 0; i < rawMessages.length; i++) {
    const msg = rawMessages[i];
    const role = normalizeRole(msg);

    if (role === "user") {
      // 遇到新的用户消息，封闭之前的 AgentTurn
      if (currentAgentTurn) {
        turns.push(currentAgentTurn);
        currentAgentTurn = null;
      }
      turns.push({
        id: msg.id || `user-turn-${i}`,
        role: "user",
        content: extractMessageText(msg),
        created_at: msg.created_at || msg.response_metadata?.created_at,
        rawMessages: [msg],
      });
    } else if (role === "system") {
      // 系统消息忽略或独立保存
      continue;
    } else {
      // agent 或 tool 均纳入当前 AgentTurn
      if (!currentAgentTurn) {
        currentAgentTurn = {
          id: msg.id || `agent-turn-${i}`,
          role: "agent",
          content: "",
          steps: [],
          created_at: msg.created_at || msg.response_metadata?.created_at,
          rawMessages: [],
        };
      }
      currentAgentTurn.rawMessages.push(msg);

      const text = extractMessageText(msg);

      if (role === "agent") {
        if (msg.tool_calls && Array.isArray(msg.tool_calls) && msg.tool_calls.length > 0) {
          // 提取工具调用，并将伴随该批工具调用的思考/说明正文注入到步骤中
          for (let tcIdx = 0; tcIdx < msg.tool_calls.length; tcIdx++) {
            const tc = msg.tool_calls[tcIdx];
            currentAgentTurn.steps!.push({
              toolCallId: tc.id || `tc-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
              toolName: tc.name,
              args: tc.args || {},
              // 仅在当前批次第一个工具上挂载说明文本，避免多工具并行时文字重复
              thought: tcIdx === 0 ? (text || undefined) : undefined,
            });
          }
        } else if (text) {
          // 纯文本回复（阶段小结或最终回答）
          currentAgentTurn.content = text;
        }
      } else if (role === "tool") {
        // 关联工具返回结果
        const toolCallId = msg.tool_call_id;
        const output = text;
        const matched = currentAgentTurn.steps!.find((s) => s.toolCallId === toolCallId);
        if (matched) {
          matched.output = output;
        } else {
          currentAgentTurn.steps!.push({
            toolCallId: toolCallId || `tool-step-${i}`,
            toolName: msg.name || "tool",
            args: {},
            output,
          });
        }
        // 注意：Tool 产出绝不能覆盖 currentAgentTurn.content！
      }
    }
  }

  if (currentAgentTurn) {
    turns.push(currentAgentTurn);
  }

  return turns;
}

/**
 * 动静分离拆解器：将消息流拆分为“已完成静态历史”与“当前活跃流式轮次”
 * 确保推流期间历史列表引用绝对稳定（0 重绘），高频更新仅集中在 activeTurn
 */
export function splitCompletedAndActive(
  rawMessages: any[],
  isStreaming: boolean
): { completedTurns: NormalizedTurn[]; activeTurn: NormalizedTurn | null } {
  const allTurns = groupMessagesIntoTurns(rawMessages);
  if (allTurns.length === 0) {
    return { completedTurns: [], activeTurn: null };
  }

  // 仅在正在处于流式态且末尾为 Agent 回答时，将其隔离为 activeTurn
  const lastTurn = allTurns[allTurns.length - 1];
  if (isStreaming && lastTurn.role === "agent") {
    return {
      completedTurns: allTurns.slice(0, -1),
      activeTurn: lastTurn,
    };
  }

  return {
    completedTurns: allTurns,
    activeTurn: null,
  };
}
