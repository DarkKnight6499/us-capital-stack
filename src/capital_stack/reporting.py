"""Portable Markdown tables and deterministic output artifacts."""

from pathlib import Path
import numbers

import pandas as pd


def markdown_table(frame: pd.DataFrame, digits: int = 6, *, scientific: bool = False) -> str:
    """Render a Markdown table without requiring tabulate."""
    def cell(value: object) -> str:
        if isinstance(value, bool):
            return str(value)
        if isinstance(value, numbers.Real) and not isinstance(value, numbers.Integral):
            return f"{value:.{digits}e}" if scientific else f"{value:.{digits}f}"
        return str(value).replace("|", "/").replace("\n", " ")

    columns = [str(column) for column in frame.columns]
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join([":-"] * len(columns)) + " |"]
    lines += ["| " + " | ".join(cell(value) for value in row) + " |" for row in frame.itertuples(index=False, name=None)]
    return "\n".join(lines) + "\n"


def write_table(frame: pd.DataFrame, output: Path, name: str) -> None:
    """Write equivalent CSV and Markdown artifacts to the requested output directory."""
    output.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output / f"{name}.csv", index=False, float_format="%.12g")
    (output / f"{name}.md").write_text(markdown_table(frame, scientific="residual" in name), encoding="utf-8")
