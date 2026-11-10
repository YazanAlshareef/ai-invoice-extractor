from pathlib import Path

import pytest

from extractor.evaluate import evaluate
from extractor.llm import FatalExtractionError

ROOT = Path(__file__).resolve().parent.parent


def test_fatal_error_stops_evaluation():
    class Retired:
        def extract(self, p):
            raise FatalExtractionError("404")

    with pytest.raises(FatalExtractionError):
        evaluate(Retired(), ROOT / "inbox", ROOT / "truth")


def test_truth_without_inbox_file_exits_cleanly(tmp_path):
    with pytest.raises(SystemExit, match="no file"):
        evaluate(None, tmp_path, ROOT / "truth")
