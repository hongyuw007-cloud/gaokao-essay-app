# -*- coding: utf-8 -*-
"""
《生成式人工智能》实验1：高考满分作文智能应用 —— 后端
技术栈：FastAPI + OpenAI SDK + Supabase Auth/PostgREST
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel, Field

load_dotenv()

try:
    from .prompt import (
        SYSTEM_PROMPT,
        build_length_revision_prompt,
        build_user_prompt,
    )
    from .supabase_service import (
        AuthUser,
        SupabaseAPIError,
        SupabaseConfigurationError,
        create_essay,
        delete_essay,
        get_user,
        is_configured,
        list_essays,
        refresh_session,
        sign_in,
        sign_out,
        sign_up,
        update_essay,
        update_user,
    )
except ImportError:  # Supports `cd backend && uvicorn main:app`.
    from prompt import SYSTEM_PROMPT, build_length_revision_prompt, build_user_prompt
    from supabase_service import (
        AuthUser,
        SupabaseAPIError,
        SupabaseConfigurationError,
        create_essay,
        delete_essay,
        get_user,
        is_configured,
        list_essays,
        refresh_session,
        sign_in,
        sign_out,
        sign_up,
        update_essay,
        update_user,
    )


API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
PUBLIC_APP_URL = os.getenv("PUBLIC_APP_URL", "").strip().rstrip("/")

client = OpenAI(api_key=API_KEY or "not-configured", base_url=BASE_URL)

app = FastAPI(title="高考满分作文智能应用", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=500)
    material: str = Field(default="", max_length=4000)
    genre: Literal["auto", "argumentative", "narrative"] = "auto"
    target_word_count: int = Field(default=800, ge=600, le=1200)


class AuthRequest(BaseModel):
    action: Literal["register", "login", "refresh", "logout"]
    email: str = ""
    password: str = ""
    refresh_token: str = ""
    name: str = Field(default="", max_length=40)
    class_name: str = Field(default="", max_length=60)
    student_id: str = Field(default="", max_length=40)


class ProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    class_name: str = Field(min_length=1, max_length=60)
    student_id: str = Field(min_length=1, max_length=40)


class EssayPatchRequest(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    is_favorite: bool


class EssayCreateRequest(BaseModel):
    topic: str = Field(min_length=1, max_length=500)
    essay: str = Field(min_length=1, max_length=20000)


@dataclass(frozen=True)
class AuthContext:
    user: AuthUser
    token: str


def _service_error(exc: Exception) -> HTTPException:
    if isinstance(exc, SupabaseConfigurationError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, SupabaseAPIError):
        safe_statuses = {400, 401, 403, 404, 409, 422, 429}
        status_code = exc.status_code if exc.status_code in safe_statuses else 502
        return HTTPException(status_code=status_code, detail=exc.detail)
    return HTTPException(status_code=502, detail="Supabase 服务暂时不可用")


def _metadata(user: AuthUser) -> dict[str, str]:
    metadata = user.metadata
    return {
        "name": str(metadata.get("name", "")),
        "class_name": str(metadata.get("class_name", "")),
        "student_id": str(metadata.get("student_id", "")),
    }


def _public_user(user: AuthUser) -> dict[str, object]:
    metadata = _metadata(user)
    return {
        "id": user.id,
        "email": user.email,
        "name": metadata["name"],
        "class_name": metadata["class_name"],
        "student_id": metadata["student_id"],
    }


def _get_auth_context(authorization: str | None) -> AuthContext:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="请先登录")
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="登录凭证为空")
    try:
        user = get_user(token)
    except (SupabaseConfigurationError, SupabaseAPIError) as exc:
        raise _service_error(exc) from exc
    return AuthContext(user=user, token=token)


def current_auth(
    authorization: str | None = Header(default=None),
) -> AuthContext:
    return _get_auth_context(authorization)


def _normalize_public_session(payload: dict[str, object]) -> dict[str, object]:
    result = dict(payload)
    user = result.get("user")
    if isinstance(user, AuthUser):
        result["user"] = _public_user(user)
    return result


def _clean_email(email: str) -> str:
    value = email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        raise HTTPException(status_code=422, detail="请输入有效的邮箱地址")
    return value


def _validate_password(password: str) -> str:
    if len(password) < 6:
        raise HTTPException(status_code=422, detail="密码至少需要 6 位")
    return password


def _title_from_essay(essay: str) -> str:
    for line in essay.splitlines():
        text = line.strip()
        if text:
            match = re.search(r"《([^》]{1,30})》", text)
            return match.group(1) if match else text[:30]
    return "未命名作文"


def _count_words(text: str) -> int:
    """Count occupied composition-grid cells; whitespace does not occupy a cell."""
    return len(re.findall(r"\S", text))


def _word_check(actual: int, target: int) -> dict[str, int | bool | str]:
    """Return a deterministic check instead of relying on model self-reporting."""
    minimum = max(1, target - 50)
    maximum = target + 50
    if actual < minimum:
        status = "short"
    elif actual > maximum:
        status = "long"
    else:
        status = "ok"
    return {
        "target": target,
        "actual": actual,
        "minimum": minimum,
        "maximum": maximum,
        "difference": actual - target,
        "passed": status == "ok",
        "status": status,
    }


def _parse_model_output(content: str) -> tuple[dict[str, str] | None, str]:
    """Split the learning-oriented strategy summary from the saved essay."""
    text = content.strip()
    strategy_marker = "【写作策略】"
    essay_marker = "【作文正文】"
    if essay_marker not in text:
        return None, text

    strategy_block, essay = text.split(essay_marker, 1)
    essay = essay.strip()
    if not essay:
        return None, text
    if strategy_marker not in strategy_block:
        return None, essay
    strategy_block = strategy_block.split(strategy_marker, 1)[1].strip()

    labels = {
        "central_idea": "中心立意",
        "genre": "文体选择",
        "structure": "结构方式",
        "advice": "写作建议",
    }
    strategy: dict[str, str] = {}
    for line in strategy_block.splitlines():
        clean_line = line.strip()
        for key, label in labels.items():
            match = re.match(rf"^{re.escape(label)}[：:]\s*(.+)$", clean_line)
            if match:
                strategy[key] = match.group(1).strip()
                break

    if not strategy:
        return None, essay
    return strategy, essay


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "model": MODEL,
        "deepseek_configured": bool(API_KEY),
        "supabase_configured": is_configured(),
    }


@app.get("/api/config")
def public_config() -> dict[str, object]:
    return {
        "model": MODEL,
        "supabase_configured": is_configured(),
        "deepseek_configured": bool(API_KEY),
    }


@app.post("/api/auth")
def auth_action(
    req: AuthRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    try:
        if req.action == "register":
            email = _clean_email(req.email)
            password = _validate_password(req.password)
            name = req.name.strip()
            class_name = req.class_name.strip()
            student_id = req.student_id.strip()
            if not name or not class_name or not student_id:
                raise HTTPException(
                    status_code=422,
                    detail="姓名、班级和学号均不能为空",
                )
            payload = sign_up(
                email,
                password,
                {
                    "name": name,
                    "class_name": class_name,
                    "student_id": student_id,
                },
                redirect_to=f"{PUBLIC_APP_URL}/" if PUBLIC_APP_URL else None,
            )
            return _normalize_public_session(payload)

        if req.action == "login":
            return _normalize_public_session(
                sign_in(_clean_email(req.email), _validate_password(req.password))
            )

        if req.action == "refresh":
            if not req.refresh_token.strip():
                raise HTTPException(status_code=422, detail="缺少刷新凭证")
            return _normalize_public_session(
                refresh_session(req.refresh_token.strip())
            )

        context = _get_auth_context(authorization)
        sign_out(context.token)
        return {"authenticated": False}
    except (SupabaseConfigurationError, SupabaseAPIError) as exc:
        raise _service_error(exc) from exc


@app.get("/api/profile")
def get_profile(auth: AuthContext = Depends(current_auth)) -> dict[str, object]:
    return {"user": _public_user(auth.user)}


@app.put("/api/profile")
def save_profile(
    req: ProfileRequest,
    auth: AuthContext = Depends(current_auth),
) -> dict[str, object]:
    metadata = {
        "name": req.name.strip(),
        "class_name": req.class_name.strip(),
        "student_id": req.student_id.strip(),
    }
    try:
        user = update_user(auth.token, metadata)
    except (SupabaseConfigurationError, SupabaseAPIError) as exc:
        raise _service_error(exc) from exc
    return {"user": _public_user(user)}


@app.post("/api/generate")
def generate(
    req: GenerateRequest,
    auth: AuthContext = Depends(current_auth),
) -> dict[str, object]:
    """Generate an essay, then persist it under the authenticated user."""
    if not API_KEY:
        raise HTTPException(
            status_code=500,
            detail="未配置 DEEPSEEK_API_KEY，请在 .env 文件中填写",
        )

    topic = req.topic.strip()
    material = req.material.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="作文题目不能为空")

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_user_prompt(
                        topic,
                        material=material,
                        genre=req.genre,
                        target_word_count=req.target_word_count,
                    ),
                },
            ],
            temperature=0.8,
            max_tokens=2048,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"调用大模型失败：{exc}") from exc

    model_output = response.choices[0].message.content or ""
    if not model_output.strip():
        raise HTTPException(status_code=502, detail="大模型未返回作文内容")

    strategy, essay = _parse_model_output(model_output)

    actual_word_count = _count_words(essay)
    word_check = _word_check(actual_word_count, req.target_word_count)

    length_revision: dict[str, object] = {
        "attempted": False,
        "applied": False,
        "before": actual_word_count,
        "after": actual_word_count,
        "attempts": [],
    }
    revision_warning = None
    if not word_check["passed"]:
        length_revision["attempted"] = True
        attempts = length_revision["attempts"]
        assert isinstance(attempts, list)
        for attempt_number in range(1, 3):
            if word_check["passed"]:
                break
            before_revision = actual_word_count
            attempt_info: dict[str, object] = {
                "number": attempt_number,
                "before": before_revision,
                "applied": False,
            }
            try:
                revision_response = client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "你负责对高考作文进行有限的篇幅调整。"
                                "必须保留原文核心内容，并且只返回修订后的完整正文。"
                            ),
                        },
                        {
                            "role": "user",
                            "content": build_length_revision_prompt(
                                topic,
                                essay,
                                actual_word_count=actual_word_count,
                                target_word_count=req.target_word_count,
                                minimum_word_count=int(word_check["minimum"]),
                                maximum_word_count=int(word_check["maximum"]),
                            ),
                        },
                    ],
                    temperature=0.5,
                    max_tokens=2048,
                )
                revision_output = revision_response.choices[0].message.content or ""
                _, revised_essay = _parse_model_output(revision_output)
                revised_word_count = _count_words(revised_essay)
                revised_check = _word_check(revised_word_count, req.target_word_count)
                attempt_info["candidate"] = revised_word_count
                attempt_info["status"] = revised_check["status"]
                is_closer = abs(revised_word_count - req.target_word_count) < abs(
                    actual_word_count - req.target_word_count
                )
                if revised_essay.strip() and (revised_check["passed"] or is_closer):
                    essay = revised_essay
                    actual_word_count = revised_word_count
                    word_check = revised_check
                    attempt_info["applied"] = True
                    length_revision["applied"] = True
                    length_revision["after"] = actual_word_count
            except Exception:  # noqa: BLE001
                attempt_info["status"] = "model_call_failed"
            attempts.append(attempt_info)

        if not word_check["passed"]:
            revision_warning = "作文已生成，但两次自动调整后字数仍未达到程序要求"

    record = None
    warning = revision_warning
    try:
        record = create_essay(
            auth.token,
            user_id=auth.user.id,
            topic=topic,
            title=_title_from_essay(essay),
            essay=essay,
            word_count=actual_word_count,
        )
    except (SupabaseConfigurationError, SupabaseAPIError) as exc:
        save_warning = f"作文已生成，但保存到历史记录失败：{exc.detail}"
        warning = f"{warning}；{save_warning}" if warning else save_warning

    return {
        "essay": essay,
        "record": record,
        "saved": record is not None,
        "warning": warning,
        "writing_requirements": {
            "material_provided": bool(material),
            "genre": req.genre,
            "target_word_count": req.target_word_count,
        },
        "word_check": word_check,
        "length_revision": length_revision,
        "strategy": strategy,
    }


@app.get("/api/essays")
def essays(auth: AuthContext = Depends(current_auth)) -> dict[str, object]:
    try:
        rows = list_essays(auth.token)
    except (SupabaseConfigurationError, SupabaseAPIError) as exc:
        raise _service_error(exc) from exc
    return {"items": rows}


@app.post("/api/essays")
def save_existing_essay(
    req: EssayCreateRequest,
    auth: AuthContext = Depends(current_auth),
) -> dict[str, object]:
    """Persist an already generated essay without calling the model again."""
    topic = req.topic.strip()
    essay = req.essay.strip()
    if not topic or not essay:
        raise HTTPException(status_code=422, detail="作文题目和正文不能为空")
    try:
        row = create_essay(
            auth.token,
            user_id=auth.user.id,
            topic=topic,
            title=_title_from_essay(essay),
            essay=essay,
            word_count=_count_words(essay),
        )
    except (SupabaseConfigurationError, SupabaseAPIError) as exc:
        raise _service_error(exc) from exc
    return {"record": row}


@app.patch("/api/essays")
def patch_essay(
    req: EssayPatchRequest,
    auth: AuthContext = Depends(current_auth),
) -> dict[str, object]:
    try:
        row = update_essay(
            auth.token,
            essay_id=req.id,
            user_id=auth.user.id,
            is_favorite=req.is_favorite,
        )
    except (SupabaseConfigurationError, SupabaseAPIError) as exc:
        raise _service_error(exc) from exc
    return {"record": row}


@app.delete("/api/essays")
def remove_essay(
    id: str,
    auth: AuthContext = Depends(current_auth),
) -> dict[str, object]:
    try:
        delete_essay(auth.token, essay_id=id, user_id=auth.user.id)
    except (SupabaseConfigurationError, SupabaseAPIError) as exc:
        raise _service_error(exc) from exc
    return {"deleted": True}


# Local development also serves the frontend. Vercel serves `frontend/` directly.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
