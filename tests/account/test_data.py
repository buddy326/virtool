import pytest
from aiohttp.test_utils import make_mocked_coro
from virtool_core.models.enums import Permission

from virtool.account.data import AccountData
from virtool.account.oas import CreateKeysSchema
from virtool.groups.oas import EditPermissionsSchema


@pytest.mark.parametrize(
    "administrator", [True, False], ids=["administrator", "limited"]
)
@pytest.mark.parametrize(
    "has_permission", [True, False], ids=["has permission", "missing permission"]
)
async def test_create_api_key(administrator, has_permission, mocker, dbi, static_time):
    """
    Test that an API key is created correctly with varying key owner administrator status and
    permissions.

    """
    m_get_alternate_id = mocker.patch(
        "virtool.account.db.get_alternate_id", make_mocked_coro("foo_0")
    )

    m_generate_key = mocker.patch(
        "virtool.utils.generate_key", return_value=("bar", "baz")
    )

    groups = [{"id": "technicians"}, {"id": "managers"}]

    # Vary the key owner's administrator status and permissions.
    await dbi.users.insert_one(
        {
            "_id": "bob",
            "administrator": administrator,
            "groups": groups,
            "permissions": {
                Permission.create_sample.value: True,
                "modify_subtraction": has_permission,
            },
        }
    )

    account_data = AccountData(dbi)
    data = CreateKeysSchema(
        name="Foo",
        permissions=EditPermissionsSchema(create_sample=True, modify_subtraction=True),
    )

    _, document = await account_data.create_key(data, "bob")
    document = document.dict()

    permissions = {p.value: False for p in Permission}
    permissions[Permission.create_sample.value] = True
    permissions["modify_subtraction"] = False

    expected = {
        "administrator": administrator,
        "id": "foo_0",
        "name": "Foo",
        "created_at": static_time.datetime,
        "groups": groups,
        "permissions": permissions,
    }

    # The key should not have the `create_subtraction` permission set unless the key
    # owner is and administrator or has the `create_subtraction` permission themselves.
    if administrator or has_permission:
        expected["permissions"]["modify_subtraction"] = True

    # Check that expected functions were called.
    m_get_alternate_id.assert_called_with(dbi, "Foo")
    m_generate_key.assert_called()

    # Check returned document matches expected.
    for group in expected["groups"]:
        group.update({"name": group["id"]})

    assert document == expected

    # Modify expected document to check what we expect to have been inserted in the database.
    del expected["groups"][0]["name"]
    del expected["groups"][1]["name"]

    expected.update({"_id": "baz", "user": {"id": "bob"}})

    assert await dbi.keys.find_one() == expected
