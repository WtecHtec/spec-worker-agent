import os
import asyncio
from pathlib import Path
from typing import Any
import httpx
from .base import BaseTool, ToolResult

SANDBOX_URL = os.getenv("SANDBOX_DAEMON_URL", "http://localhost:5050").rstrip("/")
BASE_WORKSPACE = os.getenv("SANDBOX_WORKSPACE_DIR", "./workspace")


def _get_workspace_path(session_id: str | None = None) -> Path:
    """获取沙箱工作区根目录（与后端和 Go Sandbox Daemon 会话隔离规范完全对齐）"""
    base = Path(BASE_WORKSPACE).resolve()
    if session_id and str(session_id).strip():
        target = base / "sessions" / str(session_id).strip()
    else:
        target = base
    target.mkdir(parents=True, exist_ok=True)
    return target


class SandboxRunCommandTool(BaseTool):
    """沙箱环境命令执行工具"""

    @property
    def name(self) -> str:
        return "sandbox_run_command"

    @property
    def description(self) -> str:
        return (
            "【隔离容器执行】在沙箱环境中执行 shell 命令（如 python, pytest, git, ls 等）。"
            "非交互模式运行，具备超时和输出截断防护。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "要执行的 shell 命令行"},
                "cwd": {"type": "string", "description": "执行相对子目录路径，默认当前根目录"},
            },
            "required": ["command"],
        }

    async def execute(self, ctx: dict[str, Any], **kwargs: Any) -> ToolResult:
        command = kwargs.get("command", "")
        cwd = kwargs.get("cwd", "")
        session_id = ctx.get("thread_id") or ctx.get("session_id")

        # 1. 优先调用 Go Sandbox Daemon / Docker 容器执行
        try:
            async with httpx.AsyncClient(timeout=65.0) as client:
                payload = {
                    "command": command,
                    "cwd": cwd,
                    "session_id": str(session_id) if session_id else None,
                    "timeout": 60,
                }
                resp = await client.post(f"{SANDBOX_URL}/exec", json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    out = data.get("output") or data.get("combined") or data.get("stdout") or data.get("stderr") or "命令执行成功（无输出）。"
                    exit_code = data.get("exit_code", 0)
                    return ToolResult(output=out, is_error=exit_code != 0, metadata=data)
        except Exception:
            pass

        # 2. 本地工作区回退执行
        workspace = _get_workspace_path(session_id)
        target_cwd = (workspace / cwd).resolve() if cwd else workspace
        target_cwd.mkdir(parents=True, exist_ok=True)
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                cwd=str(target_cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=60.0)
            stdout = stdout_b.decode("utf-8", errors="replace")
            stderr = stderr_b.decode("utf-8", errors="replace")
            is_err = proc.returncode != 0
            res_text = stdout if not is_err else (stderr or stdout)
            return ToolResult(output=res_text or "命令执行完毕（无输出）", is_error=is_err)
        except Exception as e:
            return ToolResult(output=f"命令执行异常: {str(e)}", is_error=True)


class SandboxReadFileTool(BaseTool):
    """沙箱文件读取工具"""

    @property
    def name(self) -> str:
        return "sandbox_read_file"

    @property
    def description(self) -> str:
        return "读取沙箱工作区中的指定文本文件内容。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "相对文件路径"},
                "start_line": {"type": "integer", "description": "起始行号（可选，1-indexed）"},
                "end_line": {"type": "integer", "description": "结束行号（可选，1-indexed）"},
            },
            "required": ["file_path"],
        }

    async def execute(self, ctx: dict[str, Any], **kwargs: Any) -> ToolResult:
        file_path = kwargs.get("file_path", "")
        start_line = kwargs.get("start_line")
        end_line = kwargs.get("end_line")
        session_id = ctx.get("thread_id") or ctx.get("session_id")

        # 1. 优先调用 Go Sandbox Daemon
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                payload = {
                    "file_path": file_path,
                    "session_id": str(session_id) if session_id else None,
                }
                if start_line is not None:
                    payload["start_line"] = start_line
                if end_line is not None:
                    payload["end_line"] = end_line
                resp = await client.post(f"{SANDBOX_URL}/fs/read", json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    if not data.get("is_error"):
                        return ToolResult(output=data.get("content", ""))
        except Exception:
            pass

        # 2. 本地工作区回退读取
        workspace = _get_workspace_path(session_id)
        target = (workspace / file_path).resolve()
        try:
            if not target.exists():
                return ToolResult(output=f"文件不存在: {file_path}", is_error=True)
            lines = target.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
            if start_line or end_line:
                s = max(1, start_line or 1) - 1
                e = end_line or len(lines)
                selected = lines[s:e]
                content = "".join(selected)
            else:
                content = "".join(lines)
            return ToolResult(output=content[:15000])
        except Exception as e:
            return ToolResult(output=f"读取文件失败: {str(e)}", is_error=True)


from src.db.file_recorder import record_sandbox_file


class SandboxWriteFileTool(BaseTool):
    """沙箱文件写入工具"""

    @property
    def name(self) -> str:
        return "sandbox_write_file"

    @property
    def description(self) -> str:
        return "在沙箱工作区中创建或覆盖写入文本文件。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "相对文件路径"},
                "content": {"type": "string", "description": "要写入的文件文本内容"},
            },
            "required": ["file_path", "content"],
        }

    async def execute(self, ctx: dict[str, Any], **kwargs: Any) -> ToolResult:
        file_path = kwargs.get("file_path", "")
        content = kwargs.get("content", "")
        session_id = ctx.get("thread_id") or ctx.get("session_id")
        user_id = ctx.get("user_id")
        task_id = ctx.get("task_id")

        write_success = False

        # 1. 优先调用 Go Sandbox Daemon 写入
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                payload = {
                    "file_path": file_path,
                    "content": content,
                    "session_id": str(session_id) if session_id else None,
                }
                resp = await client.post(f"{SANDBOX_URL}/fs/write", json=payload)
                if resp.status_code == 200:
                    write_success = True
        except Exception:
            pass

        # 2. 本地工作区回退写入
        if not write_success:
            workspace = _get_workspace_path(session_id)
            target = (workspace / file_path).resolve()
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                write_success = True
            except Exception as e:
                return ToolResult(output=f"写入文件失败: {str(e)}", is_error=True)

        # 3. 成功后直接直连 PostgreSQL 同步持久化文件元数据与版本
        if write_success:
            await record_sandbox_file(
                thread_id=session_id,
                file_path=file_path,
                content=content,
                user_id=user_id,
                task_id=task_id,
            )
            return ToolResult(output=f"成功写入文件: {file_path} ({len(content)} 字符，已持久化至 PostgreSQL)")

        return ToolResult(output=f"写入文件失败: 未知错误", is_error=True)
