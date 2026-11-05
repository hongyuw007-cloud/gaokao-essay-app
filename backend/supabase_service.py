# -*- coding: utf-8 -*-
"""Supabase Auth and PostgREST helpers for the multi-user experience."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

import httpx


class SupabaseConfigurationError(RuntimeError):
    """Raised when Supabase environment variables are unavailable."""


class SupabaseAPIError(RuntimeError):
    """A sanitized error returned by Supabase."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str
    metadata: dict[str, Any] = field(default_factory=dict)


def is_configured() -> bool:
    return bool(_base_url() and os.getenv("SUPABASE_ANON_KEY", "").strip())


def _base_url() -> str:
    return os.getenv("SUPABASE_URL", "").strip().rstrip("/")


def _anon_key() -> str:
    return os.getenv("SUPABASE_ANON_KEY", "").strip()


def _require_configuration() -> tuple[str, str]:
    url = _base_url()
    key = _anon_key()
    if not url or not key:
        raise SupabaseConfigurationError(
            "未配置 SUPABASE_URL 和 SUPABASE_ANON_KEY，请先完成 Supabase 配置"
        )
    return url, key


def _headers(
    token: str | None = None,
    *,
    prefer: str | None = None,
) -> dict[str, str]:
    _, anon_key = _require_configuration()
    headers = {
        "apikey": anon_key,
        "Authorization": f"Bearer {token or anon_key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:300] or "Supabase 请求失败"

    if isinstance(payload, dict):
        for key in ("msg", "message", "error_description", "error", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        return str(payload)[:300]
    return str(payload)[:300]


def _request(
    method: str,
    path: str,
    *,
    token: str | None = None,
    json: Any = None,
    params: dict[str, str] | None = None,
    prefer: str | None = None,
) -> Any:
    base_url, _ = _require_configuration()
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.request(
                method,
                f"{base_url}{path}",
                headers=_headers(token, prefer=prefer),
                json=json,
                params=params,
            )
    except httpx.RequestError as exc:
        raise SupabaseAPIError(502, f"无法连接 Supabase：{exc}") from exc

    if response.status_code >= 400:
        raise SupabaseAPIError(response.status_code, _error_detail(response))
    if response.status_code == 204 or not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return response.text


def _user_from_payload(payload: dict[str, Any]) -> AuthUser:
    user_data = payload.get("user") if isinstance(payload.get("user"), dict) else payload
    metadata = user_data.get("user_metadata") or user_data.get("data") or {}
    return AuthUser(
        id=str(user_data.get("id", "")),
        email=str(user_data.get("email", "")),
        metadata=metadata if isinstance(metadata, dict) else {},
    )


def _session_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if "access_token" not in payload:
        return {
            "authenticated": False,
            "requires_confirmation": True,
            "user": _user_from_payload(payload),
        }

    return {
        "authenticated": True,
        "access_token": payload["access_token"],
        "refresh_token": payload.get("refresh_token", ""),
        "expires_in": payload.get("expires_in"),
        "token_type": payload.get("token_type", "bearer"),
        "user": _user_from_payload(payload),
    }


def sign_up(
    email: str,
    password: str,
    metadata: dict[str, str],
    *,
    redirect_to: str | None = None,
) -> dict[str, Any]:
    payload = _request(
        "POST",
        "/auth/v1/signup",
        params={"redirect_to": redirect_to} if redirect_to else None,
        json={"email": email, "password": password, "data": metadata},
    )
    return _session_payload(payload)


def sign_in(email: str, password: str) -> dict[str, Any]:
    payload = _request(
        "POST",
        "/auth/v1/token",
        params={"grant_type": "password"},
        json={"email": email, "password": password},
    )
    return _session_payload(payload)


def refresh_session(refresh_token: str) -> dict[str, Any]:
    payload = _request(
        "POST",
        "/auth/v1/token",
        params={"grant_type": "refresh_token"},
        json={"refresh_token": refresh_token},
    )
    return _session_payload(payload)


def sign_out(token: str) -> None:
    _request("POST", "/auth/v1/logout", token=token)


def get_user(token: str) -> AuthUser:
    payload = _request("GET", "/auth/v1/user", token=token)
    if not isinstance(payload, dict):
        raise SupabaseAPIError(502, "Supabase 返回了无效的用户信息")
    user = _user_from_payload(payload)
    if not user.id:
        raise SupabaseAPIError(401, "登录凭证无效")
    return user


def update_user(token: str, metadata: dict[str, str]) -> AuthUser:
    payload = _request(
        "PUT",
        "/auth/v1/user",
        token=token,
        json={"data": metadata},
    )
    if not isinstance(payload, dict):
        raise SupabaseAPIError(502, "Supabase 返回了无效的用户信息")
    return _user_from_payload(payload)


def list_essays(token: str) -> list[dict[str, Any]]:
    payload = _request(
        "GET",
        "/rest/v1/essays",
        token=token,
        params={
            "select": (
                "id,user_id,topic,title,essay,word_count,"
                "is_favorite,created_at"
            ),
            "order": "created_at.desc",
            "limit": "100",
        },
    )
    return payload if isinstance(payload, list) else []


def create_essay(
    token: str,
    *,
    user_id: str,
    topic: str,
    title: str,
    essay: str,
    word_count: int,
) -> dict[str, Any]:
    payload = _request(
        "POST",
        "/rest/v1/essays",
        token=token,
        prefer="return=representation",
        json={
            "user_id": user_id,
            "topic": topic,
            "title": title,
            "essay": essay,
            "word_count": word_count,
            "is_favorite": False,
        },
    )
    if not isinstance(payload, list) or not payload:
        raise SupabaseAPIError(502, "作文已生成，但保存记录时未返回数据")
    return payload[0]


def update_essay(
    token: str,
    *,
    essay_id: str,
    user_id: str,
    is_favorite: bool,
) -> dict[str, Any]:
    safe_id = quote(essay_id, safe="")
    safe_user = quote(user_id, safe="")
    payload = _request(
        "PATCH",
        "/rest/v1/essays",
        token=token,
        prefer="return=representation",
        params={"id": f"eq.{safe_id}", "user_id": f"eq.{safe_user}"},
        json={"is_favorite": is_favorite},
    )
    if not isinstance(payload, list) or not payload:
        raise SupabaseAPIError(404, "未找到该作文记录")
    return payload[0]


def delete_essay(token: str, *, essay_id: str, user_id: str) -> None:
    safe_id = quote(essay_id, safe="")
    safe_user = quote(user_id, safe="")
    _request(
        "DELETE",
        "/rest/v1/essays",
        token=token,
        prefer="return=minimal",
        params={"id": f"eq.{safe_id}", "user_id": f"eq.{safe_user}"},
    )
