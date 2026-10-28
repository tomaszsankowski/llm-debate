import json
import sqlite3
from pathlib import Path


class Storage:
    """Atomowe snapshoty w SQLite; wywołania odbywają się w jednym wątku pętli API."""

    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS debates (id TEXT PRIMARY KEY, data TEXT NOT NULL)"
        )
        self.connection.commit()

    def save(self, debate: dict) -> None:
        with self.connection:
            self.connection.execute(
                "INSERT INTO debates VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
                (debate["id"], json.dumps(debate, ensure_ascii=False)),
            )

    def get(self, debate_id: str) -> dict:
        row = self.connection.execute(
            "SELECT data FROM debates WHERE id=?", (debate_id,)
        ).fetchone()
        if row is None:
            raise KeyError(debate_id)
        return json.loads(row[0])

    def delete(self, debate_id: str) -> None:
        with self.connection:
            cursor = self.connection.execute("DELETE FROM debates WHERE id=?", (debate_id,))
            if cursor.rowcount == 0:
                raise KeyError(debate_id)

    def list(self) -> list[dict]:
        rows = self.connection.execute(
            "SELECT id, json_extract(data, '$.config.name'), "
            "json_extract(data, '$.config.topic'), json_extract(data, '$.created_at'), "
            "json_extract(data, '$.status'), json_extract(data, '$.annotations.outcome'), "
            "json_array_length(data, '$.messages'), json_extract(data, '$.config.rounds') "
            "FROM debates ORDER BY json_extract(data, '$.created_at') DESC"
        ).fetchall()
        keys = ["id", "name", "topic", "created_at", "status", "outcome", "turns", "rounds"]
        return [dict(zip(keys, row, strict=True)) for row in rows]

    def recover(self, now: str) -> None:
        for summary in self.list():
            if summary["status"] not in {"running", "pausing", "waiting"}:
                continue
            debate = self.get(summary["id"])
            debate.update(
                status="interrupted",
                reason="Backend został uruchomiony ponownie.",
                updated_at=now,
                retry_at=None,
            )
            for attempt in debate["attempts"]:
                if attempt["status"] == "streaming":
                    attempt.update(
                        status="interrupted",
                        finished_at=now,
                        error={"code": "restart", "message": "Przerwano pracę backendu."},
                    )
            self.save(debate)

    def close(self) -> None:
        self.connection.close()
