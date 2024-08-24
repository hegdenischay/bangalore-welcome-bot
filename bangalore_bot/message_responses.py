import logging

from nio import AsyncClient, MatrixRoom, RoomMessageText

from bangalore_bot.chat_functions import send_text_to_room, find_admins_and_reply
from bangalore_bot.config import Config
from bangalore_bot.storage import Storage

logger = logging.getLogger(__name__)


class Message:
    def __init__(
        self,
        client: AsyncClient,
        store: Storage,
        config: Config,
        message_content: str,
        room: MatrixRoom,
        event: RoomMessageText,
    ):
        """Initialize a new Message

        Args:
            client: nio client used to interact with matrix.

            store: Bot storage.

            config: Bot configuration parameters.

            message_content: The body of the message.

            room: The room the event came from.

            event: The event defining the message.
        """
        self.client = client
        self.store = store
        self.config = config
        self.message_content = message_content
        self.room = room
        self.event = event

    async def process(self) -> None:
        """Process and possibly respond to the message"""
        if self.message_content.lower() == "hello world":
            await self._hello_world()
        if self.message_content.lower() == "@admin":
            await self._tag_admins()
        if self.message_content.lower() == "@admins":
            await self._tag_admins()

    async def _hello_world(self) -> None:
        """Say hello"""
        text = "Hello, world!"
        await send_text_to_room(self.client, self.room.room_id, text)

    async def _tag_admins(self) -> None:
        """Send a message responding to this one, tagging admins"""
        text = "Tagging all admins"
        all_users = self.room.power_levels.users
        admins = [user for user, level in all_users.items() if level >= 50 and 'whatsappbot' not in user]
        await find_admins_and_reply(self.client, self.room.room_id, self.event.event_id, text, admins)
