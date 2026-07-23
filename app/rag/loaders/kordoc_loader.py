import os
from pathlib import Path
import shutil
import subprocess
import json
import shutil
import subprocess
from app.schemas.rfp_schema import ParseResult

IS_WIN = os.name == "nt"

def resolve_kordoc_cmd() -> list[str] | None:
    candidates = []
    if os.environ.get("KORDOC_NPX"):
        candidates.append([os.environ["KORDOC_NPX"], "kordoc"])
    for name in ("npx", "npx.cmd", "npx.CMD"):
        p = shutil.which(name)
        if p:
            candidates.append([p, "kordoc"])
            break
    for name in ("kordoc", "kordoc.cmd", "kordoc.CMD"):
        p = shutil.which(name)
        if p:
            candidates.append([p])
            break

    for cmd in candidates:
        try:
            common = dict(capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace")
            r = subprocess.run(subprocess.list2cmdline(cmd + ["--version"]) if IS_WIN else cmd + ["--version"], shell=IS_WIN, **common)
            if r.returncode == 0:
                return cmd
        except Exception:
            continue
    return None

def parse_file(path: Path, kordoc_cmd: list[str]) -> ParseResult:
    res = ParseResult(source=str(path))
    try:
        common = dict(capture_output=True, text=True, timeout=600, encoding="utf-8", errors="replace")
        cmd_run = subprocess.list2cmdline(kordoc_cmd + [str(path), "--format", "json", "--silent"]) if IS_WIN else kordoc_cmd + [str(path), "--format", "json", "--silent"]
        p = subprocess.run(cmd_run, shell=IS_WIN, **common)
        
        if p.returncode != 0:
            res.status = "error"
            return res

        data = json.loads(p.stdout.strip())
        res.markdown = data.get("markdown", "")
        res.char_count = len(res.markdown)
        res.fmt = path.suffix.lstrip(".")
        return res
    except Exception as e:
        res.status = f"error: {str(e)}"
        return res