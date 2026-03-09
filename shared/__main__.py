import json
from pathlib import Path

import typer

from shared.scaffold import group_by_provider, scaffold_provider

app = typer.Typer()


@app.command()
def scaffold(
    export_json: Path = typer.Argument(
        ..., help="data_gov_tw/datasets/export.json 的路徑"
    ),
    output_dir: Path = typer.Option(
        ".", help="產生 package 的根目錄"
    ),
) -> None:
    """從 data.gov.tw export.json 產生所有提供機關的 package。"""
    data = json.loads(export_json.read_text(encoding="utf-8"))
    groups = group_by_provider(data)

    created = 0
    skipped = 0
    for provider, datasets in groups.items():
        pkg_dir = output_dir / scaffold_provider(output_dir, provider, datasets)
        if (pkg_dir / "manifest.json").stat().st_size > 0:
            created += 1
        else:
            skipped += 1

    print(f"完成: 產生 {created} 個 package（跳過 {skipped} 個已存在）")


if __name__ == "__main__":
    app()
