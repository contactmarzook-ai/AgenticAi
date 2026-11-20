"""Arithmetic without eval(): only numbers and + - * / // % ** are allowed."""

import ast
import operator

_OPS = {
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


class EvalError(ValueError):
    pass


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > 100:
            raise EvalError("Exponent too large")
        return _OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise EvalError("Only numbers and + - * / // % ** are allowed")


def calculate(expression: str):
    if len(expression) > 500:
        raise EvalError("Formula too long")
    try:
        tree = ast.parse(expression.replace(",", ""), mode="eval")
    except SyntaxError as exc:
        raise EvalError("Invalid formula") from exc
    try:
        return _eval(tree)
    except ZeroDivisionError as exc:
        raise EvalError("Division by zero") from exc
