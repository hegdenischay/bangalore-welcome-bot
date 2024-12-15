from nio import AsyncClient, MatrixRoom, RoomMessageText

from bangalore_bot.chat_functions import react_to_event, send_text_to_room, find_admins_and_reply, make_pill
from bangalore_bot.config import Config
from bangalore_bot.storage import Storage
from datetime import datetime
import random
import aiohttp
import base64
from urllib.parse import urlencode


class Command:
    def __init__(
        self,
        client: AsyncClient,
        store: Storage,
        config: Config,
        command: str,
        room: MatrixRoom,
        event: RoomMessageText,
    ):
        """A command made by a user.

        Args:
            client: The client to communicate to matrix with.

            store: Bot storage.

            config: Bot configuration parameters.

            command: The command and arguments.

            room: The room the command was sent in.

            event: The event describing the command.
        """
        self.client = client
        self.store = store
        self.config = config
        self.command = command
        self.room = room
        self.event = event
        self.args = self.command.split()[1:]
        self.day = ""
        self.month = ""
        self.year = ""

    async def process(self):
        """Process the command"""
        if self.command.startswith("help"):
            await self._show_help()
        elif self.command.startswith("birthday"):
            await self._birthday_func()
        elif self.command.startswith("rules"):
            await self._rules_func()
        elif self.command.startswith("admin"):
            await self._tag_admins() 
        elif self.command.startswith("8ball"):
            await self._8ball()
        elif self.command.startswith("spotify"):
            await self._search_spotify()
        else:
            await self._unknown_command()
    
    async def _get_access_token(self, session):
        """Get an access token for Spotify API authentication."""
        auth_str = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
        b64_auth_str = base64.b64encode(auth_str.encode()).decode()
        
        headers = {
            'Authorization': f'Basic {b64_auth_str}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        data = {'grant_type': 'client_credentials'}

        async with session.post("https://accounts.spotify.com/api/token", headers=headers, data=data) as response:
            response_data = await response.json()
            return response_data.get("access_token")

    async def _search_spotify(self, type='track'):
        """Search Spotify for a given query and return Spotify URLs."""
        query = " ".join(self.args)
        async with aiohttp.ClientSession() as session:
            access_token = await self._get_access_token(session)
            
            headers = {
                'Authorization': f'Bearer {access_token}'
            }
            
            search_params = {
                'q': query,
                'type': type,
                'limit': 1  # Adjust this to get more results
            }
            
            search_url = f"https://api.spotify.com/v1/search?{urlencode(search_params)}"
            
            async with session.get(search_url, headers=headers) as response:
                search_results = await response.json()
                try:
                    uri = search_results['tracks']['items'][0]['uri']
                    spotify_id = uri.split(":")[2]
                    response = f"https://open.spotify.com/track/{spotify_id}"
                except:
                    response = "No song found for this search 🥹"
                await send_text_to_room(self.client, self.room.room_id, response, reply_to_event_id=self.event.event_id)
            


    async def _tag_admins(self) -> None:
        """Send a message responding to this one, tagging admins"""
        text = "Tagging all admins! "
        all_users = self.room.power_levels.users
        admins = [user for user, level in all_users.items() if level >= 50 and 'whatsappbot' not in user]
        text += ", ".join([make_pill(admin) for admin in admins])
        await find_admins_and_reply(self.client, self.room.room_id, self.event.event_id, text, admins)

    async def _8ball(self):
        responses = [
          "It is certain.",
          "It is decidedly so.",
          "Without a doubt.",
          "Yes - definitely.",
          "You may rely on it.",
          "As I see it, yes.",
          "Most likely.",
          "Outlook good.",
          "Yes.",
          "Signs point to yes.",
          "Reply hazy, try again.",
          "Ask again later.",
          "Better not tell you now.",
          "Cannot predict now.",
          "Concentrate and ask again.",
          "Don't count on it.",
          "My reply is no.",
          "My sources say no.",
          "Outlook not so good.",
          "Very doubtful."
          ]
        response = random.choice(responses) 
        await send_text_to_room(self.client, self.room.room_id, response, reply_to_event_id=self.event.event_id)

    async def _echo(self):
        """Echo back the command's arguments"""
        response = " ".join(self.args)
        await send_text_to_room(self.client, self.room.room_id, response, reply_to_event_id=self.event.event_id)

    async def _birthday_func(self):
        """Birthday provider aggregator"""
        args = " ".join(self.args)
        print("Sender:", self.event.sender)
        sender_name = ""
        print("Args:", self.args)
        response = "WIP function"
        #await send_text_to_room(self.client, self.room.room_id, response, reply_to_event_id=self.event.event_id)
        #return
        valid_date = await self.is_valid_date_any_format(args)

        if self.args == []:
            response = "Please use !birthday list <month> to list birthdays"
            await send_text_to_room(self.client, self.room.room_id, response, reply_to_event_id=self.event.event_id)

        if self.args[0] == "list":
            if len(self.args) != 1:
                self.store._execute(f"select sender, birth_day from birthdays where birth_month={self.args[1]} order by birth_day asc")
                res = self.store.cursor.fetchall()
                await self._display_names(res, self.args[1])
            else:
                response = "Please use a month to specify which month you want results for"
                await send_text_to_room(self.client, self.room.room_id, response, reply_to_event_id=self.event.event_id)
        
        if valid_date:
            res = self.store._execute("INSERT INTO birthdays (sender, sender_name, birth_month, birth_day, birth_year) VALUES (?, ?, ?, ?, ?)", (self.event.sender, sender_name, self.month, self.day, self.year))
            response = f"Stored the birthday!"
            await send_text_to_room(self.client, self.room.room_id, response, reply_to_event_id=self.event.event_id)

    def _ordinal(self, n):
        return str(n)+("th" if 4<=n%100<=20 else {1:"st",2:"nd",3:"rd"}.get(n%10, "th"))

    async def _display_names(self, birthdays, birth_month):
        counter = 1
        formatted_message = f"Birthdays for the month of {birth_month}"
        if len(birthdays) == 0:
            formatted_message = "I don't know anyone's birthday for this month 😢"
        else:
            for row in birthdays:
                formatted_message += f"<p>{make_pill(row[0])}'s birthday is on the {self._ordinal(row[1])}!</p>"
        await send_text_to_room(self.client, self.room.room_id, formatted_message, reply_to_event_id=self.event.event_id) 

    async def is_valid_date_any_format(self, date_string):
        date_formats = [
            "%Y-%m-%d",   # 2023-10-15
            "%m/%d/%Y",   # 10/15/2023
            "%d-%m-%Y",   # 15-10-2023
            "%d/%m/%Y",   # 15/10/2023
            "%Y/%m/%d",   # 2023/10/15
            "%b %d, %Y",  # Oct 15, 2023
            "%B %d, %Y",  # October 15, 2023
            "%d %b %Y",   # 15 Oct 2023
            "%d %B %Y",   # 15 October 2023
        ]
        
        for date_format in date_formats:
            try:
                # Try to parse the date string with the current format
                date_obj = datetime.strptime(date_string, date_format)
                today = datetime.now()
                eighteen = today.replace(year=today.year-18)
                ninety = today.replace(year=today.year-90)
                if date_obj > eighteen and date_obj < today:
                    response = "Underage b&. Mooooods!!!"
                    await send_text_to_room(self.client, self.room.room_id, response, reply_to_event_id=self.event.event_id)
                    return False
                if date_obj < ninety:
                    response = "Wow, how are you even alive? Need help using this app?"
                    await send_text_to_room(self.client, self.room.room_id, response, reply_to_event_id=self.event.event_id)
                    return False
                if date_obj > today:
                    response = "Hey, Time traveller! Mind telling us some juicy facts about the future?"
                    await send_text_to_room(self.client, self.room.room_id, response, reply_to_event_id=self.event.event_id)
                    return False

                self.day = date_obj.day
                self.month = date_obj.month
                self.year = date_obj.year
                return True
            except ValueError:
                # If the format doesn't match, continue trying with the next format
                continue
        return False
    
    async def _rules_func(self):
        response = (f"The rules of this chat:\n\n"
                f"- This group is a *safe space*. Add and invite people. Please don’t let the GC die.\n\n"
f"- We’ll plan hangouta every weekend or do something fun. Let’s kill loneliness away.\n\n"
f"- Pls post an intro once you’re in :)\n\n"
f"- Please keep conversations in English or provide translations for other languages in view of the larger group."
                )
        await send_text_to_room(self.client, self.room.room_id, response, reply_to_event_id=self.event.event_id)

    async def _react(self):
        """Make the bot react to the command message"""
        # React with a start emoji
        reaction = "⭐"
        await react_to_event(
            self.client, self.room.room_id, self.event.event_id, reaction
        )

        # React with some generic text
        reaction = "Some text"
        await react_to_event(
            self.client, self.room.room_id, self.event.event_id, reaction
        )

    async def _show_help(self):
        """Show the help text"""
        if not self.args:
            text = (
                    f"Hello, I am a bot made by {make_pill('@tlh:intothematrix.in')}, using `matrix-nio`!\n\n" 
                    f"I run on the messaging protocol matrix, so expect problems if my maker didn't maintain me properly.\n\n"
                    f"Use `!help commands` to view available commands."
            )
            await send_text_to_room(self.client, self.room.room_id, text, reply_to_event_id=self.event.event_id)
            return

        topic = self.args[0]
        if topic == "rules":
            text = "These are the rules: Don't ask me for commands!"
        elif topic == "commands":
            text = "Available commands: admins, birthday, rules, 8ball, spotify"
        elif topic == "admins":
            text = "Using !admin or !admins while writing to a message will notify the admins"
        elif topic == "birthday":
            text = """!birthday DD-MM-YYYY - Add or update your birthday\n
!birthday list (1-12) - List of upcoming birthdays in this month"""
        elif topic == "birthdays":
            text = """!birthday DD-MM-YYY - Add or update your birthday\n
            !birthday list (1-12) - List of upcoming birthdays in this month"""
        elif topic == "spotify":
            text = "!spotify - Get Spotify song links in the chat"
        elif topic == "8ball":
            text = "!8ball - Ask the magic 8 ball!"
        else:
            text = "Unknown help topic!"
        await send_text_to_room(self.client, self.room.room_id, text, reply_to_event_id=self.event.event_id)

    async def _unknown_command(self):
        await send_text_to_room(
            self.client,
            self.room.room_id,
            f"Unknown command '{self.command}'. Try the 'help' command for more information.",
        )
