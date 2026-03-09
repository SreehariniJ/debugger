from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any

try:
    from llama_cpp import Llama
except ImportError:  # pragma: no cover - environment dependent
    Llama = None

try:
    import radon.metrics as radon_mi
except ImportError:  # pragma: no cover - environment dependent
    radon_mi = None


# Force UTF-8 for Windows console support.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class DebuggingAgents:
    def __init__(self, model_path: str = "models/qwen2.5-coder-1.5b-instruct-q4_k_m.gguf"):
        self.model_path = model_path
        self.llm = None
        self._lock = threading.Lock()  # llama.cpp is NOT thread-safe

        if _env_flag("OFFLINE_DEBUGGER_DISABLE_MODEL"):
            print("⚠️ Model loading disabled via OFFLINE_DEBUGGER_DISABLE_MODEL.")
            return

        if Llama is None:
            print("⚠️ llama-cpp-python is not installed. LLM features are disabled.")
            return

        if not os.path.exists(self.model_path):
            print(f"⚠️ Model not found at {self.model_path}")
            return

        n_threads = min(os.cpu_count() or 4, 8)
        try:
            self.llm = Llama(
                model_path=self.model_path,
                n_ctx=2048,
                n_threads=n_threads,
                n_batch=128,
                verbose=False,
            )
            print(f"✅ Model loaded on {n_threads} threads")
        except Exception as exc:  # pragma: no cover - depends on local runtime/GGUF
            self.llm = None
            print(f"⚠️ Failed to initialize model: {exc}")

    def clean_response(self, text: str, start_phrase: str) -> str:
        """Strict filter to keep output concise and parse-safe."""
        if not text:
            return f"{start_phrase} No response generated."

        sentences = text.split(".")
        short_version = ". ".join(sentences[:2])

        for stopper in ["A:", "B:", "Analysis:", "Teacher:", "Explanation:", "This solution"]:
            short_version = short_version.split(stopper)[0]

        clean_text = short_version.strip().replace("..", ".")
        if not clean_text.endswith("."):
            clean_text += "."

        return f"{start_phrase} {clean_text}"

    def generate_response(self, prompt: str) -> str:
        if self.llm is None:
            return "Model unavailable."
        try:
            with self._lock:
                output = self.llm(
                    prompt,
                    max_tokens=80,
                    temperature=0.0,
                    repeat_penalty=1.7,
                    echo=False,
                )
            return output["choices"][0]["text"].strip()
        except Exception as exc:  # pragma: no cover - runtime dependent
            return f"Model error: {exc}"

    def multi_agent_pipeline(self, error: str, context: str, knowledge: str) -> dict[str, str]:
        """Consolidate analysis/explanation/verification into one LLM call."""
        if self.llm is None:
            return {
                "analysis": f"The error is {error}.",
                "explanation": f"Fix: {knowledge}",
                "status": "Verification needed.",
            }

        start_marker = "JSON_START"
        prompt = f"""<|im_start|>system
You are a senior debugging architect. Analyze the error and provide a structured response in JSON.
{start_marker}
{{
  "analysis": "10-word summary of the bug",
  "explanation": "1-sentence fix suggestion",
  "status": "Safe or Unsafe (5 words max)"
}}
<|im_end|>
<|im_start|>user
Code Context: {context}
Error Message: {error}
Local Knowledge: {knowledge}
<|im_end|>
<|im_start|>assistant
{start_marker}
"""
        raw = self.generate_response(prompt)
        try:
            content = raw.split(start_marker)[-1].strip()
            return json.loads(content)
        except Exception:
            return {
                "analysis": self.analyzer_agent(error, context),
                "explanation": self.explainer_agent("Error detected", knowledge),
                "status": "Verification needed.",
            }

    def analyzer_agent(self, error: str, context: str) -> str:
        start = "The error is"
        prompt = (
            f"Code: {context}\n"
            f"Error: {error}\n"
            f"Task: Identify the bug in 10 words or less.\n"
            f"Result: {start}"
        )
        raw = self.generate_response(prompt)
        return self.clean_response(raw, start)

    def explainer_agent(self, analysis: str, knowledge: str) -> str:
        start = "Fix:"
        prompt = f"""
        [STRICT MODE]
        Knowledge: {knowledge}
        Bug: {analysis}
        Constraint: Do not guess variable meanings.
        Task: Provide a 1-sentence fix.
        Result: {start}"""
        raw = self.generate_response(prompt)
        return self.clean_response(raw, start)

    def verifier_agent(self, explanation: str) -> str:
        start = "Status:"
        prompt = f"Fix: {explanation}\nTask: Is this safe? Answer in 5 words.\nResult: {start}"
        raw = self.generate_response(prompt)
        return self.clean_response(raw, start)

    def _heuristic_fallback_fix(self, context: str, error: str) -> str:
        if "ZeroDivisionError" in error and "result = num / denom" in context:
            return context.replace(
                "result = num / denom",
                (
                    "if denom != 0:\n"
                    "    result = num / denom\n"
                    "else:\n"
                    "    result = 0\n"
                    "    print('Handled zero denominator safely')"
                ),
            )
        return (
            "# Auto-fix skipped: model unavailable or low-confidence generation.\n"
            "# Original code is preserved below.\n"
            f"{context}"
        )

    def code_fixer_agent(self, context: str, error: str, attempt: int = 1) -> str:
        """Rewrite script to fix detected error using guarded prompting."""
        if self.llm is None:
            return self._heuristic_fallback_fix(context, error)

        retry_tip = ""
        if attempt > 1:
            retry_tip = (
                "\n[CRITIC FEEDBACK] Previous fix failed validation."
                " Simplify logic and avoid security risks."
            )

        prompt = f"""<|im_start|>system
You are an expert Python developer. Fix the bug with minimal, safe edits.
1. Identify the crashing line.
2. Apply the smallest valid correction.
3. Keep behavior intact unless required for safety.{retry_tip}
Return ONLY corrected code inside a ```python block.<|im_end|>
<|im_start|>user
Buggy Code:
{context}

Error:
{error}

Fixed Code:<|im_end|>
<|im_start|>assistant
```python"""

        try:
            with self._lock:
                output = self.llm(
                    prompt,
                    max_tokens=1024,
                    temperature=0.01 if attempt == 1 else 0.4,
                    stop=["<|im_end|>", "```"],
                    echo=False,
                )
            fixed = output["choices"][0]["text"].strip()
        except Exception:
            return self._heuristic_fallback_fix(context, error)

        if len(fixed) < 10 or fixed.strip() == context.strip():
            return self._heuristic_fallback_fix(context, error)
        return fixed

    def researcher_agent(self, error: str, context: str, workspace_files: list[dict[str, Any]]) -> list[str]:
        """Identify relevant files based on imports/error keywords."""
        relevant_files: list[str] = []
        try:
            tree = ast.parse(context)
            imports: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for import_node in node.names:
                        if isinstance(import_node.name, str):
                            imports.append(import_node.name)
                elif isinstance(node, ast.ImportFrom) and isinstance(node.module, str):
                    imports.append(node.module)

            for file_info in workspace_files:
                path = file_info.get("path")
                name = file_info.get("name", "")
                if not isinstance(path, str) or not isinstance(name, str):
                    continue

                module_name = name.replace(".py", "")
                if any(imp and module_name in imp for imp in imports):
                    relevant_files.append(path)
                elif any(word in error.lower() for word in module_name.lower().split("_")):
                    relevant_files.append(path)
        except Exception:
            return []

        return list(set(relevant_files))[:2]

    def critic_agent(self, original_code: str, proposed_fix: str) -> dict[str, Any]:
        """Validate proposed fix for syntax, complexity, and security."""
        try:
            ast.parse(proposed_fix)
        except SyntaxError:
            return {"valid": False, "reason": "Syntax error in proposed fix."}

        complexity = self.complexity_agent(proposed_fix)
        orig_complexity = self.complexity_agent(original_code)
        security = self.security_audit_agent(proposed_fix)
        critical_vulnerabilities = [v for v in security.get("issues", []) if v.get("risk") == "CRITICAL"]

        if critical_vulnerabilities:
            return {
                "valid": False,
                "reason": f"Fix introduced critical vulnerability: {critical_vulnerabilities[0]['type']}",
            }
        if complexity["complexity_score"] > 25 and complexity["complexity_score"] > orig_complexity["complexity_score"]:
            return {"valid": False, "reason": "Fix drastically increased code complexity (Cyclomatic > 25)."}

        return {"valid": True, "metrics": {"complexity": complexity, "security": security}}

    async def viper_orchestration(
        self, error: str, context: str, workspace_files: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Orchestrated multi-agent loop with research and critique."""
        if self.llm is None:
            return {
                "success": False,
                "fix": "",
                "reason": "LLM unavailable; orchestration skipped.",
                "path_taken": "LLM unavailable fallback",
            }

        relevant_paths = self.researcher_agent(error, context, workspace_files)
        augmented_context = context
        for path in relevant_paths:
            try:
                with open(path, encoding="utf-8", errors="replace") as file_obj:
                    augmented_context += f"\n\n# Context from {os.path.basename(path)}:\n" + file_obj.read()
            except OSError:
                continue

        best_fix = ""
        last_reason = None
        for attempt in range(1, 3):
            candidate = self.code_fixer_agent(augmented_context, error, attempt)
            report = self.critic_agent(context, candidate)
            if report["valid"]:
                return {
                    "success": True,
                    "fix": candidate,
                    "metrics": report["metrics"],
                    "path_taken": f"Orchestrated fix successful on attempt {attempt}",
                }
            last_reason = report["reason"]
            best_fix = candidate

        return {
            "success": False,
            "fix": best_fix,
            "reason": f"Fix candidate failed validation: {last_reason}",
            "path_taken": "Viper fallback (no valid fix found within constraints)",
        }

    def severity_agent(self, error: str) -> str:
        error_lower = error.lower()
        if any(
            token in error_lower
            for token in ["segfault", "memoryerror", "zerodivision", "systemerror", "recursionerror", "timeout"]
        ):
            return "CRITICAL"
        if any(
            token in error_lower
            for token in ["typeerror", "valueerror", "indexerror", "keyerror", "attributeerror", "nameerror"]
        ):
            return "WARNING"
        return "INFO"

    def complexity_agent(self, code_text: str) -> dict[str, Any]:
        """AST-based cyclomatic complexity analysis with summary metrics."""
        try:
            tree = ast.parse(code_text)
        except SyntaxError:
            return {
                "functions": 0,
                "classes": 0,
                "loops": 0,
                "conditions": 0,
                "complexity_score": 0,
                "grade": "F",
                "loc": 0,
                "comments": 0,
                "top_complex": "N/A",
                "mi_score": None,
                "mi_grade": None,
            }

        functions = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        classes = sum(1 for n in ast.walk(tree) if isinstance(n, ast.ClassDef))
        loops = sum(1 for n in ast.walk(tree) if isinstance(n, (ast.For, ast.While, ast.AsyncFor)))
        conditions = sum(1 for n in ast.walk(tree) if isinstance(n, (ast.If, ast.Compare, ast.BoolOp)))
        complexity_score = len(functions) + loops + conditions

        lines = code_text.splitlines()
        loc = len([line for line in lines if line.strip()])
        comments = len([line for line in lines if line.strip().startswith("#")])

        top_complex = "N/A"
        if functions:
            def count_complexity(node: ast.AST) -> int:
                return sum(
                    1 for item in ast.walk(node) if isinstance(item, (ast.For, ast.While, ast.If, ast.Compare, ast.BoolOp))
                )

            scored_functions = [(func.name, count_complexity(func)) for func in functions]
            top_complex = max(scored_functions, key=lambda entry: entry[1])[0]

        grade = "A"
        if complexity_score > 30:
            grade = "F"
        elif complexity_score > 20:
            grade = "D"
        elif complexity_score > 10:
            grade = "C"
        elif complexity_score > 5:
            grade = "B"

        radon_data = self.complexity_radon_metrics(code_text)

        return {
            "functions": len(functions),
            "classes": classes,
            "loops": loops,
            "conditions": conditions,
            "complexity_score": complexity_score,
            "grade": grade,
            "loc": loc,
            "comments": comments,
            "top_complex": top_complex,
            "mi_score": radon_data.get("mi_score") if radon_data else None,
            "mi_grade": radon_data.get("mi_grade") if radon_data else None,
        }

    def complexity_radon_metrics(self, code_text: str) -> dict[str, Any] | None:
        """Advanced maintainability metrics using Radon, if installed."""
        if radon_mi is None:
            return None
        try:
            mi_score = radon_mi.mi_visit(code_text, multi=True)
            return {
                "mi_score": round(mi_score, 2),
                "mi_grade": "A" if mi_score > 40 else ("B" if mi_score > 20 else "C"),
            }
        except Exception:
            return None

    def security_bandit_agent(self, code_text: str) -> list[dict[str, Any]]:
        """Run Bandit if installed; return findings in normalized format."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as tmp:
            tmp.write(code_text)
            tmp_path = tmp.name

        try:
            result = subprocess.run(
                ["bandit", "-f", "json", "-q", tmp_path],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if not result.stdout.strip():
                return []

            data = json.loads(result.stdout)
            issues: list[dict[str, Any]] = []
            for issue in data.get("results", []):
                issues.append(
                    {
                        "type": issue.get("issue_text"),
                        "risk": issue.get("issue_severity"),
                        "desc": f"{issue.get('issue_text')} (Confidence: {issue.get('issue_confidence')})",
                        "line": issue.get("line_number"),
                    }
                )
            return issues
        except Exception:
            return []
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    def security_audit_agent(self, code_text: str) -> dict[str, Any]:
        """Audit code for common security vulnerabilities."""
        vulnerabilities: list[dict[str, Any]] = []
        lower_text = code_text.lower()

        if "os.system(" in code_text or ("subprocess" in lower_text and "shell=true" in lower_text):
            vulnerabilities.append(
                {
                    "type": "Injection",
                    "risk": "CRITICAL",
                    "desc": "Execution of OS commands with potentially unsafe input.",
                }
            )
        if any(token in lower_text for token in ["api_key =", "secret =", "password =", "token ="]):
            vulnerabilities.append(
                {"type": "Exposure", "risk": "HIGH", "desc": "Potential hardcoded credentials detected."}
            )
        if "yaml.load(" in code_text and "SafeLoader" not in code_text:
            vulnerabilities.append(
                {
                    "type": "Deserialization",
                    "risk": "HIGH",
                    "desc": "Insecure YAML loading can lead to code execution.",
                }
            )
        if "eval(" in code_text or "exec(" in code_text:
            vulnerabilities.append(
                {
                    "type": "Arbitrary Code Execution",
                    "risk": "CRITICAL",
                    "desc": "Use of eval()/exec() with untrusted data.",
                }
            )

        bandit_issues = self.security_bandit_agent(code_text)
        if bandit_issues:
            vulnerabilities.extend(bandit_issues)

        return {
            "count": len(vulnerabilities),
            "issues": vulnerabilities,
            "is_secure": len(vulnerabilities) == 0,
            "audit_timestamp": time.time(),
            "engine": "Bandit + Custom Heuristics",
        }

    def confidence_agent(self, error: str, analysis: str, fixed_code: str | None) -> int:
        """Score fix confidence 1-10 using stable heuristics."""
        score = 7
        known_errors = {
            "nameerror",
            "typeerror",
            "valueerror",
            "zerodivisionerror",
            "indexerror",
            "keyerror",
            "syntaxerror",
            "attributeerror",
        }

        error_lower = error.lower()
        analysis_lower = analysis.lower() if analysis else ""
        fixed_text = fixed_code or ""

        if any(token in error_lower for token in known_errors):
            score += 2
        if len(fixed_text.strip()) < 20:
            score -= 4
        if "pass" in fixed_text or "TODO" in fixed_text:
            score -= 2
        if any(token in analysis_lower for token in known_errors):
            score += 1

        return max(1, min(10, score))
