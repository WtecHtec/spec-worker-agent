from typing import Any
from datetime import datetime, timezone
import structlog

logger = structlog.get_logger()


class EpisodicMemoryManager:
    """
    自省反思与经验沉淀记忆体系（Episodic Memory & Self-Reflection）：
    在长任务或复合任务执行完成后，自动触发轻量自省，
    沉淀高价值策略与避坑经验，并在后续相似任务启动时进行前置知识注入。
    """

    def __init__(self):
        # 内存级经验知识库（在生产部署中可通过 pgvector 向量数据库持久化）
        self._memories: list[dict[str, Any]] = []

    def reflect_and_store(
        self,
        task_id: str,
        goal: str,
        steps_summary: list[dict[str, Any]],
        final_text: str,
        success: bool = True,
    ) -> dict[str, Any]:
        """
        任务完成后触发自省反思并固化经验
        """
        key_actions = [s.get("title", "") for s in steps_summary if s.get("title")]
        lesson = (
            f"成功经验：对于任务 [{goal[:30]}]，通过步骤 [{', '.join(key_actions[:3])}] 顺利达成目标。"
            if success
            else f"避坑指南：执行 [{goal[:30]}] 时遇到阻碍，注意避免相同参数死循环并及时更换策略。"
        )

        memory_entry = {
            "task_id": task_id,
            "goal": goal,
            "success": success,
            "lesson": lesson,
            "key_steps": key_actions,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        self._memories.append(memory_entry)
        logger.info("episodic_memory_stored", task_id=task_id, lesson=lesson)
        return memory_entry

    def retrieve_relevant_experiences(self, current_goal: str, top_k: int = 2) -> list[str]:
        """
        为新任务检索最相关的历史经验
        """
        if not self._memories:
            return []

        # 基于关键词简单相关度打分（后续可无缝接入 pgvector）
        scored: list[tuple[int, str]] = []
        tokens = set(current_goal.lower().split())

        for entry in self._memories:
            score = sum(1 for t in tokens if t in entry["goal"].lower())
            if score > 0 or entry.get("success"):
                scored.append((score, entry["lesson"]))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:top_k]]
