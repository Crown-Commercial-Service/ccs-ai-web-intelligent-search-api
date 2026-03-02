import sys
import types

import requests

from ccs_website_data import clean_html_from_text, fetch_all_ccs_frameworks


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        next_item = self._responses.pop(0)
        if isinstance(next_item, Exception):
            raise next_item
        return next_item


class FakeDataFrame:
    def __init__(self, rows):
        self._rows = list(rows)
        self.iloc = _FakeILoc(self._rows)

    def __len__(self):
        return len(self._rows)


class _FakeILoc:
    def __init__(self, rows):
        self._rows = rows

    def __getitem__(self, idx):
        return self._rows[idx]


def test_clean_html_from_text_basic_cases():
    assert clean_html_from_text(None) is None
    assert clean_html_from_text(float("nan")) is None
    assert clean_html_from_text(" plain text ") == "plain text"
    assert clean_html_from_text("<p>Hello <strong>World</strong></p>") == "Hello World"


def test_fetch_all_ccs_frameworks_paginates_and_cleans(monkeypatch):
    page_1_payload = {
        "results": [
            {
                "rm_number": "RM0001",
                "description": "<p>First <b>framework</b></p>",
                "summary": "<div>Summary one</div>",
                "benefits": None,
                "how_to_buy": "Buy directly",
                "keywords": "<span>cloud</span>",
            }
        ],
        "meta": {"last_page": 2},
    }
    page_2_payload = {
        "results": [
            {
                "rm_number": "RM0002",
                "description": "<p>Second framework</p>",
                "summary": "Summary two",
                "benefits": "<ul><li>Benefit A</li></ul>",
                "how_to_buy": "<p>Call CCS</p>",
                "keywords": None,
            }
        ],
        "meta": {"last_page": 2},
    }

    fake_session = FakeSession(
        [FakeResponse(page_1_payload), FakeResponse(page_2_payload)]
    )
    monkeypatch.setattr(requests, "Session", lambda: fake_session)
    monkeypatch.setitem(sys.modules, "pandas", types.SimpleNamespace(DataFrame=FakeDataFrame))

    result = fetch_all_ccs_frameworks(status="Live", sleep_seconds=0)

    assert isinstance(result, FakeDataFrame)
    assert len(result) == 2
    assert [call["params"]["page"] for call in fake_session.calls] == [1, 2]
    assert result.iloc[0]["description"] == "First framework"
    assert result.iloc[0]["keywords"] == "cloud"
    assert result.iloc[1]["benefits"] == "Benefit A"
    assert result.iloc[1]["how_to_buy"] == "Call CCS"


def test_fetch_all_ccs_frameworks_returns_none_on_request_error(monkeypatch):
    fake_session = FakeSession([requests.exceptions.Timeout("network timeout")])
    monkeypatch.setattr(requests, "Session", lambda: fake_session)

    result = fetch_all_ccs_frameworks(sleep_seconds=0)

    assert result is None
