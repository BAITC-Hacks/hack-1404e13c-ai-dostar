"""Build the walkthrough from its readable source, execute it, export HTML.

Usage: .venv/Scripts/python.exe scripts/run_ml_notebook.py
The private kernelspec uses this exact interpreter and stays in .venv.
"""
from pathlib import Path
import os
import sys

import nbformat
from nbclient import NotebookClient
from nbconvert import HTMLExporter

ROOT = Path(__file__).resolve().parents[1]
NAME = "01_demand_model_walkthrough"


def main():
    source = ROOT / "notebooks" / f"{NAME}.py"
    cells, lines, markdown = [], [], False

    def flush():
        text = "\n".join(lines).strip()
        if text:
            cells.append((nbformat.v4.new_markdown_cell if markdown
                          else nbformat.v4.new_code_cell)(text))

    for line in source.read_text(encoding="utf-8").splitlines():
        if line.startswith("# %%"):
            flush()
            lines = []
            markdown = "[markdown]" in line
        else:
            lines.append(line.removeprefix("# ") if markdown else line)
    flush()
    nb = nbformat.v4.new_notebook(cells=cells)
    nb.metadata.kernelspec = {"name": "ai-dostar", "display_name": "AI-Dostar (.venv)",
                              "language": "python"}
    # Install locally, without changing the user's global Jupyter configuration.
    from ipykernel.kernelspec import install
    install(prefix=sys.prefix, kernel_name="ai-dostar", display_name="AI-Dostar (.venv)")
    local_jupyter = str(Path(sys.prefix) / "share" / "jupyter")
    os.environ["JUPYTER_PATH"] = os.pathsep.join(filter(None, [local_jupyter, os.environ.get("JUPYTER_PATH")]))
    target = source.with_suffix(".ipynb")
    nbformat.write(nb, target)
    client = NotebookClient(nb, timeout=600, kernel_name="ai-dostar",
                            resources={"metadata": {"path": str(ROOT)}})
    client.on_cell_start = lambda cell, cell_index, **kw: print(
        f"Cell {cell_index + 1}/{len(cells)}: {cell.cell_type}", flush=True)
    client.execute()
    nbformat.write(nb, target)
    html, _ = HTMLExporter().from_notebook_node(nb)
    target.with_suffix(".html").write_text(html, encoding="utf-8")
    print(f"Executed notebook: {target}")
    print(f"Offline HTML: {target.with_suffix('.html')}")


if __name__ == "__main__":
    main()
