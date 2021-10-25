import pytest

from virtool.tasks.models import Task
from virtool.users.tasks import UpdateUserDocumentsTask


@pytest.mark.parametrize("user", ["ad_user", "existing_user", "user_with_handle"])
async def test_update_user_document_task(spawn_client, pg_session, static_time, mocker, user):
    client = await spawn_client()

    if user == "ad_user":
        document = {
            "_id": "abc123",
            "ad_given_name": "foo",
            "ad_family_name": "bar"
        }
        expected = "foo"

    elif user == "existing_user":
        document = {
            "_id": "abc123"
        }
        expected = "abc123"

    else:
        document = {
            "_id": "abc123",
            "handle": "bar"
        }

    await client.db.users.insert_one(document)
    mocker.patch("virtool.users.db.generate_handle", return_value="foo")

    if user != "user_with_handle":
        document["handle"] = expected

    task = Task(
        id=1,
        complete=False,
        context={},
        count=0,
        progress=0,
        step="rename_index_files",
        type="add_subtraction_files",
        created_at=static_time.datetime
    )

    async with pg_session as session:
        session.add(task)
        await session.commit()

    add_index_files_task = UpdateUserDocumentsTask(client.app, 1)
    await add_index_files_task.run()
    assert await client.db.users.find_one({"_id": "abc123"}) == document
