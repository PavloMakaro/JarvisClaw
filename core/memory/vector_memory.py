import os
import logging
from typing import List, Dict, Any, Optional
import lancedb
from sentence_transformers import SentenceTransformer

class VectorMemory:
    def __init__(self, storage_path="data/lancedb"):
        self.storage_path = storage_path
        self.logger = logging.getLogger("VectorMemory")
        self.db = None
        self.table = None
        self.embedding_model = None
        self._initialize()

    def _initialize(self):
        try:
            # Initialize LanceDB
            os.makedirs(self.storage_path, exist_ok=True)
            self.db = lancedb.connect(self.storage_path)

            # Initialize Embedding Model
            # use a small, fast model
            try:
                self.embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
            except Exception as e:
                self.logger.error(f"Failed to load embedding model: {e}")
                self.embedding_model = None

            # Open or Create Table
            if self.embedding_model:
                # We need a schema or initial data to create a table if it doesn't exist
                # But we can lazily create it on first add
                pass

        except Exception as e:
            self.logger.error(f"Failed to initialize VectorMemory: {e}")

    def _get_embedding(self, text: str) -> List[float]:
        if not self.embedding_model:
            return []
        try:
            return self.embedding_model.encode(text).tolist()
        except Exception as e:
            self.logger.error(f"Embedding error: {e}")
            return []

    def add(self, text: str, metadata: Dict[str, Any] = None):
        """Adds a memory item."""
        if not text or not self.db or not self.embedding_model:
            return

        vector = self._get_embedding(text)
        if not vector:
            return

        data = [{
            "vector": vector,
            "text": text,
            "metadata": metadata or {},
            "timestamp": None # Add timestamp if needed
        }]

        try:
            if "memories" not in self.db.table_names():
                self.table = self.db.create_table("memories", data=data)
            else:
                self.table = self.db.open_table("memories")
                self.table.add(data)
        except Exception as e:
            self.logger.error(f"Error adding to LanceDB: {e}")

    def search(self, query: str, k: int = 3) -> List[Dict[str, Any]]:
        """Searches for similar memories."""
        if not query or not self.db or not self.embedding_model:
            return []

        vector = self._get_embedding(query)
        if not vector:
            return []

        try:
            if "memories" not in self.db.table_names():
                return []

            self.table = self.db.open_table("memories")

            # LanceDB search
            results = self.table.search(vector).limit(k).to_list()

            # Format results
            # Each result has 'text', 'metadata', '_distance' etc
            # We return just the dicts with text and metadata
            formatted_results = []
            for r in results:
                formatted_results.append({
                    "text": r["text"],
                    "metadata": r["metadata"],
                    "score": 1 - r.get("_distance", 1.0) # Convert distance to similarity score roughly
                })
            return formatted_results

        except Exception as e:
            self.logger.error(f"Error searching LanceDB: {e}")
            return []
