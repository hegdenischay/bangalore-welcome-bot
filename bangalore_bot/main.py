#!/usr/bin/env python3
import asyncio
import logging
import sys
from time import sleep
from datetime import datetime, timedelta

from aiohttp import ClientConnectionError, ServerDisconnectedError
from nio import (
    AsyncClient,
    AsyncClientConfig,
    InviteMemberEvent,
    LocalProtocolError,
    LoginError,
    MegolmEvent,
    RoomMessageText,
    UnknownEvent,
    RoomMemberEvent,
)

from bangalore_bot.callbacks import Callbacks
from bangalore_bot.config import Config
from bangalore_bot.storage import Storage
from bangalore_bot.chat_functions import make_pill, send_text_to_room

logger = logging.getLogger(__name__)

async def daily_task(client, store):
    """The function to run at 12 a.m. each day."""
    logger.info("Running daily task at midnight")
    current_date = datetime.now()
    room_id = "<insert_room_here>"

    # Extract the day and month
    day = current_date.day
    month = current_date.month
    store._execute(f"select sender from birthdays where birth_month={month} and birth_day={day}")
    res = store.cursor.fetchall()
    if len(res) == 0:
        logger.info("Nobody to wish today")
    else:
        for row in res:
            formatted_message = f"{make_pill(row[0])}'s birthday is today🎉"
            await send_text_to_room(client, room_id, formatted_message)

async def schedule_daily_task(client, store):
    """Calculate the time until next 12 a.m. and sleep until then, repeating every day."""
    while True:
        now = datetime.now()
        # Calculate the time until the next 12 a.m.
        next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        seconds_until_midnight = (next_midnight - now).total_seconds()
        print("seconds left:", seconds_until_midnight)
        
        # Sleep until 12 a.m.
        await asyncio.sleep(seconds_until_midnight)
        
        # Run the daily task
        await daily_task(client, store)


async def main():
    """The first function that is run when starting the bot"""

    # Read user-configured options from a config file.
    # A different config file path can be specified as the first command line argument
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    else:
        config_path = "config.yaml"

    # Read the parsed config file and create a Config object
    config = Config(config_path)

    # Configure the database
    store = Storage(config.database)

    # Configuration options for the AsyncClient
    client_config = AsyncClientConfig(
        max_limit_exceeded=0,
        max_timeouts=0,
        store_sync_tokens=True,
        encryption_enabled=True,
    )

    # Initialize the matrix client
    client = AsyncClient(
        config.homeserver_url,
        config.user_id,
        device_id=config.device_id,
        store_path=config.store_path,
        config=client_config,
    )

    if config.user_token:
        client.access_token = config.user_token
        client.user_id = config.user_id

    # Set up event callbacks
    callbacks = Callbacks(client, store, config)
    client.add_event_callback(callbacks.message, (RoomMessageText,))
    # add callback on roommember
    client.add_event_callback(callbacks.user_invited, (RoomMemberEvent,))
    client.add_event_callback(
        callbacks.invite_event_filtered_callback, (InviteMemberEvent,)
    )
    client.add_event_callback(callbacks.decryption_failure, (MegolmEvent,))
    client.add_event_callback(callbacks.unknown, (UnknownEvent,))

    asyncio.create_task(schedule_daily_task(client, store))

    # Keep trying to reconnect on failure (with some time in-between)
    while True:
        try:
            if config.user_token:
                # Use token to log in
                client.load_store()

                # Sync encryption keys with the server
                if client.should_upload_keys:
                    await client.keys_upload()
            else:
                # Try to login with the configured username/password
                try:
                    login_response = await client.login(
                        password=config.user_password,
                        device_name=config.device_name,
                    )

                    # Check if login failed
                    if type(login_response) == LoginError:
                        logger.error("Failed to login: %s", login_response.message)
                        return False
                except LocalProtocolError as e:
                    # There's an edge case here where the user hasn't installed the correct C
                    # dependencies. In that case, a LocalProtocolError is raised on login.
                    logger.fatal(
                        "Failed to login. Have you installed the correct dependencies? "
                        "https://github.com/poljar/matrix-nio#installation "
                        "Error: %s",
                        e,
                    )
                    return False

                # Login succeeded!

            logger.info(f"Logged in as {config.user_id}")
            await client.sync_forever(timeout=30000, full_state=True)

        except (ClientConnectionError, ServerDisconnectedError):
            logger.warning("Unable to connect to homeserver, retrying in 15s...")

            # Sleep so we don't bombard the server with login requests
            sleep(15)
        finally:
            # Make sure to close the client connection on disconnect
            await client.close()


# Run the main function in an asyncio event loop
asyncio.get_event_loop().run_until_complete(main())
