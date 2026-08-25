import math
from typing import Any
from datetime import datetime, timezone
from .base import BaseTool, ToolResult


class CalculatorTool(BaseTool):
    """纯内存计算工具：用于精确数学运算与表达式求值"""

    @property
    def name(self) -> str:
        return "calculator"

    @property
    def description(self) -> str:
        return (
            "执行基础数学表达式计算（如加减乘除、幂运算、对数、三角函数等）。"
            "输入合法的 Python 数学表达式，如 '2**10 + 15 * 4' 或 'math.sqrt(144)'。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "要计算的数学表达式字符串",
                },
            },
            "required": ["expression"],
        }

    async def execute(self, ctx: dict[str, Any], expression: str) -> ToolResult:
        try:
            # 安全受限的环境命名空间
            safe_globals = {
                "math": math,
                "abs": abs,
                "round": round,
                "min": min,
                "max": max,
                "sum": sum,
                "pow": pow,
            }
            # 禁止内置危险函数
            safe_locals: dict[str, Any] = {}
            result = eval(expression, {"__builtins__": {}}, {**safe_globals, **safe_locals})
            return ToolResult(
                output=f"计算结果: {result}",
                is_error=False,
                metadata={"expression": expression, "result": result},
            )
        except Exception as e:
            return ToolResult(
                output=f"计算错误: {str(e)}",
                is_error=True,
            )


class CurrentTimeTool(BaseTool):
    """纯内存时间工具：获取当前标准时间"""

    @property
    def name(self) -> str:
        return "get_current_time"

    @property
    def description(self) -> str:
        return "获取当前的精确 UTC 时间与本地格式化时间。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
        }

    async def execute(self, ctx: dict[str, Any], **kwargs: Any) -> ToolResult:
        now_utc = datetime.now(timezone.utc)
        return ToolResult(
            output=f"当前时间: {now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}",
            is_error=False,
            metadata={"timestamp": now_utc.timestamp()},
        )


class FetchWebpageTool(BaseTool):
    """网页抓取与阅读工具：基于 Jina Reader (https://r.jina.ai/{url}) 将任意网页转换为清晰的 Markdown 结构"""

    @property
    def name(self) -> str:
        return "fetch_webpage"

    @property
    def description(self) -> str:
        return (
            "通过 Jina Reader API 读取并解析指定公开网页 URL 的完整内容，转换为干净结构化的 Markdown 文本。"
            "适用于阅读新闻、技术文档、维基百科、博客文章、GitHub 页面等。输入以 http:// 或 https:// 开头的完整网址。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要读取的网页完整 URL 地址（例如 'https://news.ycombinator.com'）",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "可选最大返回字符数，默认 8000 字符",
                },
            },
            "required": ["url"],
        }

    async def execute(self, ctx: dict[str, Any], url: str, max_chars: int = 8000) -> ToolResult:
        import httpx

        target_url = url.strip()
        if not target_url.startswith("http://") and not target_url.startswith("https://"):
            target_url = f"https://{target_url}"

        jina_url = f"https://r.jina.ai/{target_url}"

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                headers = {
                    "User-Agent": "Antigravity-Agent/1.0",
                    "Accept": "text/markdown, text/plain",
                    "X-No-Cache": "true",
                }
                res = await client.get(jina_url, headers=headers)

                if res.status_code != 200:
                    return ToolResult(
                        output=f"抓取网页失败 (HTTP {res.status_code}): {res.text[:500]}",
                        is_error=True,
                        metadata={"url": url, "status_code": res.status_code},
                    )

                content = res.text

                # 过滤 Jina Reader 附带的非致命 Warning 提示行，防止干扰 LLM 判断
                cleaned_lines = [
                    line for line in content.split("\n")
                    if not line.strip().startswith("Warning:")
                ]
                content = "\n".join(cleaned_lines).strip()

                is_truncated = False
                total_len = len(content)

                if total_len > max_chars:
                    content = (
                        content[:max_chars]
                        + f"\n\n... [网页内容过长已自动截断，展示前 {max_chars} 字符 / 共 {total_len} 字符] ..."
                    )
                    is_truncated = True

                return ToolResult(
                    output=content,
                    is_error=False,
                    metadata={
                        "url": url,
                        "jina_url": jina_url,
                        "total_length": total_len,
                        "is_truncated": is_truncated,
                    },
                )
        except Exception as e:
            return ToolResult(
                output=f"请求 Jina Reader 抓取网页发生异常: {str(e)}",
                is_error=True,
                metadata={"url": url, "error": str(e)},
            )

