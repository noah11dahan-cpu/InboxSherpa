import asyncio

async def main() -> None:
    while True:
        print("[worker] noop tick")
        await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
