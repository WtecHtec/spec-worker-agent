import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.domain.services.agents.planner import (
    PlannerAgent,
    PlanModel,
    PlanStepModel,
    _extract_json_from_llm_response,
)
from src.domain.services.memory.memory_manager import MemoryManager
from src.domain.services.flow.agent_flow import PlanAndExecuteFlow
from src.domain.services.tools.registry import ToolRegistry


def test_extract_json_from_llm_response():
    # 1. 纯 JSON
    raw_1 = '{"goal": "test goal", "steps": []}'
    assert _extract_json_from_llm_response(raw_1)["goal"] == "test goal"

    # 2. Markdown 代码块中的 JSON
    raw_2 = '```json\n{"goal": "markdown goal", "steps": [{"id": 1, "title": "step 1", "description": "desc", "status": "pending"}]}\n```'
    parsed_2 = _extract_json_from_llm_response(raw_2)
    assert parsed_2["goal"] == "markdown goal"
    assert len(parsed_2["steps"]) == 1

    # 3. 伴随前缀文字的 JSON
    raw_3 = '这是我为你生成的计划：\n{"goal": "prefix goal", "steps": []}\n请确认！'
    parsed_3 = _extract_json_from_llm_response(raw_3)
    assert parsed_3["goal"] == "prefix goal"


@pytest.mark.asyncio
async def test_planner_agent_create_plan():
    planner = PlannerAgent()
    mock_plan_json = """
    ```json
    {
      "goal": "抓取文章并生成报告",
      "steps": [
        {
          "id": 1,
          "title": "读取网页内容",
          "description": "通过 Jina Reader 读取文章正文",
          "status": "pending"
        },
        {
          "id": 2,
          "title": "生成 HTML 报告",
          "description": "在沙箱写入 report.html 并返回直链",
          "status": "pending"
        }
      ]
    }
    ```
    """

    with patch.object(planner.client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
        mock_choice = MagicMock()
        mock_choice.message.content = mock_plan_json
        mock_create.return_value = MagicMock(choices=[mock_choice])

        plan = await planner.create_plan("请帮我总结博客并生成 HTML 报告", ctx={"workspace_dir": "/tmp"})
        assert isinstance(plan, PlanModel)
        assert plan.goal == "抓取文章并生成报告"
        assert len(plan.steps) == 2
        assert plan.steps[0].title == "读取网页内容"
        assert plan.steps[1].title == "生成 HTML 报告"


@pytest.mark.asyncio
async def test_planner_agent_dynamic_replan():
    planner = PlannerAgent()
    current_plan = PlanModel(
        goal="抓取文章并生成报告",
        steps=[
          PlanStepModel(id=1, title="读取网页内容", description="读取网页", status="completed", result_summary="已抓取"),
          PlanStepModel(id=2, title="运行本地 Python 统计脚本", description="统计字数", status="pending"),
        ],
    )

    mock_replan_json = """
    ```json
    {
      "goal": "抓取文章并生成报告",
      "steps": [
        {
          "id": 1,
          "title": "读取网页内容",
          "description": "读取网页",
          "status": "completed",
          "result_summary": "已抓取"
        },
        {
          "id": 2,
          "title": "更换为纯内存计算与直接生成 HTML",
          "description": "跳过失败的本地脚本，直接写入 HTML 产物",
          "status": "pending"
        }
      ]
    }
    ```
    """

    with patch.object(planner.client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
        mock_choice = MagicMock()
        mock_choice.message.content = mock_replan_json
        mock_create.return_value = MagicMock(choices=[mock_choice])

        replan = await planner.replan(
            goal="抓取文章并生成报告",
            current_plan=current_plan,
            failed_step_id=2,
            reason="Python 缺少依赖 pandas 导致脚本执行报错",
            ctx={"workspace_dir": "/tmp"},
        )

        assert replan.is_replan is True
        assert len(replan.steps) == 2
        assert "更换为纯内存计算" in replan.steps[1].title


def test_memory_manager_compaction():
    mm = MemoryManager()
    for i in range(1, 6):
        step = PlanStepModel(id=i, title=f"Step {i}", description="desc", status="completed", result_summary=f"Output {i}")
        mm.record_step_result(step, f"Raw output {i}")

    summary = mm.compact_memory_if_needed()
    assert "【历史阶段成果摘要】:" in summary
    assert "Step 1" in summary
    assert "Step 2" in summary


@pytest.mark.asyncio
async def test_plan_and_execute_flow_execution():
    tool_reg = ToolRegistry()
    planner = PlannerAgent(tool_registry=tool_reg)

    mock_plan = PlanModel(
        goal="执行单步快速任务",
        steps=[
            PlanStepModel(id=1, title="创建文件", description="写入 hello.txt", status="pending"),
        ],
    )

    with patch.object(planner, "create_plan", new_callable=AsyncMock) as mock_create_plan:
        mock_create_plan.return_value = mock_plan

        flow = PlanAndExecuteFlow(planner=planner, tool_registry=tool_reg)

        # Mock ReActAgent.run
        with patch("src.domain.services.flow.agent_flow.ReActAgent") as MockReActAgent:
            mock_worker_instance = MagicMock()
            async def mock_run_generator(*args, **kwargs):
                yield {"step_index": 3, "type": "THINKING", "content": {"text": "思考中"}}
                yield {"step_index": 4, "type": "FINAL", "content": {"text": "文件创建完成"}}

            mock_worker_instance.run = mock_run_generator
            MockReActAgent.return_value = mock_worker_instance

            events = []
            async for event in flow.run("创建一个 hello.txt 文件", ctx={"task_id": "test_1"}):
                events.append(event)

            types = [e["type"] for e in events]
            assert "PLAN_GENERATED" in types
            assert "THINKING" in types
            assert "FINAL" in types
            # 验证单步快速任务直接产出最终结果
            final_step = next(e for e in events if e["type"] == "FINAL")
            assert "文件创建完成" in final_step["content"]["text"]


@pytest.mark.asyncio
async def test_planner_with_history_messages():
    planner = PlannerAgent()
    mock_plan_json = '{"goal": "截取博客页面", "steps": [{"id": 1, "title": "截图", "description": "截取博客", "status": "pending"}]}'

    with patch.object(planner.client.chat.completions, "create", new_callable=AsyncMock) as mock_create:
        mock_choice = MagicMock()
        mock_choice.message.content = mock_plan_json
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_create.return_value = mock_response

        ctx = {
            "history_messages": [
                {"role": "user", "content": "打开主页并点击进入博客"},
                {"role": "assistant", "content": "已打开博客页面，下一步可进行截图。"},
            ]
        }
        plan = await planner.create_plan("继续", ctx)
        assert plan.goal == "截取博客页面"
        
        # 验证发送给 LLM 的 messages 中包含了历史消息
        call_kwargs = mock_create.call_args[1]
        sent_messages = call_kwargs["messages"]
        assert len(sent_messages) == 4  # system + 2 history + user goal
        assert sent_messages[1]["content"] == "打开主页并点击进入博客"
        assert sent_messages[2]["content"] == "已打开博客页面，下一步可进行截图。"
        assert "继续" in sent_messages[3]["content"]
