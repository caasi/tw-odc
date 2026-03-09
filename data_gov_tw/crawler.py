from pathlib import Path

import aiohttp

EXPORTS = [
    "https://data.gov.tw/datasets/export/json",
    "https://data.gov.tw/datasets/export/csv",
    "https://data.gov.tw/datasets/export/xml",
]

DEFAULT_OUTPUT_DIR = Path(__file__).parent / "datasets"


def _filename_from_url(url: str) -> str:
    ext = url.rsplit("/", 1)[-1]
    return f"export.{ext}"


async def crawl(output_dir: Path = DEFAULT_OUTPUT_DIR) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    async with aiohttp.ClientSession() as session:
        for url in EXPORTS:
            filename = _filename_from_url(url)
            dest = output_dir / filename
            print(f"下載中: {url}")

            async with session.get(url) as resp:
                if resp.status != 200:
                    print(f"  失敗: HTTP {resp.status}")
                    continue

                data = await resp.read()
                dest.write_bytes(data)
                print(f"  完成: {dest} ({len(data)} bytes)")
