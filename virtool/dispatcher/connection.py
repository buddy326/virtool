from typing import Union

from aiohttp.web_ws import WebSocketResponse

from virtool.api.custom_json import dumps


class Connection:
    """
    Wraps a :class:``WebSocketResponse``.
    """

    def __init__(self, ws: WebSocketResponse, session):
        self._ws = ws
        self.ping = self._ws.ping
        self.user_id = session.user_id
        self.groups = session.groups
        self.permissions = session.permissions

    async def send(self, message: Union[dict, list]):
        """
        Sends the passed JSON-encodable message to the connected client.
        :param message: the message to send
        """
        try:
            await self._ws.send_json(message, dumps=dumps)
        except ConnectionResetError as err:
            if "Cannot write to closing transport" not in str(err):
                raise

            await self.close(1002)

    async def close(self, code: int):
        """
        Closes the underlying websocket connection.
        :param code: closure code to send to the client
        """
        await self._ws.close(code=code)
