"""
matrixd backend server
"""

import asyncio
import html
import re

from typing import TYPE_CHECKING, Dict, Optional, Tuple

# nuqq-based imports
from nuqql_based.based import Based
from nuqql_based.callback import Callback

# matrixd imports
from nuqql_matrixd.client import BackendClient
from nuqql_matrixd.matrix import unescape_name

if TYPE_CHECKING:   # imports for typing
    # pylint: disable=ungrouped-imports
    from nuqql_based.based import CallbackList
    from nuqql_based.account import Account


# matrixd version
VERSION = "0.4.0"


class BackendServer:
    """
    Backend server class, manages the BackendClients for connections to
    IM networks
    """

    def __init__(self) -> None:
        self.connections: Dict[int, BackendClient] = {}
        self.based = Based("matrixd", VERSION)

    async def start(self) -> None:
        """
        Start server
        """

        # set callbacks
        callbacks: "CallbackList" = [
            # based events
            (Callback.BASED_INTERRUPT, self.based_interrupt),
            (Callback.BASED_QUIT, self.based_quit),

            # nuqql messages
            (Callback.QUIT, self.stop_thread),
            (Callback.ADD_ACCOUNT, self.add_account),
            (Callback.DEL_ACCOUNT, self.del_account),
            (Callback.SEND_MESSAGE, self.send_message),
            (Callback.SET_STATUS, self.enqueue),
            (Callback.GET_STATUS, self.enqueue),
            (Callback.CHAT_LIST, self.enqueue),
            (Callback.CHAT_JOIN, self.enqueue),
            (Callback.CHAT_PART, self.enqueue),
            (Callback.CHAT_SEND, self.chat_send),
            (Callback.CHAT_USERS, self.enqueue),
            (Callback.CHAT_INVITE, self.enqueue),
        ]
        self.based.set_callbacks(callbacks)

        # start based
        await self.based.start()

    async def enqueue(self, account: Optional["Account"], cmd: Callback,
                      params: Tuple) -> str:
        """
        add commands to the command queue of the account/client
        """

        assert account
        try:
            client = self.connections[account.aid]
        except KeyError:
            # no active connection
            return ""

        await client.enqueue_command(cmd, params)

        return ""

    async def send_message(self, account: Optional["Account"], cmd: Callback,
                           params: Tuple) -> str:
        """
        send a message to a destination  on an account
        """

        # parse parameters
        if len(params) > 2:
            dest, msg, msg_type = params
        else:
            dest, msg = params
            msg_type = "chat"

        # nuqql sends a html-escaped message; construct "plain-text" version
        # and xhtml version using nuqql's message and use them as message body
        # later
        html_msg = \
            '<body xmlns="http://www.w3.org/1999/xhtml">{}</body>'.format(msg)
        msg = html.unescape(msg)
        msg = "\n".join(re.split("<br/>", msg, flags=re.IGNORECASE))

        # send message
        await self.enqueue(account, cmd, (unescape_name(dest), msg, html_msg,
                                          msg_type))

        return ""

    async def chat_send(self, account: Optional["Account"], _cmd: Callback,
                        params: Tuple) -> str:
        """
        Send message to chat on account
        """

        chat, msg = params
        # TODO: use cmd to infer msg type in send_message and remove this
        # function?
        return await self.send_message(account, Callback.SEND_MESSAGE,
                                       (chat, msg, "groupchat"))

    async def run_client(self, account: "Account", ready: asyncio.Event,
                         running: asyncio.Event) -> None:
        """
        Run client connection in a new thread,
        as long as running Event is set to true.
        """

        # create a new lock for the thread
        lock = asyncio.Lock()

        # init client connection
        client = BackendClient(account, lock)

        # save client connection in active connections dictionary
        self.connections[account.aid] = client

        # thread is ready to enter main loop, inform caller
        ready.set()

        # start client; this returns when client is stopped
        await client.start(running)

    async def add_account(self, account: Optional["Account"], _cmd: Callback,
                          _params: Tuple) -> str:
        """
        Add a new account (from based) and run a new client thread for it
        """

        # only handle matrix accounts
        assert account
        if account.type != "matrix":
            return ""

        # event to signal thread is ready
        ready = asyncio.Event()

        # event to signal if thread should stop
        running = asyncio.Event()
        running.set()

        # create and start task
        asyncio.create_task(self.run_client(account, ready, running))

        # wait until thread initialized everything
        await ready.wait()

        return ""

    async def del_account(self, account: Optional["Account"], _cmd: Callback,
                          _params: Tuple) -> str:
        """
        Delete an existing account (in based) and
        stop matrix client thread for it
        """

        # let client clean up
        assert account
        client = self.connections[account.aid]
        await client.del_account()

        # cleanup
        del self.connections[account.aid]

        return ""

    async def stop_thread(self, _account: Optional["Account"], _cmd: Callback,
                          _params: Tuple) -> str:
        """
        Quit backend/stop client thread
        """

        # stop thread
        print("Signalling account thread to stop.")
        return ""

    async def based_interrupt(self, _account: Optional["Account"],
                              _cmd: Callback, _params: Tuple) -> str:
        """
        KeyboardInterrupt event in based
        """

        return ""

    async def based_quit(self, _account: Optional["Account"], _cmd: Callback,
                         _params: Tuple) -> str:
        """
        Based shut down event
        """

        print("Waiting for all threads to finish. This might take a while.")
        return ""
