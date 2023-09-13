"""
Database utilities for groups.

"""

import asyncio
from asyncio import gather
from typing import List, Optional

from motor.motor_asyncio import AsyncIOMotorClientSession
from virtool_core.models.group import Group
from virtool_core.models.user import UserNested
from virtool.groups.pg import SQLGroup
from virtool.pg.utils import get_row, get_row_by_id

import virtool.users.db
import virtool.utils
from virtool.groups.utils import merge_group_permissions
from virtool.utils import base_processor


async def fetch_complete_group(mongo, pg, group_id: str | int) -> Optional[Group]:
    """
    Search Mongo and Postgres for a Group by its ID.

    :param mongo: The MongoDB client
    :param pg: PostgreSQL AsyncEngine object
    :param group_id: ID to search group by
    """

    if type(group_id) is str:
        return await fetch_complete_group_by_legacy_id(mongo, pg, group_id)

    pg_group = await get_row_by_id(pg, SQLGroup, group_id)

    if pg_group:
        return Group(
            **{
                **pg_group.to_dict(),
                "id": pg_group.legacy_id,
                "users": await fetch_group_users(mongo, pg_group.legacy_id),
            }
        )


async def fetch_complete_group_by_legacy_id(
    mongo, pg, group_id: str
) -> Optional[Group]:
    """
    Search Mongo and Postgres for a Group by its legacy mongo id

    :param mongo: The MongoDB client
    :param pg: PostgreSQL AsyncEngine object
    :param group_id: ID to search group by
    """
    pg_group, mongo_group, users = await gather(
        get_row(pg, SQLGroup, ("legacy_id", group_id)),
        mongo.groups.find_one({"_id": group_id}),
        fetch_group_users(mongo, group_id),
    )

    if pg_group:
        group = pg_group.to_dict()
        group["id"] = pg_group.legacy_id
    else:
        group = mongo_group

    if group:
        group["users"] = users
        return Group(**group)


async def get_merged_permissions(mongo, id_list: List[str]) -> dict:
    """
    Get the merged permissions that are inherited as a result of membership in the groups defined in `id_list`.

    :param mongo: The MongoDB client
    :param id_list: a list of group ids
    :return: the merged permissions

    """
    groups = await asyncio.shield(
        mongo.groups.find({"_id": {"$in": id_list}}, {"_id": False}).to_list(None)
    )
    return merge_group_permissions(groups)


async def update_member_users(
    mongo,
    group_id: str,
    remove: bool = False,
    session: Optional[AsyncIOMotorClientSession] = None,
):
    groups = await mongo.groups.find({}, session=session).to_list(None)

    async for user in mongo.users.find(
        {"groups": group_id},
        ["administrator", "groups", "permissions", "primary_group"],
        session=session,
    ):
        if remove:
            user["groups"].remove(group_id)

        update_dict = {}

        if remove:
            update_dict["$pull"] = {"groups": group_id}

            if user["primary_group"] == group_id:
                update_dict["$set"]["primary_group"] = ""

        if update_dict:
            await mongo.users.find_one_and_update(
                {"_id": user["_id"]},
                update_dict,
                projection=["groups", "permissions"],
                session=session,
            )

        permissions = merge_group_permissions(
            [group for group in groups if group["_id"] in user["groups"]]
        )

        await virtool.users.db.update_keys(
            mongo,
            user["administrator"],
            user["_id"],
            user["groups"],
            permissions,
            session=session,
        )


async def fetch_group_users(mongo, group_id: str) -> List[UserNested]:
    return [
        UserNested(**base_processor(user))
        async for user in mongo.users.find({"groups": group_id})
    ]
