import os

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

import virtool.utils
from virtool.uploads.models import Upload, UploadType
from virtool_core.models.enums import Permission


@pytest.fixture
def files(test_files_path):
    return {"file": open(test_files_path / "test.fq.gz", "rb")}


class TestUpload:
    @pytest.mark.parametrize("upload_type", UploadType.to_list())
    async def test(
        self,
        files,
        upload_type,
        tmp_path,
        snapshot,
        spawn_client,
        static_time,
        pg: AsyncEngine,
    ):
        """
        Test `POST /uploads` to assure a file can be uploaded and that it properly updates the db.

        """
        client = await spawn_client(
            authorize=True, permissions=[Permission.upload_file]
        )

        client.app["config"].data_path = tmp_path

        if upload_type:
            resp = await client.post_form(
                f"/uploads?name=Test.fq.gz&type={upload_type}", data=files
            )
        else:
            resp = await client.post_form("/uploads?name=Test.fq.gz", data=files)

        assert resp.status == 201
        assert await resp.json() == snapshot

        assert os.listdir(tmp_path / "files") == ["1-Test.fq.gz"]

    async def test_invalid_request(self, files, spawn_client, resp_is):
        """
        Test `POST /uploads` to assure it properly rejects an invalid request.

        """
        client = await spawn_client(
            authorize=True, permissions=[Permission.upload_file]
        )

        resp = await client.post_form("/uploads", data=files)

        assert resp.status == 400

    async def test_bad_type(self, files, spawn_client, resp_is):
        """
        Test `POST /uploads` to assure it properly rejects an invalid upload type.

        """
        client = await spawn_client(
            authorize=True, permissions=[Permission.upload_file]
        )

        resp = await client.post_form(
            "/uploads?name=Test.fq.gz&type=foobar", data=files
        )

        await resp_is.bad_request(resp, "Unsupported upload type")


class TestFind:
    @pytest.mark.parametrize("upload_type", ["reads", "reference", None])
    async def test(self, upload_type, spawn_client, snapshot, test_uploads):
        """
        Test `GET /uploads` to assure that it returns the correct `upload` documents.

        """
        client = await spawn_client(authorize=True, administrator=True)

        url = "/uploads"

        if upload_type:
            url += f"?upload_type={upload_type}"

        resp = await client.get(url)

        assert resp.status == 200
        assert await resp.json() == snapshot

    @pytest.mark.parametrize("ready", [True, False, None])
    async def test_ready(self, ready, spawn_client, snapshot, test_uploads):
        """
        Test `GET /uploads?ready` to assure that it returns the correct `upload` documents
        with correct 'ready' status.

        """
        client = await spawn_client(authorize=True, administrator=True)

        url = "/uploads"

        if ready is not None:
            url += f"?ready={ready}"

        resp = await client.get(url)

        assert resp.status == 200
        assert await resp.json() == snapshot


class TestGet:
    @pytest.mark.parametrize("exists", [True, False])
    async def test(self, exists, files, resp_is, spawn_client, tmp_path):
        """
        Test `GET /uploads/:id` to assure that it lets you download a file.

        """
        client = await spawn_client(authorize=True, administrator=True)

        client.app["config"].data_path = tmp_path

        if exists:
            await client.post_form("/uploads?name=test.fq.gz&type=hmm", data=files)

        resp = await client.get("/uploads/1")

        assert resp.status == 200 if exists else 404

    @pytest.mark.parametrize("exists", [True, False])
    async def test_upload_removed(
        self, exists, resp_is, spawn_client, pg: AsyncEngine, tmp_path
    ):
        """
        Test `GET /uploads/:id` to assure that it doesn't let you download a file that has been removed.

        """
        client = await spawn_client(authorize=True, administrator=True)

        client.app["config"].data_path = tmp_path

        async with AsyncSession(pg) as session:
            session.add(
                Upload(
                    id=1,
                    created_at=virtool.utils.timestamp(),
                    name="test.fq.gz",
                    name_on_disk="1-test.fq.gz",
                    ready=True,
                    removed=exists,
                    removed_at=None,
                    reserved=False,
                    size=9081,
                    type="hmm",
                    uploaded_at=virtool.utils.timestamp(),
                    user="test",
                )
            )
            await session.commit()

        resp = await client.get("/uploads/1")

        assert resp.status == 404


class TestDelete:
    async def test(self, files, spawn_client, tmp_path, resp_is):
        """
        Test `DELETE /uploads/:id to assure that it properly deletes an existing `uploads` row and file.

        """
        client = await spawn_client(authorize=True, administrator=True)

        client.app["config"].data_path = tmp_path
        await client.post_form("/uploads?name=test.fq.gz&type=hmm", data=files)

        resp = await client.delete("/uploads/1")
        await resp_is.no_content(resp)

        resp = await client.get("api/uploads/1")
        assert resp.status == 404

    @pytest.mark.parametrize("exists", [True, False])
    async def test_already_removed(
        self, exists, spawn_client, tmp_path, pg: AsyncEngine, resp_is
    ):
        """
        Test `DELETE /uploads/:id to assure that it doesn't try to delete a file that has already been removed.

        """
        client = await spawn_client(authorize=True, administrator=True)

        client.app["config"].data_path = tmp_path

        async with AsyncSession(pg) as session:
            session.add(
                Upload(
                    id=1,
                    created_at=virtool.utils.timestamp(),
                    name="test.fq.gz",
                    name_on_disk="1-test.fq.gz",
                    ready=True,
                    removed=exists,
                    removed_at=None,
                    reserved=False,
                    size=9081,
                    type="hmm",
                    uploaded_at=virtool.utils.timestamp(),
                    user="test",
                )
            )

            await session.commit()

        resp = await client.delete("/uploads/1")

        if exists:
            assert resp.status == 404
        else:
            await resp_is.no_content(resp)

    @pytest.mark.parametrize("exists", [True, False])
    async def test_record_dne(
        self, exists, spawn_client, pg: AsyncEngine, tmp_path, resp_is
    ):
        """
        Test `DELETE /uploads/:id to assure that it doesn't try to delete a file that corresponds to a `upload`
        record that does not exist.

        """
        client = await spawn_client(authorize=True, administrator=True)

        client.app["config"].data_path = tmp_path

        if exists:
            async with AsyncSession(pg) as session:
                session.add(
                    Upload(
                        id=1,
                        created_at=virtool.utils.timestamp(),
                        name="test.fq.gz",
                        name_on_disk="1-test.fq.gz",
                        ready=True,
                        removed_at=None,
                        reserved=False,
                        size=9081,
                        type="hmm",
                        uploaded_at=virtool.utils.timestamp(),
                        user="test",
                    )
                )
                await session.commit()

        resp = await client.delete("/uploads/1")

        if exists:
            await resp_is.no_content(resp)
        else:
            assert resp.status == 404
