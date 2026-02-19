import json
import os
import math
import re

class VectorMemory:
    def __init__(self, storage_file="data/vector_memory.json"):
        self.storage_file = storage_file
        self.memory = []
        self._load()

    def _load(self):
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, "r", encoding="utf-8") as f:
                    self.memory = json.load(f)
            except:
                self.memory = []
        else:
            self.memory = []

    def _save(self):
        # ensure dir exists
        os.makedirs(os.path.dirname(self.storage_file), exist_ok=True)
        with open(self.storage_file, "w", encoding="utf-8") as f:
            json.dump(self.memory, f, ensure_ascii=False, indent=2)

    def add(self, text, metadata=None):
        """Adds a memory item."""
        if not text:
            return

        entry = {
            "text": text,
            "metadata": metadata or {},
            "timestamp": None # Add timestamp if needed
        }
        self.memory.append(entry)
        self._save()

    def search(self, query, k=3):
        """
        Simulates vector search using keyword overlap / simple scoring.
        Returns top k results.
        """
        if not self.memory:
            return []

        query_tokens = set(re.findall(r"\w+", query.lower()))
        results = []

        for item in self.memory:
            text = item["text"]
            text_tokens = set(re.findall(r"\w+", text.lower()))

            if not text_tokens:
                score = 0
            else:
                # Jaccard similarity as a proxy for semantic relevance
                intersection = query_tokens.intersection(text_tokens)
                union = query_tokens.union(text_tokens)
                score = len(intersection) / len(union) if union else 0

            if score > 0:
                results.append((score, item))

        # Sort by score desc
        results.sort(key=lambda x: x[0], reverse=True)

        return [r[1] for r in results[:k]]
