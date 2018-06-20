import asyncio
import json
import os

import aiohttp
import semver

import virtool.db
import virtool.db.processes
import virtool.db.utils
import virtool.http.proxy
import virtool.http.utils
import virtool.processes
import virtool.software
import virtool.utils

VIRTOOL_RELEASES_URL = "https://www.virtool.ca/releases"


async def fetch_and_update_software_releases(app):
    """
    Get a list of releases, from the Virtool website, published since the current server version.

    :param app: the application object

    :return: a list of releases
    :rtype: Coroutine[list]

    """
    db = app["db"]
    version = app["version"]
    session = app["client"]
    settings = app["settings"]

    if app is None:
        return list()

    try:
        async with virtool.http.proxy.ProxyRequest(settings, session.get, VIRTOOL_RELEASES_URL) as resp:
            data = await resp.text()
            data = json.loads(data)
    except aiohttp.ClientConnectionError:
        # Return any existing release list or `None`.
        return await virtool.db.utils.get_one_field(db.status, "releases", "software")

    data = data["software"]

    channel = settings["software_channel"]

    # Reformat the release dicts to make them more palatable. If the response code was not 200, the releases list
    # will be empty. This is interpreted by the web client as an error.
    if channel == "stable":
        data = [r for r in data if "alpha" not in r["name"] and "beta" not in r["name"]]

    elif channel == "beta":
        data = [r for r in data if "alpha" not in r["name"]]

    releases = list()

    for release in data:
        if semver.compare(release["name"].replace("v", ""), version.replace("v", "")) < 1:
            break

        releases.append(release)

    await db.status.update_one({"_id": "software"}, {
        "$set": {
            "releases": releases
        }
    })

    return releases


async def install(app, release, process_id):
    """
    Installs the update described by the passed release document.

    """
    db = app["db"]

    with virtool.utils.get_temp_dir() as tempdir:
        # Download the release from GitHub and write it to a temporary directory.
        compressed_path = os.path.join(str(tempdir), "release.tar.gz")

        progress_tracker = virtool.processes.ProgressTracker(
            db,
            process_id,
            release["size"],
            factor=0.5,
            initial=0
        )

        try:
            await virtool.http.utils.download_file(
                app,
                release["download_url"],
                compressed_path,
                progress_handler=progress_tracker.add
            )
        except FileNotFoundError:
            await virtool.db.processes.update(db, process_id, errors=[
                "Could not write to release download location"
            ])

        # Start decompression step, reporting this to the DB.
        await virtool.db.processes.update(
            db,
            process_id,
            progress=0.5,
            step="unpack"
        )

        # Decompress the gzipped tarball to the root of the temporary directory.
        await app["run_in_thread"](virtool.utils.decompress_tgz, compressed_path, str(tempdir))

        # Start check tree step, reporting this to the DB.
        await virtool.db.processes.update(
            db,
            process_id,
            progress=0.7,
            step="verify"
        )

        # Check that the file structure matches our expectations.
        decompressed_path = os.path.join(str(tempdir), "virtool")

        good_tree = await app["run_in_thread"](virtool.software.check_software_files, decompressed_path)

        if not good_tree:
            await virtool.db.processes.update(db, process_id, errors=[
                "Invalid unpacked installation tree"
            ])

        # Copy the update files to the install directory.
        await virtool.db.processes.update(
            db,
            process_id,
            progress=0.9,
            step="install"
        )

        await app["run_in_thread"](
            virtool.software.copy_software_files,
            decompressed_path,
            "/home/igboyes/temp_install" # virtool.software.INSTALL_PATH
        )

        await virtool.db.processes.update(
            db,
            process_id,
            progress=1
        )

        await asyncio.sleep(1.5, loop=app.loop)

        await virtool.utils.reload(app)


async def update_software_process(db, progress, step=None):
    """
    Update the process field in the software update document. Used to keep track of the current progress of the update
    process.

    :param db: the application database client
    :type db: :class:`~motor.motor_asyncio.AsyncIOMotorClient`

    :param progress: the numeric progress number for the step
    :type progress: Union(int, float)

    :param step: the name of the step in progress
    :type step: str

    """
    return await virtool.utils.update_status_process(db, "software", progress, step)
