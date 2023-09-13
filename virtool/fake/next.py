"""
Easily create fake data.

"""
from typing import Dict, List, Optional, Type
import pathlib
from typing import List, Optional

import aiofiles
from faker import Faker
from faker.providers import BaseProvider, color, lorem, python
from faker.providers import BaseProvider, python, color, lorem, file
from virtool_core.models.group import Group
from virtool_core.models.hmm import HMM
from virtool_core.models.job import Job
from virtool_core.models.label import Label
from virtool_core.models.roles import AdministratorRole
from virtool_core.models.task import Task
from virtool_core.models.upload import Upload
from virtool_core.models.user import User

from virtool.administrators.oas import UpdateUserRequest
from virtool.data.layer import DataLayer
from virtool.groups.oas import UpdateGroupRequest, UpdatePermissionsRequest
from virtool.indexes.tasks import EnsureIndexFilesTask
from virtool.jobs.utils import WORKFLOW_NAMES
from virtool.ml.models import MLModel
from virtool.references.tasks import CleanReferencesTask, CloneReferenceTask
from virtool.releases import ReleaseManifestItem
from virtool.subtractions.tasks import AddSubtractionFilesTask
from virtool.tasks.task import BaseTask
from virtool.uploads.models import UploadType
from virtool.uploads.utils import CHUNK_SIZE, naive_writer
from virtool.users.oas import UpdateUserRequest


async def fake_file_chunks(path: pathlib.Path) -> bytearray:
    """
    Read a chunk of size `CHUNK_SIZE` from a file.
    """
    async with aiofiles.open(path, "r") as f:

        yield await f.read(CHUNK_SIZE)


class VirtoolProvider(BaseProvider):
    def mongo_id(self):
        return self.random_letters(8)

    def pg_id(self) -> int:
        return self.random_int()

    def workflow(self) -> str:
        return self.random_choices(
            [name.replace("job_", "") for name in WORKFLOW_NAMES], 1
        )[0]


class DataFaker:
    def __init__(self, layer: DataLayer, mongo):
        self.layer = layer

        self.faker = Faker()
        self.faker.seed_instance(0)
        self.faker.add_provider(VirtoolProvider)
        self.faker.add_provider(color)
        self.faker.add_provider(lorem)
        self.faker.add_provider(python)
        self.faker.add_provider(file)

        self.groups = GroupsFakerPiece(self)
        self.hmm = HMMFakerPiece(self)
        self.jobs = JobsFakerPiece(self)
        self.labels = LabelsFakerPiece(self)
        self.ml = MLFakerPiece(self)
        self.tasks = TasksFakerPiece(self)
        self.users = UsersFakerPiece(self)
        self.uploads = UploadsFakerPiece(self)

        self.mongo = mongo


class DataFakerPiece:
    def __init__(self, data_faker: DataFaker):
        self.layer = data_faker.layer
        self.faker = data_faker.faker
        self.history = []


class JobsFakerPiece(DataFakerPiece):
    model = Job

    async def create(self, user: User, workflow: Optional[str] = None) -> Job:
        return await self.layer.jobs.create(
            workflow or self.faker.workflow(),
            self.faker.pydict(nb_elements=6, value_types=[str, int, float]),
            user.id,
            0,
        )


class GroupsFakerPiece(DataFakerPiece):
    model = Group

    async def create(self, permissions: Optional[UpdatePermissionsRequest] = None):
        name = "contains spaces"

        while " " in name:
            name = self.faker.profile()["job"].lower() + "s"

        group = await self.layer.groups.create(name)

        if permissions:
            group = await self.layer.groups.update(
                group.id, UpdateGroupRequest(permissions=permissions)
            )

        return group


class LabelsFakerPiece(DataFakerPiece):
    model = Label

    async def create(self):
        return await self.layer.labels.create(
            self.faker.word().capitalize(),
            self.faker.hex_color(),
            self.faker.sentence(),
        )


class MLFakerPiece(DataFakerPiece):
    model = MLModel

    async def populate(self):
        """Populate the ML model collection with fake data."""
        return await self.layer.ml.load(
            {
                "ml-plant-viruses": [
                    self.create_release_manifest_item() for _ in range(3)
                ],
                "ml-insect-viruses": [
                    self.create_release_manifest_item() for _ in range(3)
                ],
            },
        )

    def create_release_manifest_item(self) -> ReleaseManifestItem:
        """
        Create a fake release manifest item like you would receive from the
        www.virtool.ca releases endpoints

        """
        return ReleaseManifestItem(
            id=self.faker.pyint(),
            body=self.faker.paragraph(),
            content_type=self.faker.pystr(),
            download_url=self.faker.url(),
            filename=self.faker.pystr(),
            html_url=self.faker.url(),
            name=self.faker.pystr(),
            prerelease=self.faker.pybool(),
            published_at=self.faker.date_time(),
            size=self.faker.pyint(),
        )


class TasksFakerPiece(DataFakerPiece):
    model = Task

    async def create(self):
        return await self.layer.tasks.create(
            self.faker.random_element(
                [
                    EnsureIndexFilesTask,
                    AddSubtractionFilesTask,
                    CloneReferenceTask,
                    CleanReferencesTask,
                ]
            ),
            {},
        )

    async def create_with_class(self, cls: Type[BaseTask], context: Dict):
        return await self.layer.tasks.create(cls, context)


class UsersFakerPiece(DataFakerPiece):
    model = User

    async def create(
        self,
        handle: Optional[str] = None,
        groups: Optional[List[Group]] = None,
        primary_group: Optional[Group] = None,
        administrator_role: Optional[AdministratorRole] = None,
    ):
        handle = handle or self.faker.profile()["username"]
        user = await self.layer.users.create(handle, self.faker.password())

        if groups or primary_group:
            if groups:
                await self.layer.administrators.update(
                    user.id, UpdateUserRequest(groups=[group.id for group in groups])
                )

            if primary_group:
                await self.layer.administrators.update(
                    user.id, UpdateUserRequest(primary_group=primary_group.id)
                )

            if administrator_role:
                await self.layer.administrators.set_administrator_role(
                    user.id, administrator_role
                )

            return await self.layer.users.get(user.id)

        return user


class HMMFakerPiece(DataFakerPiece):
    model = HMM

    async def create(self, mongo):
        hmm_id = "".join(self.faker.mongo_id())
        faker = self.faker

        document = await mongo.hmm.insert_one(
            {
                "entries": [
                    {
                        "accession": faker.pystr(),
                        "gi": faker.pystr(),
                        "name": faker.pystr(),
                        "organism": faker.pystr(),
                    }
                ],
                "genera": {faker.pystr(): faker.pyint()},
                "length": faker.pyint(),
                "mean_entropy": faker.pyfloat(),
                "total_entropy": faker.pyfloat(),
                "_id": hmm_id,
                "cluster": faker.pyint(),
                "count": faker.pyint(),
                "families": {faker.pystr(): faker.pyint()},
                "names": [faker.pystr()],
            }
        )

        return HMM(**document)


class UploadsFakerPiece(DataFakerPiece):
    model = Upload

    async def create(
        self,
        user: User,
        with_file: bool = False,
        upload_type: str = "reads",
        name: str = "test.fq.gz",
        reserved: bool = False,
    ) -> Upload:

        if upload_type not in UploadType.to_list():
            upload_type = "reads"

        upload = await self.layer.uploads.create(name, upload_type, reserved, user.id)

        size = self.faker.pyint(min_value=100)

        if with_file:
            config = getattr(self.layer.uploads, "_config")
            file_path = config.data_path / "files" / upload.name_on_disk
            size = await naive_writer(fake_file_chunks(file_path), file_path)

        upload = await self.layer.uploads.finalize(size, upload.id)

        return upload
