import asyncio
from typing import Callable, Tuple

from aiohttp import BasicAuth, web
from aiohttp.web import Request, Response
from aiohttp.web_exceptions import HTTPUnauthorized
from jose import ExpiredSignatureError
from jose.exceptions import JWTClaimsError, JWTError

from virtool.data.utils import get_data_from_req
from virtool.errors import AuthError
from virtool.http.client import UserClient
from virtool.http.policy import (
    get_handler_policy,
    PublicRoutePolicy,
)
from virtool.http.utils import set_session_id_cookie
from virtool.oidc.utils import validate_token
from virtool.users.db import B2CUserAttributes
from virtool.users.sessions import clear_reset_code, create_session, get_session
from virtool.utils import hash_key


def get_ip(req: Request) -> str:
    """
    A convenience function for getting the client IP address from a
    :class:`~Request` object.

    :param req: the request
    :return: the client's IP address string

    """
    return req.transport.get_extra_info("peername")[0]


def decode_authorization(authorization: str) -> Tuple[str, str]:
    """
    Parse and decode an API key from an HTTP authorization header value.

    :param authorization: the authorization header value for an API request
    :return: the user id and API key parsed from the authorization header

    """
    try:
        auth = BasicAuth.decode(authorization)
    except ValueError as error:
        raise AuthError(str(error))

    return auth.login, auth.password


async def authenticate_with_key(req: Request, handler: Callable) -> Response:
    """
    Authenticate the request with an API key or job key.

    :param req: the request to authenticate
    :param handler: the handler to call with the request if authenticated

    """
    try:
        holder_id, key = decode_authorization(req.headers.get("AUTHORIZATION"))
    except AuthError:
        raise HTTPUnauthorized(text="Malformed Authorization header")

    return await authenticate_with_api_key(req, handler, holder_id, key)


async def authenticate_with_api_key(
    req: Request, handler: Callable, handle: str, key: str
) -> Response:
    db = req.app["db"]

    document, user = await asyncio.gather(
        db.keys.find_one({"_id": hash_key(key)}, ["permissions", "user"]),
        db.users.find_one(
            {"handle": handle}, ["administrator", "groups", "permissions"]
        ),
    )

    if not document or not user or document["user"]["id"] != user["_id"]:
        raise HTTPUnauthorized(text="Invalid authorization header")

    req["client"] = UserClient(
        db=db,
        administrator=user["administrator"],
        force_reset=False,
        groups=user["groups"],
        permissions=document["permissions"],
        user_id=user["_id"],
        authenticated=True,
    )

    return await handler(req)


async def authenticate_with_b2c(req: Request, handler: Callable) -> Response:
    """
    Authenticate requests when req.app["config"].use_b2c is True.

    If no id_token cookie is attached to request, redirect to /acquire_tokens

    If id_token cookie is found, attempt to validate to gather user information from
    claims. If token is expired, redirect to /refresh_tokens. If token is invalid for
    some other reason, redirect to /delete_tokens

    find or create user based on token claims, then populate req["cient"] with user
    information and return the response from the handler.

    :param req: the request to handle
    :param handler: the handler to call with the request if authenticated
    :return: the response
    """
    token = req.headers.get("bearer") or req.cookies.get("bearer")

    if token is None:
        raise HTTPUnauthorized(text="Invalid authorization")

    try:
        token_claims = await validate_token(req.app, token)
    except (JWTClaimsError, JWTError, ExpiredSignatureError):
        raise HTTPUnauthorized(text="Invalid authorization")

    user = await get_data_from_req(req).users.find_or_create_b2c_user(
        B2CUserAttributes(
            display_name=token_claims["name"],
            given_name=token_claims.get("given_name", ""),
            family_name=token_claims.get("family_name", ""),
            oid=token_claims["oid"],
        )
    )

    req["client"] = UserClient(
        db=req.app["db"],
        administrator=user.administrator,
        force_reset=False,
        groups=[group.id for group in user.groups],
        permissions=user.permissions.dict(),
        user_id=user.id,
        authenticated=True,
    )

    resp = await handler(req)
    resp.set_cookie("bearer", token, httponly=True, max_age=2600000)

    return resp


@web.middleware
async def middleware(req, handler) -> Response:
    """
    Handle requests based on client type and authentication status.

    :param req: the request to handle
    :param handler: the handler to call with the request if authenticated
    :return: the response
    """
    db = req.app["db"]

    if isinstance(get_handler_policy(handler, req.method), PublicRoutePolicy):
        req["client"] = UserClient(
            db=db,
            administrator=False,
            force_reset=False,
            groups=[],
            permissions={},
            user_id=None,
            authenticated=False,
        )

        return await handler(req)

    if req.headers.get("AUTHORIZATION"):
        return await authenticate_with_key(req, handler)

    if req.app["config"].use_b2c:
        try:
            return await authenticate_with_b2c(req, handler)
        except HTTPUnauthorized:
            # Allow authentication by both session and JWT in same instance.
            pass

    # Get session information from cookies.
    session_id = req.cookies.get("session_id")
    session_token = req.cookies.get("session_token")

    session, session_token = await get_session(db, session_id, session_token)

    ip = get_ip(req)

    if session is None:
        session, session_token = await create_session(db, ip)

    session_id = session["_id"]

    if session_token:
        req["client"] = UserClient(
            db,
            session["administrator"],
            session["force_reset"],
            session["groups"],
            session["permissions"],
            session["user"]["id"],
            authenticated=True,
            session_id=session_id,
        )

    else:
        req["client"] = UserClient(
            db=db,
            administrator=False,
            force_reset=False,
            groups=[],
            permissions={},
            user_id=None,
            authenticated=False,
        )

    resp = await handler(req)

    if req.path != "/account/reset":
        await clear_reset_code(db, session["_id"])

    set_session_id_cookie(resp, session_id)

    return resp
