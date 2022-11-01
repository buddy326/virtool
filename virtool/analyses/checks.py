from datetime import datetime
from typing import Optional

from virtool.analyses.utils import find_nuvs_sequence_by_index
from virtool.data.errors import (
    ResourceConflictError,
    ResourceNotModifiedError,
    ResourceNotFoundError,
)


async def check_if_analysis_modified(
    if_modified_since: Optional[datetime], document: dict
):
    if if_modified_since is not None:
        try:
            updated_at = document["updated_at"]
        except KeyError:
            updated_at = document["created_at"]

        if if_modified_since == updated_at:
            raise ResourceNotModifiedError()


async def check_if_analysis_ready(jobs_api_flag: bool, ready: bool):
    if jobs_api_flag and ready:
        raise ResourceConflictError()
    else:
        if not ready:
            raise ResourceConflictError()


async def check_analysis_workflow(workflow: str):
    if workflow != "nuvs":
        raise ResourceConflictError("Not a NuVs analysis")


async def check_if_analysis_running(ready: bool):
    if not ready:
        raise ResourceConflictError("Analysis is still running")


async def check_analysis_nuvs_sequence(document, sequence_index):
    sequence = find_nuvs_sequence_by_index(document, sequence_index)

    if sequence is None:
        raise ResourceNotFoundError()
