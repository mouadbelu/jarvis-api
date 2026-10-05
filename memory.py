from dataclasses import dataclass

@dataclass
class MemoryStore:
    """Minimal in-process store. Replace with SQLite/Postgres in production."""

    data: dict[str, str]

    def __init__(self):
        self.data = {}

    def remember(self, key: str, value: str) -> None:
        self.data[key] = value

    def recall(self, key: str) -> str | None:
        return self.data.get(key)

    def all(self) -> dict[str, str]:
        return dict(self.data)

memory = MemoryStore()
