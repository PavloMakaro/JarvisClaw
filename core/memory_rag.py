import os
import time
import hashlib
import traceback

class VectorMemory:
    def __init__(self, collection_name="user_facts", persist_path="data/chroma_db"):
        self.enabled = False
        try:
            import chromadb
            # Try to initialize PersistentClient
            # Ensure directory exists
            if not os.path.exists(persist_path):
                os.makedirs(persist_path)

            self.client = chromadb.PersistentClient(path=persist_path)
            self.collection = self.client.get_or_create_collection(name=collection_name)
            self.enabled = True
            print(f"Vector Memory initialized at {persist_path}")
        except Exception as e:
            print(f"Warning: ChromaDB failed to initialize: {e}")
            print("Falling back to text file memory (legacy mode) or disabled.")
            self.enabled = False

    def add(self, text, metadata=None):
        if not self.enabled:
            return "Vector memory not enabled."

        try:
            doc_id = hashlib.md5(f"{text}{time.time()}".encode()).hexdigest()
            self.collection.add(
                documents=[text],
                metadatas=[metadata or {}],
                ids=[doc_id]
            )
            return f"Fact stored (ID: {doc_id})"
        except Exception as e:
            return f"Error adding to vector memory: {e}"

    def search(self, query, n_results=3):
        if not self.enabled:
            return []

        try:
            count = self.collection.count()
            if count == 0:
                return []

            n = min(n_results, count)
            results = self.collection.query(
                query_texts=[query],
                n_results=n
            )
            return results["documents"][0] if results["documents"] else []
        except Exception as e:
            print(f"Error searching vector memory: {e}")
            return []

# Singleton instance
memory_instance = VectorMemory()
