"""
semantic_index — TF-IDF / BM25 semantic retrieval over knowledge documents.

Replaces the simple keyword-matching in the original ``LocalRAGEngine``
with a proper information retrieval pipeline.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class KnowledgeDocument:
    doc_id: str
    title: str
    content: str
    source: str
    tags: list[str] = field(default_factory=list)
    tokens: list[str] = field(default_factory=list)


@dataclass
class RetrievalResult:
    doc_id: str
    title: str
    content: str
    score: float
    source: str


class SemanticIndex:
    """
    BM25-based semantic retrieval engine for debugging knowledge.

    BM25 parameters:
        k1 = 1.5 (term frequency saturation)
        b  = 0.75 (document length normalization)
    """

    K1 = 1.5
    B = 0.75

    def __init__(self, data_dir: str = "knowledge_base"):
        self.data_dir = data_dir
        self._documents: list[KnowledgeDocument] = []
        self._idf: dict[str, float] = {}
        self._avg_dl: float = 0.0
        self._built = False

    def load_and_index(self, base_path: str | None = None) -> int:
        """Load all knowledge documents and build the BM25 index."""
        root = Path(base_path) if base_path else Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        kb_dir = root / self.data_dir

        self._documents.clear()

        # Load kb.json
        kb_path = kb_dir / "kb.json"
        if kb_path.exists():
            self._load_kb_json(kb_path)

        # Load pylint_knowledge.json
        pylint_path = kb_dir / "pylint_knowledge.json"
        if pylint_path.exists():
            self._load_pylint_json(pylint_path)

        # Load any .md or .txt files in the knowledge base
        for f in kb_dir.glob("*.md"):
            self._load_text_file(f)
        for f in kb_dir.glob("*.txt"):
            self._load_text_file(f)

        # Load playbooks
        playbooks_dir = kb_dir / "playbooks"
        if playbooks_dir.exists():
            for f in playbooks_dir.glob("*.json"):
                self._load_playbook_file(f)

        # Build the BM25 index
        self._build_index()
        return len(self._documents)

    def query(self, query_text: str, top_k: int = 5) -> list[RetrievalResult]:
        """Retrieve the top-k most relevant documents for a query."""
        if not self._built or not self._documents:
            return []

        query_tokens = self._tokenize(query_text)
        if not query_tokens:
            return []

        scores: list[tuple[int, float]] = []

        for i, doc in enumerate(self._documents):
            score = self._bm25_score(query_tokens, doc)
            if score > 0:
                scores.append((i, score))

        scores.sort(key=lambda x: x[1], reverse=True)

        results: list[RetrievalResult] = []
        for idx, score in scores[:top_k]:
            doc = self._documents[idx]
            results.append(RetrievalResult(
                doc_id=doc.doc_id,
                title=doc.title,
                content=doc.content,
                score=round(score, 4),
                source=doc.source,
            ))

        return results

    def query_text(self, query_text: str, top_k: int = 3) -> str:
        """Return concatenated text of top results (drop-in replacement for old query_docs)."""
        results = self.query(query_text, top_k=top_k)
        if not results:
            return "No relevant knowledge found."
        return "\n\n".join(
            f"[{r.source}] {r.title}: {r.content}" for r in results
        )

    # --- Index construction ---

    def _build_index(self) -> None:
        if not self._documents:
            self._built = True
            return

        # Tokenize all documents
        for doc in self._documents:
            doc.tokens = self._tokenize(doc.content + " " + doc.title)

        # Compute average document length
        total_tokens = sum(len(doc.tokens) for doc in self._documents)
        self._avg_dl = total_tokens / len(self._documents) if self._documents else 1.0

        # Compute IDF for all terms
        n = len(self._documents)
        df: Counter[str] = Counter()
        for doc in self._documents:
            unique_terms = set(doc.tokens)
            for term in unique_terms:
                df[term] += 1

        self._idf = {}
        for term, doc_freq in df.items():
            self._idf[term] = math.log((n - doc_freq + 0.5) / (doc_freq + 0.5) + 1)

        self._built = True

    def _bm25_score(self, query_tokens: list[str], doc: KnowledgeDocument) -> float:
        score = 0.0
        dl = len(doc.tokens)
        tf_map = Counter(doc.tokens)

        for token in query_tokens:
            if token not in self._idf:
                continue
            tf = tf_map.get(token, 0)
            idf = self._idf[token]
            numerator = tf * (self.K1 + 1)
            denominator = tf + self.K1 * (1 - self.B + self.B * dl / self._avg_dl)
            score += idf * (numerator / denominator)

        return score

    # --- Document loaders ---

    def _load_kb_json(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for section in ["core", "secondary"]:
                entries = data.get(section, {})
                for err_name, details in entries.items():
                    explanation = details.get("explanation", "")
                    suggestion = details.get("suggestion", "")
                    self._documents.append(KnowledgeDocument(
                        doc_id=f"kb:{err_name}",
                        title=err_name,
                        content=f"{explanation} Suggestion: {suggestion}",
                        source="kb.json",
                        tags=[err_name.lower(), section],
                    ))
        except (json.JSONDecodeError, OSError):
            pass

    def _load_pylint_json(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for item in data:
                    name = item.get("name", "")
                    desc = item.get("description", "")
                    if name:
                        self._documents.append(KnowledgeDocument(
                            doc_id=f"pylint:{name}",
                            title=name,
                            content=desc,
                            source="pylint_knowledge.json",
                            tags=["pylint", name.lower()],
                        ))
        except (json.JSONDecodeError, OSError):
            pass

    def _load_text_file(self, path: Path) -> None:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            self._documents.append(KnowledgeDocument(
                doc_id=f"file:{path.name}",
                title=path.stem,
                content=content[:5000],
                source=path.name,
                tags=[path.suffix.lstrip(".")],
            ))
        except OSError:
            pass

    def _load_playbook_file(self, path: Path) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            name = data.get("name", path.stem)
            triggers = data.get("triggers", [])
            steps = data.get("steps", [])
            content = f"Triggers: {', '.join(triggers)}. "
            content += " ".join(
                f"Step {i+1}: {s.get('description', '')}"
                for i, s in enumerate(steps)
            )
            self._documents.append(KnowledgeDocument(
                doc_id=f"playbook:{name}",
                title=name,
                content=content,
                source=f"playbook:{path.name}",
                tags=["playbook"] + [t.lower() for t in triggers],
            ))
        except (json.JSONDecodeError, OSError):
            pass

    # --- Tokenizer ---

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        text = text.lower()
        tokens = re.findall(r"[a-z][a-z0-9_]*", text)
        # Remove very short tokens
        return [t for t in tokens if len(t) > 1]
