from __future__ import annotations

import asyncio
import json
from pathlib import Path
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models import User
from app.services.importer import import_json_messages
from app.schemas.importer import ImportRequest
from app.services.clustering import cluster_messages_v1


DEMO_DATE = "2026-01-12"


async def main() -> None:
    # load demo messages
    p = Path("data/sample_inbox.json")
    if not p.exists():
        raise RuntimeError("Missing data/sample_inbox.json. Generate it first.")

    messages = json.loads(p.read_text(encoding="utf-8"))

    async with AsyncSessionLocal() as session:
        u = await session.scalar(select(User).where(User.email == "demo@inboxsherpa.local"))
        if not u:
            raise RuntimeError("Demo user missing. Run: python -m app.scripts.seed_dev")

        req = ImportRequest(user_id=u.id, messages=messages)
        res = await import_json_messages(session=session, req=req)
        print("Import:", res.model_dump())

        # run clustering explicitly to show pipeline
        from datetime import date
        d = date.fromisoformat(DEMO_DATE)
        clusters = await cluster_messages_v1(session=session, user_id=u.id, digest_date=d, rebuild_for_day=True)
        print(f"Clusters created: {len(clusters)}")
        for c in clusters[:8]:
            print("-", c.title)


if __name__ == "__main__":
    asyncio.run(main())
