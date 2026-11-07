from __future__ import annotations

import base64
from datetime import datetime
import json
import logging
import re
import secrets
import string
from typing import Any

import aiohttp
import async_timeout
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from . import const
from .const import (
    DEFAULT_CHANNEL,
    DEFAULT_TENANT_ID,
    REQUEST_KEY_PREFIX,
    REQUEST_KEY_SUFFIX,
    TIMEOUT,
    USER_AGENT,
    mini_program_referer,
)

_LOGGER = logging.getLogger(__name__)


class ShenzhenWaterApiError(Exception):
    """Shenzhen Water API error."""


class ShenzhenWaterAuthError(ShenzhenWaterApiError):
    """Utoken 失效，重新登录后可以恢复。"""


class ShenzhenWaterOpenIdError(ShenzhenWaterApiError):
    """OpenId 本身不被服务端识别，重登也没用，只能换 OpenId。"""


# 服务端认不出 OpenId 时的提示
_OPENID_INVALID_MARKERS = ("不能识别用户", "不存在的用户", "9991002")


class ShenzhenWaterApi:
    """Client for Shenzhen Water mini-program API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        customer_code: str,
        openid: str,
        tenant_id: str = DEFAULT_TENANT_ID,
        channel: str = DEFAULT_CHANNEL,
        base_url: str | None = None,
    ) -> None:
        self._session = session
        self._customer_code = customer_code
        self._openid = (openid or "").strip()
        self._guid = ""
        self._utoken = ""
        self._tenant_id = tenant_id
        self._channel = channel
        self._base_url = (base_url or const.BASE_URL).rstrip("/")
        self._logged_in = False

    @property
    def customer_code(self) -> str:
        """Return water customer code."""
        return self._customer_code

    @property
    def openid(self) -> str:
        """Return the OpenId from the mini program."""
        return self._openid

    @property
    def base_url(self) -> str:
        """Return API base URL."""
        return self._base_url

    @staticmethod
    def _random_header_value(length: int = 32) -> str:
        chars = string.digits + string.ascii_uppercase[:25]
        return "".join(secrets.choice(chars) for _ in range(length))

    @staticmethod
    def _make_key(header_value: str) -> str:
        if not header_value or len(header_value) < 24:
            raise ShenzhenWaterApiError(
                f"Invalid 04A52C9F header value: {header_value}"
            )

        return REQUEST_KEY_PREFIX + header_value[8:24] + REQUEST_KEY_SUFFIX

    @classmethod
    def _encrypt(cls, payload: dict[str, Any], header_value: str) -> str:
        key = cls._make_key(header_value)
        plain = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        cipher = AES.new(key.encode("utf-8"), AES.MODE_ECB)
        encrypted = cipher.encrypt(pad(plain.encode("utf-8"), AES.block_size))
        return base64.b64encode(encrypted).decode("utf-8")

    @classmethod
    def _decrypt(cls, text: str, header_value: str) -> dict[str, Any]:
        try:
            body = json.loads(text)
        except Exception:
            body = text.strip().strip('"')

        if not isinstance(body, str):
            raise ShenzhenWaterApiError("Encrypted response is not a string")

        body = re.sub(r"\s+", "", body)
        if len(body) <= 20:
            raise ShenzhenWaterApiError(f"Invalid encrypted response: {body}")

        cipher_text = body[:7] + body[20:] + body[7:20]
        cipher_text += "=" * (-len(cipher_text) % 4)
        raw = base64.b64decode(cipher_text)

        if len(raw) % AES.block_size != 0:
            raise ShenzhenWaterApiError(
                f"Invalid AES payload length: {len(raw)}"
            )

        key = cls._make_key(header_value)
        cipher = AES.new(key.encode("utf-8"), AES.MODE_ECB)
        plain = unpad(cipher.decrypt(raw), AES.block_size).decode("utf-8")

        try:
            return json.loads(plain)
        except json.JSONDecodeError as err:
            raise ShenzhenWaterApiError(f"Invalid decrypted JSON: {plain}") from err

    def _build_headers(
        self, header_value: str, *, include_token: bool = True
    ) -> dict[str, str]:
        return {
            "04A52C9F": header_value,
            "Accept": "*/*",
            "Channel": self._channel,
            "Content-Type": "application/json",
            "OpenId": self._openid,
            "Referer": mini_program_referer(),
            "TenantId": self._tenant_id,
            "User-Agent": USER_AGENT,
            "Utoken": self._utoken if include_token else "",
            "xweb_xhr": "1",
        }

    @staticmethod
    def _looks_like_auth_error(message: str) -> bool:
        lowered = message.lower()
        return any(
            keyword in lowered
            for keyword in (
                "utoken",
                "unauthorized",
                "token信息不合法",
                "token不合法",
                "登录失效",
                "未登录",
                "请登录",
                "9999904",
            )
        )

    async def _post(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        include_token: bool,
    ) -> dict[str, Any]:
        """Send one encrypted request and return the decrypted body."""
        url = f"{self._base_url}{path}"
        header_value = self._random_header_value()
        encrypted_payload = self._encrypt(payload, header_value)

        try:
            async with async_timeout.timeout(TIMEOUT):
                async with self._session.post(
                    url,
                    headers=self._build_headers(
                        header_value, include_token=include_token
                    ),
                    data=json.dumps(encrypted_payload),
                ) as resp:
                    text = await resp.text()
                    status = resp.status
                    response_header = resp.headers.get("04A52C9F")

        except ShenzhenWaterApiError:
            raise
        except Exception as err:
            raise ShenzhenWaterApiError(f"Request failed: {err}") from err

        # 401 一定是身份问题（OpenId / Utoken / TenantId），直接当成认证错误，
        # 这样上层可以重新登录而不是把它当成普通故障。
        if status == 401:
            raise ShenzhenWaterAuthError(
                f"{path} 认证失败（HTTP 401）: {text[:200]}"
            )

        if status != 200:
            message = f"HTTP {status}: {text[:300]}"
            if self._looks_like_auth_error(message):
                raise ShenzhenWaterAuthError(message)
            raise ShenzhenWaterApiError(message)

        if not text:
            # 空响应体：服务端接受了请求但没给数据（常见于 token 已过期、
            # 渠道/租户被拒）。归到认证错误，让上层重登一次再判断。
            raise ShenzhenWaterAuthError(
                f"{path} 返回空响应（可能是 Utoken 已失效）"
            )

        if not response_header:
            raise ShenzhenWaterApiError(
                f"Response header 04A52C9F not found: {text[:300]}"
            )

        return self._decrypt(text, response_header)

    async def _request(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        include_token: bool = True,
    ) -> dict[str, Any]:
        """Send encrypted request to Shenzhen Water mini-program API."""
        data = await self._post(path, payload, include_token=include_token)

        if data.get("code") not in (0, "0"):
            message = json.dumps(data, ensure_ascii=False)
            if self._looks_like_auth_error(message):
                raise ShenzhenWaterAuthError(message)
            raise ShenzhenWaterApiError(f"API error: {message}")

        return data

    async def async_login(self) -> dict[str, Any]:
        """Refresh mini-program token and GUID from OpenId."""
        # 登录接口本身失败时不能再抛 AuthError：那会让上层反复重试登录。
        # OpenId 被服务端拒绝 → OpenIdError（换 OpenId 才有用）；
        # 其它失败（网络、WAF）→ 普通 API 错误。
        try:
            data = await self._request(
                "/api/wechat/op/user/AutomaticLoginV20",
                {
                    "openid": self._openid,
                    "channel": self._channel,
                },
                include_token=False,
            )
        except ShenzhenWaterAuthError as err:
            raise ShenzhenWaterApiError(f"自动登录失败: {err}") from err
        except ShenzhenWaterApiError as err:
            if any(marker in str(err) for marker in _OPENID_INVALID_MARKERS):
                raise ShenzhenWaterOpenIdError(
                    f"OpenId 不被服务端识别，请重新抓取: {err}"
                ) from err
            raise

        login_data = data.get("data") or {}
        token = login_data.get("token")
        guid = login_data.get("guid")

        if not token or not guid:
            raise ShenzhenWaterApiError(
                f"自动登录未返回 token/guid: {data}"
            )

        self._utoken = str(token)
        self._guid = str(guid)
        self._logged_in = True
        return data

    async def _ensure_login(self) -> None:
        if not self._logged_in:
            await self.async_login()

    async def async_call(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        include_token: bool = True,
    ) -> dict[str, Any]:
        """Call a business endpoint, re-logging in once when the token expired.

        深圳水务的 Utoken 会过期（也可能被服务端主动踢掉），原来只在
        ``async_get_all`` 里重登一次，其它调用路径全都直接失败。
        统一放在这里，任何接口都能自愈。
        """
        await self._ensure_login()

        try:
            return await self._request(
                path, payload, include_token=include_token
            )
        except ShenzhenWaterAuthError as err:
            _LOGGER.debug("%s 认证失败，重新登录后重试: %s", path, err)

        self._logged_in = False
        await self.async_login()

        return await self._request(path, payload, include_token=include_token)

    def _base_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "channel": self._channel,
            "openid": self._openid,
            "guid": self._guid,
        }

        if self._guid in ("", None):
            payload.pop("guid")

        return payload

    async def async_get_users(self) -> dict[str, Any]:
        """Get bound water users."""
        return await self.async_call(
            "/api/wechat/op/user/GetUsersV20",
            {
                **self._base_payload(),
                "status": 0,
            },
        )

    async def async_get_latest_bill_details(self) -> dict[str, Any]:
        """Get latest bill details."""
        return await self.async_call(
            "/api/wechat/op/BillInfo/GetLatestBillDetails2V30",
            {
                **self._base_payload(),
                "customerType": "details",
                "customercodelist": [self._customer_code],
                "isLimitRequest": "1",
            },
        )

    async def async_get_bill_info(self, bill_month: int | None = None) -> dict[str, Any]:
        """Get bill info from the mini-program bill endpoint."""
        payload = {
            **self._base_payload(),
            "customerCodes": [self._customer_code],
        }
        if bill_month:
            payload["costdate"] = int(bill_month)

        return await self.async_call(
            "/api/wechat/op/user/billInfo/BillingInfoBycustomerCodesV30",
            payload,
        )

    async def async_get_all(self) -> dict[str, Any]:
        """Get all Shenzhen Water data.

        认证错误会由 ``async_call`` 自动重登重试；这里再失败就是真失败，
        直接往上抛，让 HA 实体进入 unavailable 而不是显示空值。
        """
        current = await self.async_get_latest_bill_details()

        current_rows = current.get("data") or []
        current_month = current_rows[0].get("costDate") if current_rows else None

        current_bill_info = {}
        try:
            current_bill_info = await self.async_get_bill_info(current_month)
        except ShenzhenWaterApiError:
            current_bill_info = {}

        bill_info_rows = current_bill_info.get("data") or []
        if bill_info_rows:
            current_month = bill_info_rows[0].get("costDate") or current_month

        previous: dict[str, Any] = {}
        previous_month = _previous_month(current_month)
        if previous_month:
            try:
                previous = await self.async_get_bill_info(previous_month)
            except ShenzhenWaterApiError:
                previous = {}

        return {
            "current": current,
            "current_bill_info": current_bill_info,
            "previous": previous,
        }


def _previous_month(current_month: Any) -> int | None:
    """Return the previous billing month as YYYYMM."""
    if not current_month:
        return None

    try:
        month = datetime.strptime(str(current_month), "%Y%m")
    except ValueError:
        _LOGGER.debug("无法解析账单月份: %s", current_month)
        return None

    year = month.year - 1 if month.month == 1 else month.year
    previous = 12 if month.month == 1 else month.month - 1

    return year * 100 + previous
