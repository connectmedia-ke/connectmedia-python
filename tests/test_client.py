import json
import unittest
from datetime import datetime

from connectmedia_sms import Client, ConnectMediaError, normalize_msisdn


class FakeTransport:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def __call__(self, url, headers, body, timeout):
        self.calls.append((url, headers, json.loads(body)))
        if isinstance(self.response, Exception):
            raise self.response
        return json.dumps(self.response).encode() if isinstance(self.response, dict) else self.response


class NormalizeTest(unittest.TestCase):
    def test_local_kenyan_numbers(self):
        self.assertEqual(normalize_msisdn("0712345678"), "254712345678")
        self.assertEqual(normalize_msisdn("0110 123 456"), "254110123456")

    def test_international_and_punctuation(self):
        self.assertEqual(normalize_msisdn("+254 712-345-678"), "254712345678")
        self.assertEqual(normalize_msisdn("256712345678"), "256712345678")


class ClientTest(unittest.TestCase):
    def test_send_builds_request(self):
        t = FakeTransport({"code": "201", "message": "Queued"})
        res = Client("k" * 64, transport=t).send(["0712345678", "+254733000111"], "Hi", sender="Brand")
        url, headers, body = t.calls[0]
        self.assertEqual(url, "https://app.connectmedia.co.ke/api.php")
        self.assertEqual(headers["Authorization"], "Bearer " + "k" * 64)
        self.assertEqual(body, {"action": "send", "to": "254712345678,254733000111", "message": "Hi", "sender": "Brand"})
        self.assertEqual(res["code"], "201")

    def test_send_splits_comma_string_and_schedules(self):
        t = FakeTransport({"code": "201", "message": "ok"})
        Client("k", transport=t).send("0712345678, 0722000000", "Hi", schedule_at=datetime(2026, 12, 1, 9, 0))
        body = t.calls[0][2]
        self.assertEqual(body["to"], "254712345678,254722000000")
        self.assertEqual(body["schedule"], 1)
        self.assertEqual(body["schedule_datetime"], "2026-12-01 09:00:00")

    def test_validation(self):
        c = Client("k", transport=FakeTransport({}))
        with self.assertRaises(ValueError):
            c.send([], "Hi")
        with self.assertRaises(ValueError):
            c.send("0712345678", "")
        with self.assertRaises(ValueError):
            c.send("0712345678", "Hi", sender="ThisIsTooLong")
        with self.assertRaises(ValueError):
            Client("")

    def test_each_action_success_code(self):
        for method, code in (("balance", "200"), ("history", "202"), ("inbox", "302")):
            t = FakeTransport({"code": code, "message": "ok", "data": {}})
            self.assertEqual(getattr(Client("k", transport=t), method)()["code"], code)
            self.assertEqual(t.calls[0][2]["action"], method)

    def test_api_error_raises(self):
        t = FakeTransport({"code": "100", "message": "Invalid or missing API key"})
        with self.assertRaises(ConnectMediaError) as ctx:
            Client("k", transport=t).balance()
        self.assertEqual(ctx.exception.code, "100")
        self.assertIn("Invalid", ctx.exception.message)

    def test_wrong_success_code_for_action_raises(self):
        # A 200 envelope is not success for a send.
        with self.assertRaises(ConnectMediaError):
            Client("k", transport=FakeTransport({"code": "200", "message": "?"})).send("0712345678", "Hi")

    def test_non_json_and_network_errors(self):
        with self.assertRaises(ConnectMediaError) as ctx:
            Client("k", transport=FakeTransport(b"<html>")).balance()
        self.assertEqual(ctx.exception.code, "invalid_response")
        with self.assertRaises(ConnectMediaError) as ctx:
            Client("k", transport=FakeTransport(OSError("timed out"))).balance()
        self.assertEqual(ctx.exception.code, "network")

    def test_history_optional_dates(self):
        t = FakeTransport({"code": "202", "message": "ok"})
        Client("k", transport=t).history(limit=5, start_date="2026-09-01")
        self.assertEqual(t.calls[0][2], {"action": "history", "limit": 5, "offset": 0, "start_date": "2026-09-01"})


if __name__ == "__main__":
    unittest.main()
