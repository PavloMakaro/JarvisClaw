import lancedb
from lancedb.embeddings import get_registry
from lancedb.pydantic import LanceModel, Vector
import logging
import json
import os

class VectorMemory:
    def __init__(self, storage_path="data/lancedb", table_name="memory"):
        self.logger = logging.getLogger("VectorMemory")
        self.storage_path = storage_path
        self.table_name = table_name

        # Ensure directory exists
        os.makedirs(storage_path, exist_ok=True)

        # Initialize Embedding Function (using sentence-transformers)
        # This will download the model on first use if not present
        self.func = get_registry().get("sentence-transformers").create(name="all-MiniLM-L6-v2")

        # Define Schema dynamically to bind the function
        class MemoryItem(LanceModel):
            text: str = self.func.SourceField()
            vector: Vector(self.func.ndims()) = self.func.VectorField()
            metadata: str # Store as JSON string

        self.schema = MemoryItem

        # Connect to DB
        self.db = lancedb.connect(self.storage_path)

        # Open or Create Table
        if self.table_name in self.db.table_names():
            self.table = self.db.open_table(self.table_name)
        else:
            self.table = self.db.create_table(self.table_name, schema=self.schema)

    def add(self, text: str, metadata: dict = None):
        """Adds a text item to the vector store."""
        if not text:
            return

        meta_str = json.dumps(metadata or {})

        # The embedding function automatically handles vectorization of 'text'
        self.table.add([{"text": text, "metadata": meta_str}])
        self.logger.info(f"Added to memory: {text[:50]}...")

    def search(self, query: str, k: int = 3):
        """Searches for similar items."""
        if not query:
            return []

        try:
            results = self.table.search(query).limit(k).to_list()

            parsed_results = []
            for r in results:
                try:
                    meta = json.loads(r["metadata"])
                except:
                    meta = {}

                # LanceDB search returns items. Distance might be available depending on query type.
                # Usually it's in _distance if metric is set, but let's just return the item.
                parsed_results.append({
                    "text": r["text"],
                    "metadata": meta,
                    "score": r.get("_distance", 0.0)
                })
            return parsed_results
        except Exception as e:
            self.logger.error(f"Search failed: {e}")
            return []
