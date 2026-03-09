import asyncio

from data_gov_tw.crawler import crawl


async def run() -> None:
    await crawl()
