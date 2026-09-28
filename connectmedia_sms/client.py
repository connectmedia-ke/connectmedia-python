import json
import re
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, Optional, Union

DEFAULT_BASE_URL = "https://dashboard.connectmedia.co.ke/api.php"

# Application code returned in the JSON envelope when each action succeeds.
SUCCESS_CODES = {"send": "201", "balance": "200", "history": "202", "inbox": "302"}

Transport = Callable[[str, Dict[str, str], bytes, float], bytes]


class ConnectMediaError(Exception):
    """Raised when the API returns a non-success code or the request fails."""

    def __init__(self, code: str, message: str, response: Optional[Dict[str, Any]] = None):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.response = response or {}


def normalize_msisdn(number: str) -> str:
    """Return a number in 2547XXXXXXXX form.

    Strips spaces, dashes, brackets and a leading '+', and converts Kenyan local
    numbers (07XXXXXXXX / 01XXXXXXXX) to international format. Other inputs are
    returned without the punctuation and otherwise unchanged.
    """
    digits = re.sub(r"[\s\-()+]", "", str(number))
    if re.fullmatch(r"0[17]\d{8}", digits):
        return "254" + digits[1:]
    return digits


def _urllib_transport(url: str, headers: Dict[str, str], body: bytes, timeout: float) -> bytes:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as err:
        # The API reports errors in the JSON body; surface it when present.
        return err.read()


class Client:
    """Connect Media SMS API client.

    >>> client = Client("YOUR_64_CHARACTER_API_KEY")
    >>> client.send("0712345678", "Your order has shipped.", sender="YourBrand")
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        transport: Optional[Transport] = None,
    ):
        if not api_key:
            raise ValueError("api_key is required")
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self._transport = transport or _urllib_transport

    def send(
        self,
        to: Union[str, Iterable[str]],
        message: str,
        sender: Optional[str] = None,
        schedule_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Send an SMS to one number, a comma-separated string or a list of numbers."""
        numbers = [to] if isinstance(to, str) else list(to)
        numbers = [normalize_msisdn(n) for part in numbers for n in str(part).split(",") if n.strip()]
        if not numbers:
            raise ValueError("at least one recipient is required")
        if not message:
            raise ValueError("message is required")
        payload: Dict[str, Any] = {"to": ",".join(numbers), "message": message}
        if sender:
            if len(sender) > 11:
                raise ValueError("sender must be 11 characters or fewer")
            payload["sender"] = sender
        if schedule_at is not None:
            payload["schedule"] = 1
            payload["schedule_datetime"] = schedule_at.strftime("%Y-%m-%d %H:%M:%S")
        return self._call("send", payload)

    def balance(self) -> Dict[str, Any]:
        """Return the account's credit balance."""
        return self._call("balance", {})

    def history(
        self,
        limit: int = 50,
        offset: int = 0,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """List sent messages with delivery status. Dates are YYYY-MM-DD."""
        payload: Dict[str, Any] = {"limit": limit, "offset": offset}
        if start_date:
            payload["start_date"] = start_date
        if end_date:
            payload["end_date"] = end_date
        return self._call("history", payload)

    def inbox(self, limit: int = 50) -> Dict[str, Any]:
        """List replies received from customers (two-way SMS)."""
        return self._call("inbox", {"limit": limit})

    def _call(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        body = json.dumps({"action": action, **payload}).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "connectmedia-sms-python/10.0.0",
        }
        try:
            raw = self._transport(self.base_url, headers, body, self.timeout)
        except OSError as err:
            raise ConnectMediaError("network", str(err)) from err
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as err:
            raise ConnectMediaError("invalid_response", "The API did not return JSON") from err
        code = str(data.get("code", ""))
        if code != SUCCESS_CODES[action]:
            raise ConnectMediaError(code or "unknown", data.get("message", "Unknown error"), data)
        return data
