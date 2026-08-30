"""Put the repo root on sys.path so the test modules can `import stats`,
`import run_weekly`, etc. regardless of how pytest is invoked (`pytest`,
`python -m pytest`, from the root or from tests/)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
