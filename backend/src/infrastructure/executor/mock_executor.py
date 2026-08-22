import asyncio
import json
import os
from pathlib import Path
from typing import AsyncGenerator
from src.config.settings import get_settings
from src.infrastructure.executor.base import AgentExecutor

settings = get_settings()

# 关键词 → mock 文件映射
KEYWORD_MAP = {
    "销售": "sales_analysis",
    "分析": "sales_analysis",
    "报告": "sales_analysis",
    "文件": "file_processing",
    "处理": "file_processing",
    "上传": "file_processing",
}

DEFAULT_MOCK = "sales_analysis"


def _resolve_mock_file(content: str) -> dict:
    """根据输入内容匹配 mock 文件"""
    mock_name = DEFAULT_MOCK
    for keyword, name in KEYWORD_MAP.items():
        if keyword in content:
            mock_name = name
            break

    mock_dir = Path(settings.mock_files_dir)
    mock_path = mock_dir / f"{mock_name}.json"
    with open(mock_path, encoding="utf-8") as f:
        return json.load(f)


class MockAgentExecutor(AgentExecutor):
    """
    Mock 执行器：从 JSON 文件读取预设步骤，逐步产出。
    实现 AgentExecutor 接口，Worker 可无感知地切换为 LlmAgentExecutor。
    """

    def __init__(self, task_input: dict, resume_from_step: int = 0):
        content = task_input.get("content", "")
        self.mock_data = _resolve_mock_file(content)
        self.resume_from_step = resume_from_step
        self.steps: list[dict] = self.mock_data.get("steps", [])
        self.result: dict = self.mock_data.get("result", {})

    async def run(self) -> AsyncGenerator[dict, None]:
        """
        异步 generator，每次 yield 一个步骤 dict。
        步骤格式：{ step_index, type, content, wait_for_human }
        """
        for step in self.steps:
            if step["step_index"] <= self.resume_from_step:
                continue  # 跳过已执行步骤（断点续传）

            delay = step.get("delay_ms", 500) / 1000
            await asyncio.sleep(delay)

            yield {
                "step_index": step["step_index"],
                "type": step["type"],
                "content": step["content"],
                "wait_for_human": step.get("wait_for_human", False),
            }

            # 遇到 HITL，暂停产出，等 Worker 处理
            if step.get("wait_for_human", False):
                return

    def get_result(self) -> dict:
        return self.result
