"""crawlers/common/curl_cffi_client 유닛 테스트."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.crawlers.common.curl_cffi_client import (
    DEFAULT_IMPERSONATE,
    CurlCffiClient,
    default_browser_headers,
)


class TestDefaultBrowserHeaders:
    def test_includes_chrome_ua(self):
        h = default_browser_headers()
        assert "Chrome/124" in h["User-Agent"]
        assert "Accept-Language" in h

    def test_accept_language_override(self):
        h = default_browser_headers(accept_language="en-GB,en;q=0.9")
        assert h["Accept-Language"] == "en-GB,en;q=0.9"


class TestCurlCffiClient:
    def test_block_signals_are_site_specific(self):
        adzuna_sigs = ("human verification", "complete the security check")
        indeed_sigs = ("additional verification required", "just a moment")

        adz = CurlCffiClient(block_signals=adzuna_sigs)
        ind = CurlCffiClient(block_signals=indeed_sigs)
        try:
            assert adz.is_blocked("Please complete Human Verification")
            assert not adz.is_blocked("Additional verification required")
            assert ind.is_blocked("Additional verification required")
            assert not ind.is_blocked("complete the security check now")
        finally:
            adz.close()
            ind.close()

    def test_get_uses_default_timeout(self):
        client = CurlCffiClient(timeout=17.0, block_signals=())
        mock_sess = MagicMock()
        client.session = mock_sess
        client.get("https://example.com/x")
        _, kwargs = mock_sess.get.call_args
        assert kwargs["timeout"] == 17.0
        client.close()

    def test_impersonate_default(self):
        with patch(
            "src.crawlers.common.curl_cffi_client.curl_requests.Session"
        ) as MockSession:
            MockSession.return_value = MagicMock()
            client = CurlCffiClient()
            MockSession.assert_called_once_with(impersonate=DEFAULT_IMPERSONATE)
            client.close()
