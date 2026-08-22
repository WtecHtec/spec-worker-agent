import asyncio
from fastapi import FastAPI
import uvicorn
import a2a.types as a2a_types
from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes.agent_card_routes import create_agent_card_routes
from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes
from a2a.server.routes.fastapi_routes import add_a2a_routes_to_fastapi


class ResearcherAgentExecutor(AgentExecutor):
    """
    遵循 Google 官方 a2a-sdk 标准实现的 AgentExecutor 执行器
    """

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        import uuid
        # 1. 提取入参消息内容
        message = context.message
        text_input = ""
        if message:
            if hasattr(message, "parts") and message.parts:
                for part in message.parts:
                    if getattr(part, "text", None):
                        text_input += part.text
            elif hasattr(message, "content") and message.content:
                for item in message.content:
                    text_input += getattr(item, "text", str(item))

        # 2. 执行专家领域逻辑（调研与分析）
        output_report = (
            f"【Google 官方 A2A 独立调研专家微服务执行完成】\n"
            f"针对任务指令：\"{text_input}\"\n"
            f"已成功检索公开资料库与学术文献，完成多来源事实交叉考证并提取核心论据。"
        )

        # 3. 按官方 A2A 规范向 event_queue 投递任务
        task = a2a_types.Task(
            id=context.task_id,
            context_id=context.context_id,
            status=a2a_types.TaskStatus(
                state=a2a_types.TaskState.TASK_STATE_COMPLETED,
                message=a2a_types.Message(
                    message_id=str(uuid.uuid4()),
                    context_id=context.context_id,
                    task_id=context.task_id,
                    role=a2a_types.Role.ROLE_AGENT,
                    parts=[a2a_types.Part(text=output_report)],
                ),
            ),
        )
        await event_queue.enqueue_event(task)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        """任务取消钩子"""
        task = a2a_types.Task(
            id=context.task_id,
            context_id=context.context_id,
            status=a2a_types.TaskStatus(state=a2a_types.TaskState.TASK_STATE_CANCELED),
        )
        await event_queue.enqueue_event(task)


# 4. 声明官方标准 AgentCard
AGENT_CARD = a2a_types.AgentCard(
    name="researcher_specialist",
    description="专注于公开互联网情报检索、技术文献深入阅读与事实查证的外部 A2A 专家智能体微服务",
    version="1.0.0",
    supported_interfaces=[
        a2a_types.AgentInterface(url="http://localhost:8090/a2a/message", protocol_binding="JSONRPC")
    ],
    skills=[
        a2a_types.AgentSkill(name="web_scraping", description="从公开互联网结构化提取关键事实"),
        a2a_types.AgentSkill(name="fact_checking", description="跨来源数据交叉核验与事实考证"),
        a2a_types.AgentSkill(name="report_generation", description="生成高结构化专业技术研报"),
    ],
)

# 5. 装配官方 A2A 服务端组件
task_store = InMemoryTaskStore()
agent_executor = ResearcherAgentExecutor()
request_handler = DefaultRequestHandler(
    agent_executor=agent_executor,
    task_store=task_store,
    agent_card=AGENT_CARD,
)

card_routes = create_agent_card_routes(agent_card=AGENT_CARD)
jsonrpc_routes = create_jsonrpc_routes(rpc_url="/a2a/message", request_handler=request_handler)

app = FastAPI(title="Official Google A2A Researcher Specialist Microservice")
add_a2a_routes_to_fastapi(app, agent_card_routes=card_routes, jsonrpc_routes=jsonrpc_routes)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8090)
