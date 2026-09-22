# SPDX-License-Identifier: Apache-2.0
# Copyright The Robinauts Authors

"""The inbound side: HTTP in, application calls out, responses back.

It translates and **decides nothing** (``docs/layout.md``): a route reads a
request, calls one application method and turns what comes back into a status,
a body, a cookie or a ``Location``. Every rule it appears to apply -- who may
sign in, whether a return target is safe, what an ID token is worth -- is
applied below it, and every service it uses is handed to it by the composition
root. It depends on ``robinauts.application`` and ``robinauts.domain`` and on
nothing else inside the package.

FastAPI, Starlette and Pydantic live here and in the composition root, and
nowhere else (``docs/specs/backend.md``, "Web"); an import-linter contract in
``backend/pyproject.toml`` says so and the test suite runs it.

What is here: the ``/auth`` routes and ``/health`` (``auth_routes``,
``web``), the cookies a sign-in uses (``cookies``), who is asking and what
each route needs of them (``access``), the checks every write passes before
anything reads it (``protection``), how an error crosses HTTP (``errors``),
and the shapes the JSON API sends (``schemas``).
"""

from robinauts.api.access import (
    FRAMEWORK_PATHS,
    NOT_SIGNED_IN,
    PERMISSION_ATTRIBUTE,
    ROUTE_LISTS,
    CurrentUser,
    check_declarations,
    current_user,
    local_access,
    permissions_asked,
    public,
    routes_of,
    signed_in,
    signing_in,
    undeclared,
    unknown_route_lists,
)
from robinauts.api.auth_routes import SIGN_IN_PAGE, UI_PATH, auth_router
from robinauts.api.cookies import (
    HOST_PREFIX,
    LOGIN_COOKIE,
    SESSION_COOKIE,
    clear_cookie,
    cookie_name,
    login_cookie,
    session_cookie,
    set_cookie,
)
from robinauts.api.errors import (
    GENERIC_DETAIL,
    INTERNAL_ERROR,
    MAX_DETAIL_CHARS,
    NOT_FOUND_DETAIL,
    NOT_FOUND_ERROR,
    QUIET_RUN_DETAIL,
    SIGN_IN_DETAIL,
    STATUS_OF,
    UNREADABLE_DETAIL,
    error_body,
    http_error_detail,
    http_error_name,
    install_handlers,
    refusal,
    status_of,
    unreadable_detail,
)
from robinauts.api.logs import MAX_SHOWN, shown
from robinauts.api.protection import (
    COOKIE_HEADER,
    CROSS_SITE_DETAIL,
    DECIDING_HEADERS,
    HOST_HEADER,
    LOOPBACK_DETAIL,
    MEDIA_TYPE_DETAIL,
    REPEATED_HEADER_DETAIL,
    SAFE_METHODS,
    SECURITY_HEADERS,
    SITE_ACCEPTED,
    WEBSOCKET_POLICY_VIOLATION,
    Refusal,
    RequestProtection,
    SecurityHeaders,
    refused,
    request_headers,
)
from robinauts.api.schemas import (
    ErrorResponse,
    HealthResponse,
    ProviderSummary,
    SessionResponse,
    UserSummary,
)
from robinauts.api.web import (
    API_VERSION,
    BOTH_WAYS,
    OPENAPI_URL,
    TITLE,
    Opening,
    create_api,
    openapi_document,
)
from robinauts.domain import MAX_CAUSES, MAX_FRAMES, chain, where

__all__ = [
    "API_VERSION",
    "BOTH_WAYS",
    "COOKIE_HEADER",
    "CROSS_SITE_DETAIL",
    "DECIDING_HEADERS",
    "FRAMEWORK_PATHS",
    "GENERIC_DETAIL",
    "HOST_HEADER",
    "HOST_PREFIX",
    "INTERNAL_ERROR",
    "LOGIN_COOKIE",
    "LOOPBACK_DETAIL",
    "MAX_CAUSES",
    "MAX_DETAIL_CHARS",
    "MAX_FRAMES",
    "MAX_SHOWN",
    "MEDIA_TYPE_DETAIL",
    "NOT_FOUND_DETAIL",
    "NOT_FOUND_ERROR",
    "NOT_SIGNED_IN",
    "OPENAPI_URL",
    "PERMISSION_ATTRIBUTE",
    "QUIET_RUN_DETAIL",
    "REPEATED_HEADER_DETAIL",
    "ROUTE_LISTS",
    "SAFE_METHODS",
    "SECURITY_HEADERS",
    "SESSION_COOKIE",
    "SIGN_IN_DETAIL",
    "SIGN_IN_PAGE",
    "SITE_ACCEPTED",
    "STATUS_OF",
    "TITLE",
    "UI_PATH",
    "UNREADABLE_DETAIL",
    "WEBSOCKET_POLICY_VIOLATION",
    "CurrentUser",
    "ErrorResponse",
    "HealthResponse",
    "Opening",
    "ProviderSummary",
    "Refusal",
    "RequestProtection",
    "SecurityHeaders",
    "SessionResponse",
    "UserSummary",
    "auth_router",
    "chain",
    "check_declarations",
    "clear_cookie",
    "cookie_name",
    "create_api",
    "current_user",
    "error_body",
    "http_error_detail",
    "http_error_name",
    "install_handlers",
    "local_access",
    "login_cookie",
    "openapi_document",
    "permissions_asked",
    "public",
    "refusal",
    "refused",
    "request_headers",
    "routes_of",
    "session_cookie",
    "set_cookie",
    "shown",
    "signed_in",
    "signing_in",
    "status_of",
    "undeclared",
    "unknown_route_lists",
    "unreadable_detail",
    "where",
]
