"""
API request handlers for account endpoints.

These endpoints modify and return data about the user account associated with the
session or API key making the requests.

"""
from typing import Union, List

from aiohttp.web import HTTPNoContent, Response
from aiohttp.web_exceptions import HTTPBadRequest
from aiohttp_pydantic import PydanticView
from aiohttp_pydantic.oas.typing import r200, r201, r204, r400, r401, r404

import virtool.http.auth
import virtool.http.routes
from virtool.account.oas import (
    EditAccountSchema,
    EditSettingsSchema,
    CreateKeysSchema,
    EditKeySchema,
    ResetPasswordSchema,
    CreateLoginSchema,
    AccountResponse,
    EditAccountResponse,
    AccountSettingsResponse,
    CreateAPIKeyResponse,
    APIKeyResponse,
    LoginResponse,
    AccountResetPasswordResponse,
    ListAPIKeysResponse,
)
from virtool.api.response import NotFound, json_response
from virtool.data.errors import ResourceError, ResourceNotFoundError
from virtool.data.utils import get_data_from_req
from virtool.http.policy import policy, PublicRoutePolicy
from virtool.http.utils import set_session_id_cookie, set_session_token_cookie

from virtool.users.checks import check_password_length
from virtool.users.oas import UpdateUserSchema


API_KEY_PROJECTION = {
    "_id": False,
    "user": False,
}
"""
A MongoDB projection to use when returning API key documents to clients.

The key should never be sent to client after its creation.
"""

routes = virtool.http.routes.Routes()
"""
A :class:`aiohttp.web.RouteTableDef` for account API routes.
"""


@routes.view("/account")
class AccountView(PydanticView):
    async def get(self) -> Union[r200[AccountResponse], r401]:
        """
        Get account.

        Retrieves the details for the account associated with the user agent.

        Status Codes:
            200: Successful Operation
            401: Requires Authorization
        """

        account = await get_data_from_req(self.request).account.get(
            self.request["client"].user_id
        )

        return json_response(account)

    async def patch(
        self, data: EditAccountSchema
    ) -> Union[r200[EditAccountResponse], r400, r401]:
        """
        Update account.

        Updates the account associated with the user agent.

        Provide a ``password`` to update the account password. The ``old_password`` must
        also be provided in the request.

        The ``email`` address is not currently used, but will be in future releases.

        Status Codes:
            200: Successful Operation
            400: Invalid old password
            400: Invalid input
            401: Requires Authorization
        """
        data_dict = data.dict(exclude_unset=True)

        if "password" in data_dict:
            error = await check_password_length(self.request, data.password)

            if error:
                raise HTTPBadRequest(text=error)

        try:
            account = await get_data_from_req(self.request).account.edit(
                self.request["client"].user_id, data
            )
        except ResourceError:
            raise HTTPBadRequest(text="Invalid credentials")

        return json_response(EditAccountResponse.parse_obj(account))


@routes.view("/account/settings")
class SettingsView(PydanticView):
    async def get(self) -> Union[r200[AccountSettingsResponse], r401]:
        """
        Get account settings.

        Retrieves the settings for the account associated with the user agent.

        Status Codes:
            200: Successful operation
            401: Requires authorization
        """
        account_settings = await get_data_from_req(self.request).account.get_settings(
            "settings", self.request["client"].user_id
        )

        return json_response(AccountSettingsResponse.parse_obj(account_settings))

    async def patch(
        self, data: EditSettingsSchema
    ) -> Union[r200[AccountSettingsResponse], r400, r401]:
        """
        Update account settings.

        Updates the settings of the account associated with the user agent.

        Status Codes:
            200: Successful operation
            400: Invalid input
            401: Requires Authorization
        """
        settings = await get_data_from_req(self.request).account.edit_settings(
            data, "settings", self.request["client"].user_id
        )

        return json_response(AccountSettingsResponse.parse_obj(settings))


@routes.view("/account/keys")
class KeysView(PydanticView):
    async def get(self) -> Union[r200[List[ListAPIKeysResponse]], r401]:
        """
        List API keys.

        Lists all API keys registered on the account associated with the user agent.

        Status Codes:
            200: Successful operation
            401: Requires authorization
        """
        keys = await get_data_from_req(self.request).account.get_keys(
            self.request["client"].user_id
        )

        return json_response(
            [ListAPIKeysResponse.parse_obj(key) for key in keys], status=200
        )

    async def post(
        self, data: CreateKeysSchema
    ) -> Union[r201[CreateAPIKeyResponse], r400, r401]:
        """
        Create an API key.

        Creates a new API key on the account associated with the user agent.

        The new key value is returned in the response. **This is the only response
        from the server that will ever include the key**.

        Status Codes:
            201: Successful operation
            400: Invalid input
            401: Requires authorization
        """
        raw, key = await get_data_from_req(self.request).account.create_key(
            data, self.request["client"].user_id
        )

        headers = {"Location": f"/account/keys/{key.id}"}

        key_dict = key.dict()

        key_dict["key"] = raw

        return json_response(
            CreateAPIKeyResponse.parse_obj(key_dict), headers=headers, status=201
        )

    async def delete(self) -> Union[r204, r401]:
        """
        Purge API keys

        Deletes all API keys registered for the account associated with the user agent.

        Status Codes:
            204: Successful operation
            401: Requires authorization
        """
        await get_data_from_req(self.request).account.delete_keys(
            self.request["client"].user_id
        )

        raise HTTPNoContent


@routes.view("/account/keys/{key_id}")
class KeyView(PydanticView):
    async def get(self) -> Union[r200[APIKeyResponse], r404]:
        """
        Get an API key.

        Retrieves the details for an API key registered on the account associated with
        the user agent.

        Status Codes:
            200: Successful operation
            404: Not found
        """
        try:
            key = await get_data_from_req(self.request).account.get_key(
                self.request["client"].user_id, self.request.match_info["key_id"]
            )
        except ResourceNotFoundError:
            raise NotFound()

        return json_response(APIKeyResponse.parse_obj(key), status=200)

    async def patch(
        self, data: EditKeySchema
    ) -> Union[r200[APIKeyResponse], r400, r401, r404]:
        """
        Update an API key.

        Updates the permissions an existing API key registered on the account
        associated with the user agent.

        Status Codes:
            200: Successful operation
            400: Invalid input
            401: Requires Authorization
            404: Not found
        """
        try:
            key = await get_data_from_req(self.request).account.edit_key(
                self.request["client"].user_id,
                self.request.match_info.get("key_id"),
                data,
            )
        except ResourceNotFoundError:
            raise NotFound()

        return json_response(APIKeyResponse.parse_obj(key))

    async def delete(self) -> Union[r204, r401, r404]:
        """
        Delete
        Remove an API key by its ID.

        Status Codes:
            204: Successful operation
            401: Requires authorization
            404: Not found
        """
        try:
            await get_data_from_req(self.request).account.delete_key(
                self.request["client"].user_id, self.request.match_info["key_id"]
            )
        except ResourceNotFoundError:
            raise NotFound()

        raise HTTPNoContent


@routes.view("/account/login")
class LoginView(PydanticView):
    @policy(PublicRoutePolicy)
    async def post(self, data: CreateLoginSchema) -> Union[r201[LoginResponse], r400]:
        """
        Login.

        Logs in using the passed credentials.

        This creates a new session for the user with `username`. The session ID and
        token are returned in cookies.

        Status Codes:
            201: Successful operation
            400: Invalid input
        """
        session_id = self.request.cookies.get("session_id")

        try:
            result = await get_data_from_req(self.request).account.login(
                session_id, data
            )
        except ResourceError:
            raise HTTPBadRequest(text="Invalid username or password")

        if type(result) is int:
            reset_code = result
            return json_response(
                {
                    "reset": True,
                    "reset_code": reset_code,
                },
                status=200,
            )

        user_id = result

        session, token = await virtool.users.sessions.replace_session(
            self.request.app["db"],
            session_id,
            virtool.http.auth.get_ip(self.request),
            user_id,
            data.remember,
        )

        resp = json_response({"reset": False}, status=201)

        set_session_id_cookie(resp, session["_id"])
        set_session_token_cookie(resp, token)

        return resp


@routes.view("/account/logout")
class LogoutView(PydanticView):
    @policy(PublicRoutePolicy)
    async def get(self) -> r204:
        """
        Logout.

        Logout the user by invalidating the session associated with the user agent. A
        new unauthenticated session ID is returned in cookies.

        Status Codes:
            204: Successful operation
        """
        session, _ = await get_data_from_req(self.request).account.logout(
            self.request.cookies.get("session_id"),
            virtool.http.auth.get_ip(self.request),
        )

        resp = Response(status=200)

        set_session_id_cookie(resp, session["_id"])
        resp.del_cookie("session_token")

        return resp


@routes.view("/account/reset")
class ResetView(PydanticView):
    @policy(PublicRoutePolicy)
    async def post(
        self, data: ResetPasswordSchema
    ) -> Union[r200[AccountResetPasswordResponse], r400]:
        """
        Reset password.

        Reset the password for the account associated with the requesting session.

        Status Codes:
            200: Successful operation
            400: Invalid input
        """
        if error := await check_password_length(self.request, data.password):
            raise HTTPBadRequest(text=error)

        status, user_id, reset = await get_data_from_req(self.request).account.reset(
            self.request.cookies.get("session_id"),
            data,
            virtool.http.auth.get_ip(self.request),
        )

        if status == 400:
            return json_response(
                {"error": error, "reset_code": reset},
                status=400,
            )

        new_session = status
        token = reset

        await get_data_from_req(self.request).users.update(
            user_id,
            UpdateUserSchema(force_reset=False, password=data.password),
        )

        try:
            self.request["client"].authorize(new_session, is_api=False)
        except AttributeError:
            pass

        resp = json_response({"login": False, "reset": False}, status=200)

        set_session_id_cookie(resp, new_session["_id"])
        set_session_token_cookie(resp, token)

        return resp
