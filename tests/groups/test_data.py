import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from virtool.authorization.client import AuthorizationClient
from virtool.data.errors import ResourceConflictError, ResourceNotFoundError
from virtool.groups.data import GroupsData
from virtool.groups.oas import UpdateGroupRequest
from virtool.groups.pg import SQLGroup
from virtool.mongo.core import Mongo
from virtool.pg.utils import get_row_by_id


@pytest.fixture
def groups_data(authorization_client, mongo, pg):
    return GroupsData(authorization_client, mongo, pg)


async def test_create(
    groups_data: GroupsData,
    mongo: Mongo,
    pg: AsyncEngine,
    snapshot,
):
    group = await groups_data.create("test")
    row = await get_row_by_id(pg, SQLGroup, 1)
    doc = await mongo.groups.find_one()

    assert doc == snapshot(name="mongo")
    assert row == snapshot(name="pg")

    assert doc["name"] == group.name == row.name
    assert doc["permissions"] == group.permissions == row.permissions
    assert doc["_id"] == group.id == row.legacy_id


class TestGet:
    async def test_get(self, groups_data: GroupsData, fake2, snapshot):
        """
        Ensure the correct group is returned when passed an postgres integer ID
        """
        await fake2.groups.create()

        assert await groups_data.get(1) == snapshot

    async def test_legacy_id(self, groups_data: GroupsData, fake2, snapshot):
        """
        Ensure the correct group is returned when passed a legacy mongo id
        """
        group = await fake2.groups.create()

        assert await groups_data.get(group.id) == snapshot

    async def test_user(self, groups_data: GroupsData, fake2, snapshot):
        """
        Ensure that users are correctly attached to the returned groups
        """
        group = await fake2.groups.create()

        await fake2.users.create(groups=[group])

        assert await groups_data.get(1) == snapshot

    @pytest.mark.parametrize("group_id", ["group_dne", 0xBEEF])
    async def test_group_dne(self, groups_data: GroupsData, group_id: str | int):
        """
        Ensure the correct exception is raised when the group does not exist
        using either a postgres or mongo id
        """
        with pytest.raises(ResourceNotFoundError):
            await groups_data.get(group_id)


async def test_create_duplicate(groups_data: GroupsData):
    group = await groups_data.create("test")

    with pytest.raises(ResourceConflictError):
        await groups_data.create(group.name)


async def test_update_name(
    authorization_client: AuthorizationClient,
    groups_data: GroupsData,
    mongo: Mongo,
    pg: AsyncEngine,
    snapshot,
):
    group = await groups_data.create("Test")

    document = await mongo.groups.find_one()
    row = await get_row_by_id(pg, SQLGroup, 1)

    assert document["name"] == row.name == "Test" == group.name

    group = await groups_data.update(group.id, UpdateGroupRequest(name="Renamed"))

    document = await mongo.groups.find_one()
    row = await get_row_by_id(pg, SQLGroup, 1)

    assert document["name"] == row.name == "Renamed" == group.name


async def test_update_permissions(
    authorization_client: AuthorizationClient,
    groups_data: GroupsData,
    mongo: Mongo,
    pg: AsyncEngine,
    snapshot,
):
    group = await groups_data.create("Test")

    group = await groups_data.update(
        group.id,
        UpdateGroupRequest(
            **{"permissions": {"create_sample": True, "modify_subtraction": True}}
        ),
    )

    doc = await mongo.groups.find_one()
    row = await get_row_by_id(pg, SQLGroup, 1)

    assert (
        group.permissions
        == row.permissions
        == doc["permissions"]
        == snapshot(name="mongo_added")
    )

    group = await groups_data.update(
        group.id, UpdateGroupRequest(**{"permissions": {"create_sample": False}})
    )

    doc = await mongo.groups.find_one()
    row = await get_row_by_id(pg, SQLGroup, 1)

    assert (
        group.permissions
        == row.permissions
        == doc["permissions"]
        == snapshot(name="mongo_removed")
    )


async def test_delete(authorization_client, groups_data, mongo, pg, snapshot):
    group = await groups_data.create("Test")

    await groups_data.delete(group.id)

    with pytest.raises(ResourceNotFoundError):
        await groups_data.get(group.id)

    assert await mongo.groups.count_documents({}) == 0
    assert await get_row_by_id(pg, SQLGroup, 1) is None


async def test_delete_dne(groups_data: GroupsData, snapshot):
    with pytest.raises(ResourceNotFoundError):
        await groups_data.delete("foobar")
