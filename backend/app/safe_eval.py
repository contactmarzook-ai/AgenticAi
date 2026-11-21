"""Arithmetic without eval(): only numbers and + - * / // % ** are allowed."""

import ast
import math
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


MAX_NODES = 60  # operators + numbers in one formula
MAX_BITS = 4096  # largest integer allowed at any point (~1,233 digits)


def _check_size(value):
    if isinstance(value, int) and value.bit_length() > MAX_BITS:
        raise EvalError("Number too large")
    if isinstance(value, float) and (math.isinf(value) or math.isnan(value)):
        raise EvalError("Number too large")
    return value


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return _check_size(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        left, right = _eval(node.left), _eval(node.right)
        # Refuse operations whose result would be huge *before* computing them: big-integer
        # arithmetic holds the interpreter lock and could freeze the whole server.
        if isinstance(node.op, ast.Pow):
            if abs(right) > 100:
                raise EvalError("Exponent too large")
            if isinstance(left, int) and isinstance(right, int) and right > 0 and left.bit_length() * right > MAX_BITS:
                raise EvalError("Number too large")
        if isinstance(node.op, ast.Mult) and isinstance(left, int) and isinstance(right, int):
            if left.bit_length() + right.bit_length() > MAX_BITS:
                raise EvalError("Number too large")
        try:
            return _check_size(_OPS[type(node.op)](left, right))
        except OverflowError as exc:
            raise EvalError("Number too large") from exc
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _check_size(_OPS[type(node.op)](_eval(node.operand)))
    raise EvalError("Only numbers and + - * / // % ** are allowed")


def calculate(expression: str):
    if len(expression) > 500:
        raise EvalError("Formula too long")
    try:
        tree = ast.parse(expression.replace(",", ""), mode="eval")
    except (SyntaxError, ValueError) as exc:  # ValueError: integer literal with too many digits
        raise EvalError("Invalid formula") from exc
    if sum(1 for _ in ast.walk(tree)) > MAX_NODES * 2:
        raise EvalError("Formula too complex")
    try:
        return _eval(tree)
    except ZeroDivisionError as exc:
        raise EvalError("Division by zero") from exc
