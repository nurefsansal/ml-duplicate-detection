"""Pydantic şema sınırları — API ile uyumlu kalmalı."""

import pytest
from pydantic import ValidationError

from backend.schemas.requests import DetectFromUrlRequest, DetectRequest


def test_detect_request_min_rules_bounds() -> None:
    DetectRequest(minRulesToMatch=1)
    DetectRequest(minRulesToMatch=4)
    with pytest.raises(ValidationError):
        DetectRequest(minRulesToMatch=0)
    with pytest.raises(ValidationError):
        DetectRequest(minRulesToMatch=5)


def test_detect_from_url_min_rules_bounds() -> None:
    DetectFromUrlRequest(url="http://example.com", minRulesToMatch=1)
    DetectFromUrlRequest(url="http://example.com", minRulesToMatch=4)
    with pytest.raises(ValidationError):
        DetectFromUrlRequest(url="http://example.com", minRulesToMatch=0)
    with pytest.raises(ValidationError):
        DetectFromUrlRequest(url="http://example.com", minRulesToMatch=5)
