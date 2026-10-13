"""Import the source tree and keep all temporary test files inside the project."""

from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def temporary_directory() -> tempfile.TemporaryDirectory:
    """Create a scoped temporary directory under the project scratch folder."""
    scratch = ROOT / ".scratch"
    scratch.mkdir(exist_ok=True)
    return tempfile.TemporaryDirectory(dir=scratch)
