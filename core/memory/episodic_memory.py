import json
import os
import asyncio

class EpisodicMemory:
    def __init__(self, storage_file="data/sessions.json"):
        self.storage_file = storage_file
        self.sessions = {}
        self.lock = asyncio.Lock()
        self._load()

    def _load(self):
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, "r", encoding="utf-8") as f:
                    self.sessions = json.load(f)
            except:
                self.sessions = {}
        else:
            self.sessions = {}

    def _save(self):
        os.makedirs(os.path.dirname(self.storage_file), exist_ok=True)
        with open(self.storage_file, "w", encoding="utf-8") as f:
            json.dump(self.sessions, f, ensure_ascii=False, indent=2)

    async def get_history(self, chat_id):
        async with self.lock:
            return self.sessions.get(str(chat_id), [])

    async def update_history(self, chat_id, history):
        async with self.lock:
            self.sessions[str(chat_id)] = history
            self._save() # Synchronous save for now, could be async in real thread

    async def add_message(self, chat_id, role, content):
        async with self.lock:
            cid = str(chat_id)
            if cid not in self.sessions:
                self.sessions[cid] = []

            self.sessions[cid].append({"role": role, "content": content})
            self._save()

    async def clear(self, chat_id):
        async with self.lock:
            self.sessions[str(chat_id)] = []
            self._save()
