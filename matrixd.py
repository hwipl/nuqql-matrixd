#!/usr/bin/env python3

"""
matrixd
"""

import sys
import asyncio
import html
import re

from threading import Thread, Lock, Event

from matrix_client.client import MatrixClient


import based

# dictionary for all client connections
CONNECTIONS = {}
THREADS = []


class NuqqlClient():
    """
    Nuqql Client Class
    """

    def __init__(self, url, username, password, lock):

        self.client = MatrixClient(url)
        self.token = self.client.login(username=username, password=password)

        # event handlers
        # TODO: add

        # data structures
        # TODO: add
        self.lock = lock
        self.buddies = []

        # misc
        # room = client.create_room("my_room_alias")
        # room.send_text("Hello!")

    def message(self, msg):
        """
        Message handler
        """

    def muc_message(self, msg):
        """
        Groupchat message handler.
        """
        # TODO: if we do nothing extra here, move it into normal message
        # handler above?

    def _muc_presence(self, presence, status):
        """
        Group chat presence handler
        """

        # get chat and our nick in the chat

    def muc_online(self, presence):
        """
        Group chat online presence handler
        """

        self._muc_presence(presence, "online")

    def muc_offline(self, presence):
        """
        Group chat offline presence handler
        """

        self._muc_presence(presence, "offline")

    def collect(self):
        """
        Collect all messages from message log
        """

    def get_messages(self):
        """
        Read incoming messages
        """

    def get_events(self):
        """
        Read (muc) events
        """

    def enqueue_message(self, message_tuple):
        """
        Enqueue a message tuple in the message queue
        Tuple consists of:
            dest, msg, html_msg, msg_type
        """

    def send_queue(self):
        """
        Send all queued messages
        """

    def update_buddies(self):
        """
        Create a "safe" copy of roster
        """


def update_buddies(account):
    """
    Read buddies from client connection
    """

    try:
        client = CONNECTIONS[account.aid]
    except KeyError:
        # no active connection
        return

    # clear buddy list
    account.buddies = []

    # parse buddy list and insert buddies into buddy list
    client.lock.acquire()
    for buddy in client.buddies:
        account.buddies.append(buddy)
    client.lock.release()


def format_messages(account, messages):
    """
    format messages for get_messages() and collect_messages()
    """

    ret = []
    for tstamp, msg in messages:
        # nuqql expects html-escaped messages; construct them
        msg_body = msg["body"]
        msg_body = html.escape(msg_body)
        msg_body = "<br/>".join(msg_body.split("\n"))
        # ret_str = "message: {} {} {} {} {}".format(account.aid, msg["to"],
        #                                            tstamp, msg["from"],
        #                                            msg_body)
        ret_str = ""    # FIXME
        ret.append(ret_str)
    return ret


def format_events(account, events):
    """
    Format events for get_messages()
    """

    ret = []
    for tstamp, chat, nick, msg in events:
        ret_str = "message: {} {} {} {} {}".format(account.aid, chat, tstamp,
                                                   chat + "/" + nick, msg)
        ret.append(ret_str)
    return ret


def get_messages(account):
    """
    Read messages from client connection
    """

    try:
        client = CONNECTIONS[account.aid]
    except KeyError:
        # no active connection
        return []

    # get messages
    messages = format_messages(account, client.get_messages())

    # get events
    # TODO: add function call for events in based.py and new message format?
    events = format_events(account, client.get_events())

    # return messages and event
    return messages + events


def collect_messages(account):
    """
    Collect all messages from client connection
    """

    try:
        client = CONNECTIONS[account.aid]
    except KeyError:
        # no active connection
        return []

    # collect messages
    messages = client.collect()

    # format and return them
    return format_messages(account, messages)


def send_message(account, dest, msg, msg_type="chat"):
    """
    send a message to a destination  on an account
    """

    try:
        client = CONNECTIONS[account.aid]
    except KeyError:
        # no active connection
        return

    # nuqql sends a html-escaped message; construct "plain-text" version and
    # xhtml version using nuqql's message and use them as message body later
    html_msg = \
        '<body xmlns="http://www.w3.org/1999/xhtml">{}</body>'.format(msg)
    msg = html.unescape(msg)
    msg = "\n".join(re.split("<br/>", msg, flags=re.IGNORECASE))

    # send message
    client.enqueue_message((dest, msg, html_msg, msg_type))


def set_status(account, status):
    """
    Set the current status of the account
    """

    try:
        client = CONNECTIONS[account.aid]
    except KeyError:
        # no active connection
        return


def get_status(account):
    """
    Get the current status of the account
    """

    try:
        client = CONNECTIONS[account.aid]
    except KeyError:
        # no active connection
        return ""

    status = "offline"

    return status


def chat_list(account):
    """
    List active chats of account
    """

    ret = []
    try:
        client = CONNECTIONS[account.aid]
    except KeyError:
        # no active connection
        return ret

    return ret


def chat_join(account, chat, nick=""):
    """
    Join chat on account
    """

    try:
        client = CONNECTIONS[account.aid]
    except KeyError:
        # no active connection
        return ""

    return ""


def chat_part(account, chat):
    """
    Leave chat on account
    """

    try:
        client = CONNECTIONS[account.aid]
    except KeyError:
        # no active connection
        return ""

    return ""


def chat_send(account, chat, msg):
    """
    Send message to chat on account
    """

    send_message(account, chat, msg, msg_type="groupchat")
    return ""


def chat_users(account, chat):
    """
    Get list of users in chat on account
    """

    ret = []
    try:
        client = CONNECTIONS[account.aid]
    except KeyError:
        # no active connection
        return ret

    roster = []     # FIXME
    for user in roster:
        if user == "":
            continue
        ret.append("chat: user: {} {} {}".format(account.aid, chat, user))

    return ret


def run_client(account, ready, running):
    """
    Run client connection in a new thread,
    as long as running Event is set to true.
    """

    # get event loop for thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # create a new lock for the thread
    lock = Lock()

    # start client connection
    url = ""        # FIXME
    user = ""       # FIXME
    password = ""   # FIXME
    client = NuqqlClient(url, user, password, lock)

    # save client connection in active connections dictionary
    CONNECTIONS[account.aid] = client

    # thread is ready to enter main loop, inform caller
    ready.set()

    # enter main loop, and keep running until "running" is set to false
    # by the KeyboardInterrupt
    while running.is_set():
        # process client for 0.1 seconds, then send pending outgoing
        # messages and update the (safe copy of the) buddy list
        # client.process(timeout=0.1)
        # client.send_queue()
        # client.update_buddies()
        pass


def add_account(account):
    """
    Add a new account (from based) and run a new client thread for it
    """

    # event to signal thread is ready
    ready = Event()

    # event to signal if thread should stop
    running = Event()
    running.set()

    # create and start thread
    new_thread = Thread(target=run_client, args=(account, ready, running))
    new_thread.start()

    # save thread in active threads dictionary
    THREADS.append((new_thread, running))

    # wait until thread initialized everything
    ready.wait()


def main():
    """
    Main function, initialize everything and start server
    """

    # parse command line arguments
    based.get_command_line_args()

    # load accounts
    based.load_accounts()

    # initialize loggers
    based.init_loggers()

    # start a client connection for every matrix account in it's own thread
    for acc in based.ACCOUNTS.values():
        if acc.type == "matrix":
            add_account(acc)

    # register callbacks
    based.CALLBACKS["add_account"] = add_account
    based.CALLBACKS["update_buddies"] = update_buddies
    based.CALLBACKS["get_messages"] = get_messages
    based.CALLBACKS["send_message"] = send_message
    based.CALLBACKS["collect_messages"] = collect_messages
    based.CALLBACKS["set_status"] = set_status
    based.CALLBACKS["get_status"] = get_status
    based.CALLBACKS["chat_list"] = chat_list
    based.CALLBACKS["chat_join"] = chat_join
    based.CALLBACKS["chat_part"] = chat_part
    based.CALLBACKS["chat_send"] = chat_send
    based.CALLBACKS["chat_users"] = chat_users

    # run the server for the nuqql connection
    try:
        based.run_server(based.ARGS)
    except KeyboardInterrupt:
        # try to terminate all threads
        for thread, running in THREADS:
            running.clear()
            thread.join()
        sys.exit()


if __name__ == '__main__':
    main()
