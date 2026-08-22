from pathlib import Path
from typing import Any
import jinja2
from datetime import datetime, timezone
import structlog

logger = structlog.get_logger()


class PromptManager:
    """
    提示词管理器：
    负责从 prompts/ 目录加载 Markdown 模板并通过 Jinja2 进行参数渲染。
    """

    def __init__(self, prompts_dir: str | Path | None = None):
        if prompts_dir is None:
            # 默认指向项目根目录下的 prompts 目录
            base_dir = Path(__file__).resolve().parent.parent.parent.parent
            self.prompts_dir = base_dir / "prompts"
        else:
            self.prompts_dir = Path(prompts_dir)

        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(self.prompts_dir)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, template_rel_path: str, **kwargs: Any) -> str:
        """
        渲染指定模板文件（例如 'system/react_worker.md'）。
        内置 current_time 默认参数。
        """
        try:
            template = self._env.get_template(template_rel_path)
            context = {
                "current_time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
                **kwargs,
            }
            return template.render(**context)
        except Exception as e:
            logger.error("prompt_render_failed", template=template_rel_path, error=str(e))
            raise


_default_manager: PromptManager | None = None


def get_prompt_manager() -> PromptManager:
    global _default_manager
    if _default_manager is None:
        _default_manager = PromptManager()
    return _default_manager
