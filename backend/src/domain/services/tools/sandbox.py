import asyncio
from pathlib import Path
from typing import Any
import structlog
from .base import BaseTool, ToolResult
from src.config.settings import get_settings
from src.infrastructure.sandbox.client import get_sandbox_client, SandboxClient

logger = structlog.get_logger()


def _get_session_workspace(base_workspace: str, session_id: str | None = None) -> Path:
    """获取会话级工作空间根目录"""
    base = Path(base_workspace).resolve()
    if session_id and session_id.strip():
        session_ws = base / "sessions" / session_id.strip()
    else:
        session_ws = base
    return session_ws


def _resolve_safe_local_path(base_workspace: str, relative_or_abs_path: str, session_id: str | None = None) -> Path:
    """本地回退模式下的路径安全校验（支持会话隔离）"""
    workspace = _get_session_workspace(base_workspace, session_id)
    target = (workspace / relative_or_abs_path).resolve()
    if not str(target).startswith(str(workspace)):
        raise PermissionError(f"沙箱安全拦截：路径越界访问拒绝 [{relative_or_abs_path}] 不在工作空间 [{workspace}] 内")
    return target


_resolve_safe_sandbox_path = _resolve_safe_local_path



class SandboxRunCommandTool(BaseTool):
    """沙箱命令执行工具"""

    def __init__(self, sandbox_client: SandboxClient | None = None):
        self.sandbox_client = sandbox_client or get_sandbox_client()
        self.settings = get_settings()

    @property
    def name(self) -> str:
        return "sandbox_run_command"

    @property
    def description(self) -> str:
        return (
            "在隔离沙箱容器环境中执行指定的 shell 命令（如 python, pytest, ls, git 等）。"
            "命令以非交互模式运行，具备超时和输出截断防护。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "要执行的完整 shell 命令行字符串",
                },
                "cwd": {
                    "type": "string",
                    "description": "可选的相对子目录路径，默认在沙箱工作区根目录执行",
                },
            },
            "required": ["command"],
        }

    async def execute(self, ctx: dict[str, Any], command: str, cwd: str = ".") -> ToolResult:
        session_id = ctx.get("session_id")

        # 1. 优先使用远程/Docker 独立沙箱
        if self.settings.sandbox_enabled:
            is_alive = await self.sandbox_client.health_check()
            if is_alive:
                res = await self.sandbox_client.execute_command(
                    command, cwd=cwd, timeout=60, session_id=session_id
                )
                output = res.get("output") or res.get("combined") or "(无输出)"
                return ToolResult(
                    output=output,
                    is_error=res.get("is_error", False),
                    metadata={
                        "mode": "docker_sandbox",
                        "exec_id": res.get("exec_id"),
                        "duration_ms": res.get("duration_ms"),
                        "is_truncated": res.get("is_truncated", False),
                    },
                )
            else:
                logger.warning("sandbox_container_unhealthy_falling_back_to_local")

        # 2. 本地安全回退模式 (Local Safe Workspace)
        workspace_dir = ctx.get("workspace_dir", self.settings.llm_workspace_dir)
        session_id = ctx.get("session_id")
        try:
            work_dir = _resolve_safe_local_path(workspace_dir, cwd, session_id=session_id)
            work_dir.mkdir(parents=True, exist_ok=True)

            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(work_dir),
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=60.0)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except Exception:
                    pass
                return ToolResult(
                    output="沙箱错误：命令执行超时（上限 60 秒），已被沙箱自动终止。",
                    is_error=True,
                    metadata={"exit_code": -1, "timeout": True, "mode": "local_fallback"},
                )

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            exit_code = proc.returncode

            combined_output = ""
            if stdout:
                combined_output += f"[stdout]\n{stdout}\n"
            if stderr:
                combined_output += f"[stderr]\n{stderr}\n"
            if not combined_output.strip():
                combined_output = f"(命令执行成功，退出码: {exit_code}，无任何标准输出)"

            is_truncated = False
            if len(combined_output) > 4000:
                head = combined_output[:1500]
                tail = combined_output[-2000:]
                combined_output = (
                    f"{head}\n\n... [沙箱输出过长已自动截断，省略中间部分] ...\n\n{tail}"
                )
                is_truncated = True

            return ToolResult(
                output=combined_output.strip(),
                is_error=(exit_code != 0),
                metadata={"exit_code": exit_code, "truncated": is_truncated, "mode": "local_fallback"},
            )

        except Exception as e:
            return ToolResult(
                output=f"沙箱执行异常: {str(e)}",
                is_error=True,
                metadata={"error": str(e), "mode": "local_fallback"},
            )


class SandboxReadFileTool(BaseTool):
    """沙箱文件读取工具"""

    def __init__(self, sandbox_client: SandboxClient | None = None):
        self.sandbox_client = sandbox_client or get_sandbox_client()
        self.settings = get_settings()

    @property
    def name(self) -> str:
        return "sandbox_read_file"

    @property
    def description(self) -> str:
        return (
            "从沙箱工作区读取指定相对路径文件的文本内容。"
            "支持通过 start_line 和 end_line 进行按行切片读取（1-based）。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "文件相对路径（相对于沙箱工作区根目录）",
                },
                "start_line": {
                    "type": "integer",
                    "description": "可选起始行号（从 1 开始，包含）",
                },
                "end_line": {
                    "type": "integer",
                    "description": "可选结束行号（包含）",
                },
            },
            "required": ["file_path"],
        }

    async def execute(
        self,
        ctx: dict[str, Any],
        file_path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> ToolResult:
        session_id = ctx.get("session_id")

        # 1. 优先使用远程/Docker 独立沙箱
        if self.settings.sandbox_enabled:
            is_alive = await self.sandbox_client.health_check()
            if is_alive:
                res = await self.sandbox_client.read_file(
                    file_path, start_line, end_line, session_id=session_id
                )
                if res.get("is_error", False):
                    return ToolResult(
                        output=f"沙箱读取失败: {res.get('message') or res.get('content')}",
                        is_error=True,
                        metadata={"mode": "docker_sandbox"},
                    )
                return ToolResult(
                    output=res.get("content", ""),
                    is_error=False,
                    metadata={"mode": "docker_sandbox", "total_lines": res.get("total_lines")},
                )
            else:
                logger.warning("sandbox_container_unhealthy_falling_back_to_local")

        # 2. 本地安全回退模式
        workspace_dir = ctx.get("workspace_dir", self.settings.llm_workspace_dir)
        session_id = ctx.get("session_id")
        try:
            target_path = _resolve_safe_local_path(workspace_dir, file_path, session_id=session_id)
            if not target_path.exists():
                return ToolResult(
                    output=f"沙箱错误：文件不存在 [{file_path}]",
                    is_error=True,
                )
            if not target_path.is_file():
                return ToolResult(
                    output=f"沙箱错误：指定路径不是普通文件 [{file_path}]",
                    is_error=True,
                )

            with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            total_lines = len(lines)
            s = max(1, start_line) if start_line is not None else 1
            e = min(total_lines, end_line) if end_line is not None else total_lines

            if s > total_lines:
                return ToolResult(
                    output=f"起始行 {s} 超出文件总行数 {total_lines}",
                    is_error=True,
                )

            selected_lines = lines[s - 1 : e]
            formatted_content = "".join(
                f"{i + s:4d} | {line}" for i, line in enumerate(selected_lines)
            )

            return ToolResult(
                output=formatted_content.rstrip(),
                is_error=False,
                metadata={"total_lines": total_lines, "read_range": [s, e], "mode": "local_fallback"},
            )

        except Exception as e:
            return ToolResult(
                output=f"沙箱读取文件失败: {str(e)}",
                is_error=True,
            )


class SandboxWriteFileTool(BaseTool):
    """沙箱文件写入工具"""

    def __init__(self, sandbox_client: SandboxClient | None = None):
        self.sandbox_client = sandbox_client or get_sandbox_client()
        self.settings = get_settings()

    @property
    def name(self) -> str:
        return "sandbox_write_file"

    @property
    def description(self) -> str:
        return (
            "将内容写入到沙箱工作区的文件中（如 html, py, md, json, txt 等）。"
            "如果目标文件不存在会自动创建父级目录；如果文件已存在将被覆盖写入。"
            "写入成功后会返回该文件的直接 HTTP 在线预览与下载链接。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要写入的文件相对路径（如 report.html, main.py 等）",
                },
                "content": {
                    "type": "string",
                    "description": "文件的完整文本内容",
                },
            },
            "required": ["file_path", "content"],
        }

    async def execute(self, ctx: dict[str, Any], file_path: str, content: str) -> ToolResult:
        session_id = ctx.get("session_id")
        if session_id:
            preview_url = f"{self.settings.sandbox_url.rstrip('/')}/fs/raw?path={file_path}&session_id={session_id}"
        else:
            preview_url = f"{self.settings.sandbox_url.rstrip('/')}/fs/raw?path={file_path}"

        # 1. 优先使用远程/Docker 独立沙箱
        if self.settings.sandbox_enabled:
            is_alive = await self.sandbox_client.health_check()
            if is_alive:
                res = await self.sandbox_client.write_file(
                    file_path, content, session_id=session_id
                )
                if not res.get("success", False):
                    return ToolResult(
                        output=f"沙箱写入失败: {res.get('message')}",
                        is_error=True,
                        metadata={"mode": "docker_sandbox"},
                    )
                return ToolResult(
                    output=(
                        f"文件成功写入沙箱容器 [{file_path}]（共 {len(content)} 字符）。\n"
                        f"在线预览/访问链接: {preview_url}"
                    ),
                    is_error=False,
                    metadata={
                        "file_path": file_path,
                        "bytes": res.get("bytes"),
                        "mode": "docker_sandbox",
                        "preview_url": preview_url,
                    },
                )
            else:
                logger.warning("sandbox_container_unhealthy_falling_back_to_local")

        # 2. 本地安全回退模式
        workspace_dir = ctx.get("workspace_dir", self.settings.llm_workspace_dir)
        session_id = ctx.get("session_id")
        try:
            target_path = _resolve_safe_local_path(workspace_dir, file_path, session_id=session_id)
            target_path.parent.mkdir(parents=True, exist_ok=True)

            with open(target_path, "w", encoding="utf-8") as f:
                f.write(content)

            return ToolResult(
                output=(
                    f"文件成功写入沙箱 [{file_path}]（共 {len(content)} 字符）。\n"
                    f"在线预览/访问链接: {preview_url}"
                ),
                is_error=False,
                metadata={
                    "file_path": file_path,
                    "bytes": len(content.encode("utf-8")),
                    "mode": "local_fallback",
                    "preview_url": preview_url,
                },
            )

        except Exception as e:
            return ToolResult(
                output=f"沙箱写入文件失败: {str(e)}",
                is_error=True,
            )

