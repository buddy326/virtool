from typing import Union, Tuple, List

from virtool_core.models.account import Account
from virtool_core.models.account import AccountSettings, APIKey

import virtool.utils
from virtool.account.api import API_KEY_PROJECTION
from virtool.account.db import compose_password_update, ACCOUNT_PROJECTION
from virtool.account.oas import (
    EditSettingsSchema,
    CreateKeysSchema,
    EditKeySchema,
    ResetPasswordSchema,
    CreateLoginSchema,
    EditAccountSchema,
)
from virtool.data.errors import ResourceError, ResourceNotFoundError
from virtool.mongo.core import DB
from virtool.mongo.utils import get_one_field
from virtool.users.db import validate_credentials
from virtool.users.sessions import create_reset_code, replace_session
from virtool.users.utils import limit_permissions

PROJECTION = (
    "_id",
    "handle",
    "administrator",
    "email",
    "groups",
    "last_password_change",
    "permissions",
    "primary_group",
    "settings",
    "force_reset",
)


class AccountData:
    def __init__(self, db: DB):
        self._db = db

    async def get(self, user_id: str) -> Account:
        """
        Find complete user document.

        :param user_id: the user ID
        :return: the user account
        """
        document = await self._db.users.find_one(user_id, PROJECTION)

        document["primary_group"] = {"id": document["primary_group"]}

        return Account(**document)

    async def edit(self, user_id: str, data: EditAccountSchema) -> Account:
        """
        Edit the user account.

        :param user_id: the user ID
        :param data: the update to the account
        :return: the user account
        """
        update = {}

        data_dict = data.dict(exclude_unset=True)

        if "password" in data_dict:

            if not await validate_credentials(
                self._db, user_id, data_dict["old_password"] or ""
            ):
                raise ResourceError("Invalid credentials")

            update = compose_password_update(data_dict["password"])

        if "email" in data_dict:
            update["email"] = data_dict["email"]

        if update:
            document = await self._db.users.find_one_and_update(
                {"_id": user_id},
                {"$set": update},
                projection=ACCOUNT_PROJECTION,
            )
        else:
            document = await self._db.users.find_one(user_id, PROJECTION)

        document["primary_group"] = {"id": document["primary_group"]}

        return Account(**document)

    async def get_settings(self, query_field: str, user_id: str) -> AccountSettings:
        """
        Gets account settings.

        :param query_field: the field to get
        :param user_id: the user ID
        :return: the account settings
        """
        settings = await get_one_field(self._db.users, query_field, user_id)

        return AccountSettings(**settings)

    async def edit_settings(
        self, data: EditSettingsSchema, query_field: str, user_id: str
    ) -> AccountSettings:
        """
        Edits account settings.

        :param data: the update to the account settings
        :param query_field: the field to edit
        :param user_id: the user ID
        :return: the account settings
        """
        settings_from_db = await get_one_field(self._db.users, query_field, user_id)

        data_dict = data.dict(exclude_unset=True)

        settings = {**settings_from_db, **data_dict}

        await self._db.users.update_one({"_id": user_id}, {"$set": settings})

        return AccountSettings(**settings)

    async def get_keys(self, user_id: str) -> List[APIKey]:
        """
        Gets API keys associated with the authenticated user account.

        :param user_id: the user ID
        :return: the api keys
        """
        cursor = self._db.keys.find({"user.id": user_id}, API_KEY_PROJECTION)

        return [APIKey(**d) async for d in cursor]

    async def create_key(
        self, data: CreateKeysSchema, user_id: str
    ) -> Tuple[str, APIKey]:
        """
        Create a new API key.

        :param data: the fields to create a new API key
        :param user_id: the user ID
        :return: the API key
        """
        permissions_dict = data.permissions.dict(exclude_unset=True)

        user = await self._db.users.find_one(
            user_id, ["administrator", "groups", "permissions"]
        )

        key_permissions = {
            **virtool.users.utils.generate_base_permissions(),
            **permissions_dict,
        }

        if not user["administrator"]:
            key_permissions = virtool.users.utils.limit_permissions(
                key_permissions, user["permissions"]
            )

        raw, hashed = virtool.utils.generate_key()

        document = {
            "_id": hashed,
            "id": await virtool.account.db.get_alternate_id(self._db, data.name),
            "administrator": user["administrator"],
            "name": data.name,
            "groups": user["groups"],
            "permissions": key_permissions,
            "created_at": virtool.utils.timestamp(),
            "user": {"id": user_id},
        }

        await self._db.keys.insert_one(document)

        del document["_id"]
        del document["user"]

        return raw, APIKey(**document)

    async def delete_keys(self, user_id: str):
        """
        Delete all API keys for the account associated with the requesting session.

        :param user_id: the user ID
        """
        await self._db.keys.delete_many({"user.id": user_id})

    async def get_key(self, user_id: str, key_id: str) -> APIKey:
        """
        Get the complete representation of the API key identified by the `key_id`.

        :param user_id: the user ID
        :param key_id: the ID of the API key to get
        :return: the API key
        """
        document = await self._db.keys.find_one(
            {"id": key_id, "user.id": user_id}, API_KEY_PROJECTION
        )

        if document is None:
            raise ResourceNotFoundError()

        return APIKey(**document)

    async def edit_key(self, user_id: str, key_id: str, data: EditKeySchema) -> APIKey:
        """
        Change the permissions for an existing API key.

        :param user_id: the user ID
        :param key_id: the ID of the API key to update
        :param data: permissions update
        :return: the API key
        """
        if data.permissions is None:
            permissions_update = {}
        else:
            permissions_update = data.permissions.dict(exclude_unset=True)

        if not await self._db.keys.count_documents({"id": key_id}):
            raise ResourceNotFoundError()

        user = await self._db.users.find_one(user_id, ["administrator", "permissions"])

        # The permissions currently assigned to the API key.
        permissions = await get_one_field(
            self._db.keys, "permissions", {"id": key_id, "user.id": user_id}
        )

        permissions.update(permissions_update)

        if not user["administrator"]:
            permissions = limit_permissions(permissions, user["permissions"])

        document = await self._db.keys.find_one_and_update(
            {"id": key_id},
            {"$set": {"permissions": permissions}},
            projection=API_KEY_PROJECTION,
        )

        return APIKey(**document)

    async def delete_key(self, user_id: str, key_id: str):
        """
        Delete an API key by its id.

        :param user_id: the user ID
        :param key_id: the ID of the API key to delete
        """
        delete_result = await self._db.keys.delete_one(
            {"id": key_id, "user.id": user_id}
        )

        if delete_result.deleted_count == 0:
            raise ResourceNotFoundError()

    async def login(self, session_id: str, data: CreateLoginSchema) -> Union[int, str]:
        """
        Create a new session for the user with `username`.

        :param session_id: the login session ID
        :param data: the login data
        """
        # When `remember` is set, the session will last for 1 month instead of the
        # 1-hour default

        # Re-render the login page with an error message if the username doesn't
        # correlate to a user_id value in
        # the database and/or password are invalid.
        document = await self._db.users.find_one({"handle": data.username})

        if not document or not await validate_credentials(
            self._db, document["_id"], data.password
        ):
            raise ResourceError()

        user_id = document["_id"]

        if await get_one_field(self._db.users, "force_reset", user_id):
            return await create_reset_code(self._db, session_id, user_id, data.remember)

        return user_id

    async def logout(self, old_session_id: str, ip: str) -> Tuple[dict, str]:
        """
        Invalidates the requesting session, effectively logging out the user.

        :param old_session_id: the ID of the old session
        :param ip: the ip
        :return: the
        """
        return await replace_session(self._db, old_session_id, ip)

    async def reset(self, session_id, data: ResetPasswordSchema, ip: str):
        """
        Resets the password for a session user.

        :param session_id: the ID of the session to reset
        :param data: the data needed to reset session
        :param ip: the ip
        """

        reset_code = data.reset_code

        session = await self._db.sessions.find_one(session_id)

        user_id = session["reset_user_id"]

        if (
            not session.get("reset_code")
            or not session.get("reset_user_id")
            or reset_code != session.get("reset_code")
        ):
            return (
                400,
                user_id,
                await create_reset_code(self._db, session_id, user_id=user_id),
            )

        new_session, token = await replace_session(
            self._db,
            session_id,
            ip,
            user_id,
            remember=session.get("reset_remember", False),
        )

        return new_session, user_id, token
