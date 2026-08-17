import unittest
from unittest.mock import patch

from app.models import Account
from app.quota import fetch_quota
from scripts.probe_start_plan import has_start_plan


class Response:
    status_code = 200
    text = ""

    def json(self):
        return {"code": 0, "data": {}}


class Client:
    def __init__(self, requests):
        self.requests = requests

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def get(self, url, headers):
        self.requests.append((url, headers))
        return Response()


class StartPlanProbeTest(unittest.TestCase):
    def test_detects_start_plan(self):
        response = {"data": {"plans": [{"plan_id": "zcode-v3-start-plan-0817"}]}}
        self.assertTrue(has_start_plan(response))
        self.assertFalse(has_start_plan({"data": {"plans": [], "hasActiveStartPlan": False}}))


class QuotaHeadersTest(unittest.IsolatedAsyncioTestCase):
    async def test_balance_uses_zcode_app_version(self):
        requests = []
        account = Account.create("zai", "test", "a.b.c")

        with (
            patch("app.quota.httpx.AsyncClient", return_value=Client(requests)),
            patch("app.quota.store.update_account"),
        ):
            await fetch_quota(account)

        headers_by_path = {url.rsplit("/", 1)[-1]: headers for url, headers in requests}
        self.assertEqual(headers_by_path["balance"]["X-Zcode-App-Version"], "3.7.7")
        self.assertNotIn("X-Zcode-App-Version", headers_by_path["current"])
        self.assertNotIn("X-Zcode-App-Version", headers_by_path["usage"])


if __name__ == "__main__":
    unittest.main()
