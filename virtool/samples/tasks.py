import logging

import virtool.samples.db
from virtool.tasks.task import Task
from virtool.data.utils import get_data_from_app

logger = logging.getLogger(__name__)


class CompressSamplesTask(Task):
    """
    Compress the legacy FASTQ files for all uncompressed samples.

    """

    task_type = "compress_samples"

    def __init__(self, app, process_id):
        super().__init__(app, process_id)
        self.steps = [self.compress_samples]

    async def compress_samples(self):
        query = {"is_legacy": True, "is_compressed": {"$exists": False}}

        count = await self.db.samples.count_documents(query)

        tracker = await self.get_tracker(count)

        while True:
            sample = await self.db.samples.find_one(query)

            if sample is None:
                break

            await virtool.samples.db.compress_sample_reads(self.app, sample)
            await tracker.add(1)

            logger.info(
                "Compressed legacy sample %s (%s%%),", sample['_id'], tracker.progress
            )

        await get_data_from_app(self.app).tasks.update(self.id, step="compress_samples")


class MoveSampleFilesTask(Task):
    """
    Move pre-SQL samples' file information to new `sample_reads` and `uploads` tables.

    """

    task_type = "move_sample_files"

    def __init__(self, app, task_id):
        super().__init__(app, task_id)

        self.steps = [self.move_sample_files]

    async def move_sample_files(self):
        query = {
            "files": {"$exists": True},
            "$or": [{"is_legacy": False}, {"is_legacy": True, "is_compressed": True}],
        }

        count = await self.db.samples.count_documents(query)

        tracker = await self.get_tracker(count)

        while True:
            sample = await self.db.samples.find_one(query)

            if sample is None:
                break

            await virtool.samples.db.move_sample_files_to_pg(self.app, sample)
            await tracker.add(1)

            logger.info(
                "Moved files in sample %s to SQL (%s%%)", sample['_id'], tracker.progress
            )

        await get_data_from_app(self.app).tasks.update(self.id, step="move_sample_files")
