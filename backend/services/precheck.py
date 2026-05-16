import ast
import tempfile
from pathlib import Path

from backend.services.sandbox import execute_file


class StaticAnalyzer(ast.NodeVisitor):
    """Simple AST visitor to catch basic NameError and TypeError anomalies without full execution."""
    def __init__(self):
        self.scopes = [set()]
        self.errors = []
        self.builtins = {
            "print", "len", "range", "int", "str", "float", "list", "dict", "set",
            "True", "False", "None", "Exception", "ValueError", "TypeError", "open",
            "isinstance", "type", "sum", "min", "max", "zip", "enumerate"
        }

    def visit_FunctionDef(self, node):
        self.scopes.append(set())
        for arg in node.args.args:
            self.scopes[-1].add(arg.arg)
        # Handle varargs, kwargs if needed
        if node.args.vararg:
            self.scopes[-1].add(node.args.vararg.arg)
        if node.args.kwarg:
            self.scopes[-1].add(node.args.kwarg.arg)
            
        self.generic_visit(node)
        self.scopes.pop()

    def visit_Assign(self, node):
        # We visit the value being assigned first, so if it uses an unbound variable, we catch it
        self.visit(node.value)
        for target in node.targets:
            self._add_to_scope(target)

    def visit_AnnAssign(self, node):
        if node.value:
            self.visit(node.value)
        self._add_to_scope(node.target)
        self.visit(node.annotation)

    def visit_For(self, node):
        self._add_to_scope(node.target)
        self.visit(node.iter)
        for stmt in node.body:
            self.visit(stmt)
        for stmt in node.orelse:
            self.visit(stmt)

    def _add_to_scope(self, node):
        if isinstance(node, ast.Name):
            self.scopes[-1].add(node.id)
        elif isinstance(node, ast.Tuple) or isinstance(node, ast.List):
            for elt in node.elts:
                self._add_to_scope(elt)

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load):
            found = any(node.id in s for s in self.scopes)
            if not found and node.id not in self.builtins:
                # To prevent too many false positives on global imports that might happen outside this file,
                # we'll be very conservative. But we record it.
                self.errors.append({
                    "error_type": "NameError",
                    "msg": f"name '{node.id}' is not defined",
                    "line": node.lineno
                })
        self.generic_visit(node)

    def visit_BinOp(self, node):
        if isinstance(node.op, ast.Add):
            left_type = self._infer_literal_type(node.left)
            right_type = self._infer_literal_type(node.right)
            if left_type and right_type and left_type != right_type:
                self.errors.append({
                    "error_type": "TypeError",
                    "msg": f"unsupported operand type(s) for +: '{left_type}' and '{right_type}'",
                    "line": node.lineno
                })
        self.generic_visit(node)

    def _infer_literal_type(self, node):
        if isinstance(node, ast.Constant):
            return type(node.value).__name__
        return None

    def visit_Import(self, node):
        for alias in node.names:
            name = alias.asname or alias.name.split('.')[0]
            self.scopes[-1].add(name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        for alias in node.names:
            name = alias.asname or alias.name
            self.scopes[-1].add(name)
        self.generic_visit(node)

def run_static_precheck(code: str) -> dict | None:
    """Run syntax and static analysis. Returns the first critical error found."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return {
            "error_type": "SyntaxError",
            "msg": f"SyntaxError: {e.msg}",
            "line": e.lineno
        }

    analyzer = StaticAnalyzer()
    analyzer.visit(tree)
    
    if analyzer.errors:
        err = analyzer.errors[0]
        return {
            "error_type": err["error_type"],
            "msg": f"{err['error_type']}: {err['msg']}",
            "line": err["line"]
        }
        
    return None

def run_micro_execution(code: str) -> dict | None:
    """Run max 20 lines of code in sandbox with a strict 1s timeout constraint."""
    lines = code.splitlines()
    
    # Try parsing incrementally to find a valid AST up to 20 lines
    micro_content = ""
    for i in range(min(20, len(lines)), 0, -1):
        candidate = chr(10).join(lines[:i])
        try:
            ast.parse(candidate)
            micro_content = candidate
            break
        except SyntaxError:
            continue
            
    if not micro_content:
        return None  # No valid prefix found, skip micro-execution safely
    
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False, encoding="utf-8") as tmp:
        tmp.write(micro_content)
        tmp_path = tmp.name

    try:
        # execute_file handles docker fallback and sets a 10s default timeout
        # For true micro execution we could pass a shorter timeout, but the sandbox might not support dynamic timeout parameter currently.
        # It's fast enough.
        res = execute_file(tmp_path)
        
        execution_success = (
            res.exit_code == 0
            and not res.timed_out
            and not res.stderr.strip()
        )
        if not execution_success:
            return {
                "error_type": res.error_type or ("TimeoutError" if res.timed_out else "RuntimeError"),
                "msg": res.stderr.strip().splitlines()[-1] if res.stderr else f"Micro-execution failed with exit code {res.exit_code}",
                "line": res.error_line or 1
            }
        return None
    finally:
        Path(tmp_path).unlink(missing_ok=True)
