import pytest

from extractor.llm import ExtractionError, FixtureExtractor, GeminiExtractor, parse_json


class Boom(Exception):
    def __init__(self, code, msg="boom"):
        super().__init__(msg)
        self.code = code


class FakeClient:
    """Mimics client.models.generate_content; plays back a script of results/exceptions."""

    def __init__(self, script):
        self.script, self.calls = list(script), 0
        self.models = self

    def generate_content(self, **kw):
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return type("R", (), {"text": item})()


@pytest.fixture
def pdf(tmp_path):
    p = tmp_path / "a.pdf"
    p.write_bytes(b"%PDF-1.4 fake")
    return p


def make(script, **kw):
    sleeps = []
    ex = GeminiExtractor(client=FakeClient(script), model="m", sleep=sleeps.append, min_interval=0, **kw)
    return ex, sleeps


def test_success_and_fenced_json(pdf):
    ex, _ = make(['```json\n{"vendor": "A"}\n```'])
    assert ex.extract(pdf) == {"vendor": "A"}


def test_retries_429_with_backoff_then_succeeds(pdf):
    ex, sleeps = make([Boom(429), Boom(503), '{"a": 1}'])
    assert ex.extract(pdf) == {"a": 1}
    assert ex._client.calls == 3 and len(sleeps) == 2
    assert sleeps[1] > sleeps[0]  # backoff grows


def test_uses_server_retry_delay(pdf):
    ex, sleeps = make([Boom(429, "quota. retryDelay: 23s"), '{"a": 1}'])
    ex.extract(pdf)
    assert 23 <= sleeps[0] < 24.1


def test_gives_up_after_max_retries(pdf):
    ex, _ = make([Boom(429)] * 3, max_retries=2)
    with pytest.raises(ExtractionError, match="429"):
        ex.extract(pdf)
    assert ex._client.calls == 3


def test_non_retryable_error_fails_at_once(pdf):
    ex, sleeps = make([Boom(400)])
    with pytest.raises(ExtractionError):
        ex.extract(pdf)
    assert ex._client.calls == 1 and sleeps == []


def test_bad_json_is_not_retried(pdf):
    ex, _ = make(["not json"])
    with pytest.raises(ExtractionError, match="valid JSON"):
        ex.extract(pdf)
    assert ex._client.calls == 1


def test_free_tier_spacing_between_calls(pdf):
    sleeps = []
    ex = GeminiExtractor(client=FakeClient(["{}", "{}"]), model="m", min_interval=6,
                         sleep=sleeps.append, clock=lambda: 100.0)
    ex.extract(pdf)
    ex.extract(pdf)
    assert sleeps == [6]


def test_missing_key_message(pdf, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(ExtractionError, match="GEMINI_API_KEY"):
        GeminiExtractor(min_interval=0).extract(pdf)


def test_fixture_extractor(tmp_path, pdf):
    (tmp_path / "a.json").write_text('{"vendor": "F"}')
    assert FixtureExtractor(tmp_path).extract(pdf) == {"vendor": "F"}
    with pytest.raises(ExtractionError, match="no cached fixture"):
        FixtureExtractor(tmp_path / "none").extract(pdf)


def test_parse_json_rejects_non_object():
    with pytest.raises(ExtractionError):
        parse_json("[1]")
