import ast
import datetime
import math
import operator
import re
from typing import Any
import httpx
from .base import BaseTool, ToolResult


class CalculatorTool(BaseTool):
    """安全数学表达式计算工具"""

    _SAFE_OPERATORS = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    _SAFE_FUNCTIONS = {
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "sqrt": math.sqrt,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "log": math.log,
        "log10": math.log10,
        "log2": math.log2,
        "exp": math.exp,
        "floor": math.floor,
        "ceil": math.ceil,
        "pi": math.pi,
        "e": math.e,
    }

    @property
    def name(self) -> str:
        return "calculator"

    @property
    def description(self) -> str:
        return (
            "执行精确数学表达式计算（如加减乘除、幂运算、对数、三角函数等）。"
            "输入合法的 Python 数学表达式，如 '2**10 + 15 * 4' 或 'sqrt(144)'。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "要计算的数学表达式字符串，例如 '123456 * 654321'",
                }
            },
            "required": ["expression"],
        }

    def _eval_node(self, node: ast.AST) -> float | int:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"不支持的常量类型: {type(node.value)}")
        elif isinstance(node, ast.BinOp):
            left = self._eval_node(node.left)
            right = self._eval_node(node.right)
            op_func = self._SAFE_OPERATORS.get(type(node.op))
            if op_func is None:
                raise ValueError(f"不支持的运算符: {type(node.op)}")
            return op_func(left, right)
        elif isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand)
            op_func = self._SAFE_OPERATORS.get(type(node.op))
            if op_func is None:
                raise ValueError(f"不支持的一元运算符: {type(node.op)}")
            return op_func(operand)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
                func = self._SAFE_FUNCTIONS.get(func_name)
                if func is None:
                    raise ValueError(f"不支持的数学函数: {func_name}")
                args = [self._eval_node(arg) for arg in node.args]
                return func(*args)
            elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                if node.func.value.id == "math":
                    func_name = node.func.attr
                    func = self._SAFE_FUNCTIONS.get(func_name)
                    if func is None:
                        raise ValueError(f"不支持的 math 函数: {func_name}")
                    args = [self._eval_node(arg) for arg in node.args]
                    return func(*args)
            raise ValueError("不支持的复杂函数调用")
        elif isinstance(node, ast.Name):
            val = self._SAFE_FUNCTIONS.get(node.id)
            if isinstance(val, (int, float)):
                return val
            raise ValueError(f"未知的常量/变量名: {node.id}")
        else:
            raise ValueError(f"不支持的语法节点: {type(node)}")

    async def execute(self, ctx: dict[str, Any], **kwargs: Any) -> ToolResult:
        expression = kwargs.get("expression", "")
        if not expression:
            return ToolResult(output="计算表达式不能为空", is_error=True)

        cleaned = expression.strip()
        cleaned = re.sub(r"\s+", "", cleaned)

        try:
            tree = ast.parse(cleaned, mode="eval")
            result = self._eval_node(tree.body)
            if isinstance(result, float) and result.is_integer():
                result = int(result)
            return ToolResult(output=str(result), metadata={"expression": expression, "result": result})
        except Exception as e:
            return ToolResult(output=f"表达式计算错误: {str(e)}", is_error=True)


class CurrentTimeTool(BaseTool):
    """当前精确时间获取工具"""

    @property
    def name(self) -> str:
        return "get_current_time"

    @property
    def description(self) -> str:
        return "获取当前的精确 UTC 时间与本地格式化时间。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, ctx: dict[str, Any], **kwargs: Any) -> ToolResult:
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        now_local = datetime.datetime.now()
        output = (
            f"当前 UTC 时间: {now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            f"当前系统时间: {now_local.strftime('%Y-%m-%d %H:%M:%S')}"
        )
        return ToolResult(output=output)


class FetchWebpageTool(BaseTool):
    """网页内容读取工具"""

    @property
    def name(self) -> str:
        return "fetch_webpage"

    @property
    def description(self) -> str:
        return "通过 Jina Reader API 读取并解析指定网页 URL 的完整 Markdown 内容。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "要读取的公开网页 URL 地址"}
            },
            "required": ["url"],
        }

    async def execute(self, ctx: dict[str, Any], **kwargs: Any) -> ToolResult:
        url = kwargs.get("url", "")
        if not url:
            return ToolResult(output="URL 不能为空", is_error=True)
        jina_url = f"https://r.jina.ai/{url}"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(jina_url)
                if resp.status_code == 200:
                    text = resp.text[:8000]
                    return ToolResult(output=text, metadata={"url": url, "truncated": len(resp.text) > 8000})
                return ToolResult(output=f"网页读取失败 (状态码 {resp.status_code})", is_error=True)
        except Exception as e:
            return ToolResult(output=f"网络请求异常: {str(e)}", is_error=True)
