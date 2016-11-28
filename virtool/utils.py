import os
import shutil
import binascii
import datetime
import pymongo
import motor

import virtool.gen


@virtool.gen.synchronous
def rm(path, recursive=False):
    """
    A function that removes files or directories in a separate thread. Wraps :func:`os.remove` and func:`shutil.rmtree`.

    :param path: the path to remove.
    :type path: str

    :param recursive: the operation should recursively descend into dirs.
    :type recursive: bool

    :return: a Tornado future.
    :rtype: :class:`tornado.concurrent.Future`

    """
    try:
        os.remove(path)
        return True
    except IsADirectoryError:
        if recursive:
            shutil.rmtree(path)
            return True

        raise


@virtool.gen.synchronous
def list_files(directory, excluded=None):
    """
    Get a list of dicts describing the files in the passed directory. Each dict contains the information:

    * _id: the file name
    * size: the size in bytes of the file
    * access: the timestamp for when the file was last accessed
    * modify:  the timestamp for when the file was last modified

    :param directory: the directory to look in.
    :type directory: str

    :param excluded: names of files to exclude from the list.
    :type excluded: list

    :returns: a list of dicts describing the files in the directory.
    :rtype: list

    """
    file_list = os.listdir(directory)

    # This list will contain a dictionary of the detail for each file that was not excluded
    available = dict()

    for name in file_list:
        if excluded is None or name not in excluded:
            # Get detailed information for file by name
            file_stats = os.stat(directory + "/" + name)

            # Append file entry to reply list
            available[name] = {
                "_id": name,
                "size": file_stats.st_size,
                "access": timestamp(file_stats.st_atime),
                "modify": timestamp(file_stats.st_mtime)
            }

    return available


def timestamp(time=None):
    """
    Returns and ISO format timestamp. Generates one for the current time if no ``time`` argument is passed.

    :param time: the date/time to generate a timestamp for.
    :type time: datetime.datetime or str or int

    :return: a timestamp
    :rtype: str

    """
    if time is None:
        return datetime.datetime.now().isoformat()

    return datetime.datetime.fromtimestamp(time).isoformat()


def random_alphanumeric(length=6, exclude_list=None):
    """
    Generates a random string composed of letters and numbers.

    :param length: the length of the string.
    :type length: int

    :param exclude_list: strings that may not be returned.
    :type exclude_list: list

    :return: a random alphanumeric string.
    :rtype: string

    """
    candidate = binascii.hexlify(os.urandom(length * 3)).decode()[0:length]

    if not exclude_list or candidate not in exclude_list:
        return candidate

    return random_alphanumeric(length, exclude_list)


@virtool.gen.coroutine
def get_new_document_id(motor_collection, excluded=None):
    """
    Get a unique 8-character alphanumeric id for the given Motor collection.

    :param motor_collection: the collection to generate a new unique id for.
    :type motor_collection: :class:`motor.motor_tornado.MotorCollection`

    :param excluded: a list of ids to exclude in addition to the extant ids in the collection
    :type excluded: list

    :return: a random 8-character alphanumeric document id.
    :rtype: str

    """
    existing_ids = yield motor_collection.find({}, {"_id": True}).distinct("_id")

    exclude = (excluded or list()) + existing_ids

    return random_alphanumeric(length=8, exclude_list=exclude)


def where(subject, predicate):
    """
    Returns the first object in ``subject`` that return True for the given ``predicate``.

    :param subject: a list of objects.
    :type subject: list

    :param predicate: a function to test object in the ``subject`` list.
    :type predicate: callable

    :return: the matched object or None.
    :rtype: any

    """
    assert callable(predicate)
    return list(filter(predicate, subject))[0]


def average_list(list1, list2):
    try:
        assert len(list1) == len(list2)
    except AssertionError:
        raise

    return [(value + list2[i]) / 2 for i, value in enumerate(list1)]
