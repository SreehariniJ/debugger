from __future__ import annotations

import ast
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any
from functools import lru_cache

_JSON_EXTRACT_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)
_JSON_OBJECT_EXTRACT_RE = re.compile(r"\{.*\}", re.DOTALL)
_CODE_EXTRACT_RE = re.compile(r"```(?:python)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_ANALYSIS_RE = re.compile(r"ANALYSIS:\s*(.*?)\s*EXPLANATION:", re.DOTALL | re.IGNORECASE)
_EXPLANATION_RE = re.compile(r"EXPLANATION:\s*(.*?)\s*STATUS:", re.DOTALL | re.IGNORECASE)
_STATUS_RE = re.compile(r"STATUS:\s*(.*)$", re.DOTALL | re.IGNORECASE)
_ROOT_CAUSE_RE = re.compile(r"ROOT_CAUSE:\s*(.*?)\s*FIXED_CODE:", re.DOTALL | re.IGNORECASE)
_FIXED_CODE_RE = re.compile(r"FIXED_CODE:\s*```(?:python)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)

try:
    from llama_cpp import Llama
except ImportError:  # pragma: no cover - environment dependent
    Llama = None

try:
    import radon.metrics as radon_mi
except ImportError:  # pragma: no cover - environment dependent
    radon_mi = None


from backend.config import (
    MODEL_ANALYSIS_MAX_TOKENS,
    MODEL_BATCH_SIZE,
    MODEL_CONTEXT_TOKENS,
    MODEL_MAX_OUTPUT_TOKENS,
    MODEL_1_5B_PATH,
    MODEL_7B_PATH,
    MODEL_RETRY_ATTEMPTS,
    MODEL_RETRY_TEMPERATURE,
    MODEL_TEMPERATURE,
    MODEL_THREADS,
)


logger = logging.getLogger("offline_debugger.model")


# Force UTF-8 for Windows console support.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class ModelConfigurationError(RuntimeError):
    """Raised when the configured LLM cannot be initialized."""


class ModelInferenceError(RuntimeError):
    """Raised when the LLM call fails or produces unusable output."""


class DebuggingAgents:
    def __init__(self):
        self.llm_1_5b = None
        self.llm_7b = None
        self.initialization_error: str | None = None
        self._lock = threading.Lock()  # llama.cpp is NOT thread-safe
        self._initialize_models()

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

    def _initialize_models(self) -> None:
        if _env_flag("OFFLINE_DEBUGGER_DISABLE_MODEL"):
            self.initialization_error = "Model loading disabled via OFFLINE_DEBUGGER_DISABLE_MODEL."
            logger.error("MODEL FAILED: %s", self.initialization_error)
            return

        if Llama is None:
            self.initialization_error = "llama-cpp-python is not installed."
            logger.error("MODEL FAILED: %s", self.initialization_error)
            return

        for tier, path_val in [("1.5B", MODEL_1_5B_PATH), ("7B", MODEL_7B_PATH)]:
            model_path = Path(path_val).expanduser().resolve()
            if not model_path.exists():
                err = f"Configured model file was not found at {model_path}"
                self.initialization_error = err if not self.initialization_error else self.initialization_error + " " + err
                logger.error("MODEL FAILED (%s): %s", tier, err)
                continue

            try:
                llm_instance = Llama(
                    model_path=str(model_path),
                    n_ctx=MODEL_CONTEXT_TOKENS,
                    n_threads=MODEL_THREADS,
                    n_batch=MODEL_BATCH_SIZE,
                    verbose=False,
                )
                if tier == "1.5B":
                    self.llm_1_5b = llm_instance
                else:
                    self.llm_7b = llm_instance
                logger.info("MODEL LOADED (%s): path=%s threads=%s ctx=%s batch=%s", tier, model_path, MODEL_THREADS, MODEL_CONTEXT_TOKENS, MODEL_BATCH_SIZE)
            except Exception as exc:  # pragma: no cover
                err = f"Failed to initialize {tier} model: {exc}"
                self.initialization_error = err if not self.initialization_error else self.initialization_error + " " + err
                logger.exception("MODEL FAILED (%s): %s", tier, err)
                
        # Warm up models in the background to prevent first-token latency
        import threading
        def _warmup(model_instance):
            if model_instance:
                try:
                    with self._lock:
                        model_instance(" ", max_tokens=1)
                except Exception:
                    pass
        threading.Thread(target=_warmup, args=(self.llm_1_5b,), daemon=True).start()
        threading.Thread(target=_warmup, args=(self.llm_7b,), daemon=True).start()

    def ensure_model_ready(self, model_tier: str = "1.5B") -> 'Llama':
        target = self.llm_7b if model_tier == "7B" else self.llm_1_5b
        fallback = self.llm_1_5b if model_tier == "7B" else self.llm_7b
        
        if target is not None:
            return target
        if fallback is not None:
            logger.warning("Requested %s model unavailable. Falling back to available model.", model_tier)
            return fallback

        raise ModelConfigurationError(self.initialization_error or "All models are unavailable.")

    def _extract_json_payload(self, raw: str) -> dict[str, Any]:
        clean = raw.strip()
        fenced = _JSON_EXTRACT_RE.search(clean)
        if fenced:
            clean = fenced.group(1).strip()
        else:
            object_match = _JSON_OBJECT_EXTRACT_RE.search(clean)
            if object_match:
                clean = object_match.group(0).strip()

        try:
            return json.loads(clean)
        except json.JSONDecodeError as exc:
            raise ModelInferenceError(f"Model returned invalid JSON: {exc}") from exc

    def _extract_code_candidate(self, raw: str) -> str:
        clean = raw.strip()
        fenced = _CODE_EXTRACT_RE.search(clean)
        if fenced:
            clean = fenced.group(1).strip()
        return clean

    @lru_cache(maxsize=256)
    def _ast_signature(self, code_text: str) -> str | None:
        try:
            parsed = ast.parse(code_text)
        except SyntaxError:
            return None
        return ast.dump(parsed, annotate_fields=False, include_attributes=False)

    def _validate_generated_fix(self, original_code: str, candidate_text: str) -> str:
        candidate = self._extract_code_candidate(candidate_text)
        if not candidate.strip():
            raise ModelInferenceError("Model inference failed: generated fix was empty.")
        if candidate.strip() == original_code.strip():
            raise ModelInferenceError("Model inference failed: generated fix matched the original code.")

        try:
            ast.parse(candidate)
        except SyntaxError as exc:
            raise ModelInferenceError(f"Model inference failed: generated fix is invalid Python ({exc}).") from exc

        original_signature = self._ast_signature(original_code)
        candidate_signature = self._ast_signature(candidate)
        if original_signature and candidate_signature and original_signature == candidate_signature:
            raise ModelInferenceError("Model inference failed: generated fix did not change program behavior.")

        return candidate

    def generate_response(
        self,
        prompt: str,
        *,
        max_tokens: int = MODEL_ANALYSIS_MAX_TOKENS,
        temperature: float = MODEL_TEMPERATURE,
        stop: list[str] | None = None,
        repeat_penalty: float = 1.1,
        model_tier: str = "1.5B",
    ) -> str:
        if not hasattr(self, "_llm_cache"):
            self._llm_cache = {}
            
        cache_key = f"{model_tier}:{hash(prompt)}:{temperature}"
        if cache_key in self._llm_cache:
            return self._llm_cache[cache_key]

        llm_instance = self.ensure_model_ready(model_tier)
        logger.info(
            "MODEL CALL STARTED: prompt_chars=%s max_tokens=%s temperature=%s",
            len(prompt),
            max_tokens,
            temperature,
        )
        try:
            with self._lock:
                call_kwargs = {
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "repeat_penalty": repeat_penalty,
                    "echo": False,
                }
                if stop:
                    call_kwargs["stop"] = stop
                output = llm_instance(prompt, **call_kwargs)
            response_text = output["choices"][0]["text"].strip()
        except Exception as exc:  # pragma: no cover - runtime dependent
            logger.exception("MODEL FAILED: %s", exc)
            raise ModelInferenceError(f"Model inference failed: {exc}") from exc

        if not response_text:
            logger.error("MODEL FAILED: empty response received from the model.")
            raise ModelInferenceError("Model inference failed: empty response received from the model.")

        logger.info("MODEL RESPONSE RECEIVED: chars=%s", len(response_text))
        self._llm_cache[cache_key] = response_text
        return response_text

    def multi_agent_pipeline(self, error: str, context: str, knowledge: str, model_tier: str = "7B") -> dict[str, str]:
        """Consolidate analysis/explanation/verification into one LLM call."""
        # Truncate inputs to reduce prompt size and improve inference speed
        truncated_error = error[-1500:] if len(error) > 1500 else error
        truncated_context = context[-3000:] if len(context) > 3000 else context
        truncated_knowledge = (knowledge or "None")[-500:]
        prompt = f"""<|im_start|>system
You are an expert Python debugger.
Given the code, traceback, and supporting notes:
1. Explain the root cause clearly.
2. Provide a concise remediation summary.
3. Respond using exactly these sections and no JSON:
ANALYSIS:
<root cause summary>
EXPLANATION:
<clear fix summary>
STATUS:
<short verdict>
<|im_end|>
<|im_start|>user
Code:
{truncated_context}

Traceback:
{truncated_error}

Supporting Notes:
{truncated_knowledge}
<|im_end|>
<|im_start|>assistant
ANALYSIS:
"""

        last_error: Exception | None = None
        for attempt_index in range(MODEL_RETRY_ATTEMPTS):
            temperature = MODEL_TEMPERATURE if attempt_index == 0 else MODEL_RETRY_TEMPERATURE
            try:
                raw = self.generate_response(
                    prompt,
                    max_tokens=MODEL_ANALYSIS_MAX_TOKENS,
                    temperature=temperature,
                    model_tier=model_tier,
                )
                clean = f"ANALYSIS:\n{raw.strip()}"
                analysis_match = _ANALYSIS_RE.search(clean)
                explanation_match = _EXPLANATION_RE.search(clean)
                status_match = _STATUS_RE.search(clean)
                analysis = analysis_match.group(1).strip() if analysis_match else ""
                explanation = explanation_match.group(1).strip() if explanation_match else ""
                status = status_match.group(1).strip() if status_match else ""
                if not analysis or not explanation or not status:
                    raise ModelInferenceError("Model returned incomplete structured analysis.")
                return {
                    "analysis": analysis,
                    "explanation": explanation,
                    "status": status,
                }
            except (ModelInferenceError, ModelConfigurationError) as exc:
                last_error = exc

        raise ModelInferenceError(f"Model inference failed: {last_error}")

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
        raise ModelInferenceError("Heuristic fallback is disabled. The debugger requires a real model response.")

    @staticmethod
    def strip_unused_imports(code_text: str) -> str:
        """Safely strip totally unused top-level library imports using AST."""
        try:
            tree = ast.parse(code_text)
        except SyntaxError:
            return code_text
            
        used_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                used_names.add(node.id)

        unused_lines = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if all((alias.asname or alias.name.split('.')[0]) not in used_names for alias in node.names):
                    unused_lines.add(node.lineno)
            elif isinstance(node, ast.ImportFrom):
                if getattr(node, "module", "") == "__future__": continue
                if all((alias.asname or alias.name) not in used_names for alias in node.names):
                    unused_lines.add(node.lineno)

        if not unused_lines:
            return code_text
            
        lines = code_text.splitlines()
        for lineno in reversed(sorted(unused_lines)):
            if 1 <= lineno <= len(lines):
                lines.pop(lineno - 1)
                
        return chr(10).join(lines)

    def code_fixer_agent(self, context: str, error: str, attempt: int = 1, model_tier: str = "1.5B") -> str:
        """Rewrite script to fix detected error using guarded prompting."""
        self.ensure_model_ready(model_tier)
        last_error: Exception | None = None

        for retry_index in range(MODEL_RETRY_ATTEMPTS):
            current_attempt = attempt + retry_index
            retry_tip = ""
            if current_attempt > 1:
                retry_tip = (
                    "\nPrevious output was rejected. The next answer must fix the traceback,"
                    " change the program meaningfully, and return executable Python."
                )

            prompt = f"""<|im_start|>system
You are an expert Python debugger.
Given code and traceback:
1. Explain the root cause clearly.
2. Provide corrected code ONLY.
3. Ensure the fix is executable and resolves the error.
Respond using exactly this format:
ROOT_CAUSE:
<short explanation>
FIXED_CODE:
```python
<corrected Python code>
```{retry_tip}
<|im_end|>
<|im_start|>user
Code:
{context[-3000:]}

Traceback:
{error[-1500:]}
<|im_end|>
<|im_start|>assistant
ROOT_CAUSE:
"""

            try:
                raw = self.generate_response(
                    prompt,
                    max_tokens=MODEL_MAX_OUTPUT_TOKENS,
                    temperature=MODEL_TEMPERATURE if current_attempt == 1 else MODEL_RETRY_TEMPERATURE,
                    model_tier=model_tier,
                )
                clean = f"ROOT_CAUSE:\n{raw.strip()}"
                root_cause_match = _ROOT_CAUSE_RE.search(clean)
                code_match = _FIXED_CODE_RE.search(clean)
                root_cause = root_cause_match.group(1).strip() if root_cause_match else ""
                fixed = self._validate_generated_fix(context, code_match.group(1).strip() if code_match else "")
                if not root_cause:
                    raise ModelInferenceError("Model inference failed: missing root cause explanation.")
                return fixed
            except (ModelInferenceError, ModelConfigurationError) as exc:
                last_error = exc

        raise ModelInferenceError(f"Model inference failed: {last_error}")

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
        self.ensure_model_ready()

        relevant_paths = self.researcher_agent(error, context, workspace_files)
        augmented_context = context
        for path in relevant_paths:
            try:
                with open(path, encoding="utf-8", errors="replace") as file_obj:
                    file_content = file_obj.read()[-2000:]  # Limit per-file context
                    augmented_context += f"\n\n# Context from {os.path.basename(path)}:\n" + file_content
            except OSError:
                continue

        best_fix = ""
        last_reason = None
        for attempt in range(1, MODEL_RETRY_ATTEMPTS + 1):
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

        raise ModelInferenceError(
            f"Model inference failed: fix candidate did not pass validation ({last_reason or 'unknown reason'})."
        )

    @lru_cache(maxsize=512)
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

    @lru_cache(maxsize=128)
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

    @lru_cache(maxsize=256)
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
