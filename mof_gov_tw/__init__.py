from shared.fetcher import fetch_all


async def run() -> None:
    await fetch_all(__file__)
