#!/usr/bin/env python3

"""
matrixd
"""

import sys
import asyncio
import html
import re
import urllib.parse
import time

from threading import Thread, Lock, Event

from matrix_client.client import MatrixClient
from matrix_client.errors import MatrixRequestError


import based
from based import Format, Callback

# dictionary for all client connections
CONNECTIONS = {}
THREADS = {}


class NuqqlClient():
    """
    Nuqql Client Class
    """

    def __init__(self, account, lock):
        # account
        self.account = account

        # server connection
        self.client = None
        self.token = None
        self.user = ""
        self.filter_own = True  # Filter own messages?

        # data structures
        self.lock = lock
        self.status = "online"
        self.buddies = []
        self.history = []
        self.messages = []
        self.queue = []

        # separate data structure for managing room invites
        self.room_invites = {}

        # misc
        # room = client.create_room("my_room_alias")
        # room.send_text("Hello!")

    def connect(self, url, username, password):
        """
        Connect to server
        """

        try:
            # initialize matrix client connection
            # construct matrix user name, remove "http://" from url
            self.user = "@{}:{}".format(username, url[7:])
            self.client = MatrixClient(url)

            # add event handlers
            self.client.add_listener(self.listener)
            self.client.add_presence_listener(self.presence_listener)
            self.client.add_invite_listener(self.invite_listener)
            self.client.add_leave_listener(self.leave_listener)
            self.client.add_ephemeral_listener(self.ephemeral_listener)

            # login
            self.token = self.client.login(username=username,
                                           password=password, sync=False)

        except MatrixRequestError as error:
            self.account.logger.error(error)
            self.status = "offline"

    def _membership_event(self, event):
        """
        Handle membership event
        """

        # parse event
        sender = event["sender"]
        try:
            sender_name = self.client.get_user(sender).get_display_name()
        except MatrixRequestError as error:
            sender_name = sender
            self.account.logger.error(error)
        room_id = event["room_id"]
        room_name = room_id
        membership = event["content"]["membership"]
        tstamp = int(int(event["origin_server_ts"])/1000)

        # get room name
        rooms = self._get_rooms()
        room_name = rooms[room_id].display_name

        # check membership type
        if membership == "invite":
            invited_user = event["content"]["displayname"]
            msg = "*** {} invited {} to {}. ***".format(sender_name,
                                                        invited_user,
                                                        room_name)
        if membership == "join":
            invited_user = event["content"]["displayname"]
            msg = "*** {} joined {}. ***".format(invited_user, room_name)

        if membership == "leave":
            msg = "*** {} left {}. ***".format(sender_name, room_name)

        # generic event, return as message
        # TODO: change parsing in nuqql and use char + / + sender here?
        formatted_msg = Format.MESSAGE.format(self.account.aid, room_id,
                                              tstamp, sender, msg)

        # add event to event list
        self.lock.acquire()
        self.messages.append(formatted_msg)
        self.lock.release()

    def listener(self, event):
        """
        Event listener
        """

        self.account.logger.debug("listener: {}".format(event))
        if event["type"] == "m.room.message":
            self.message(event)
        if event["type"] == "m.room.member":
            self._membership_event(event)

    def presence_listener(self, event):
        """
        Presence event listener
        """

        self.account.logger.debug("presence: {}".format(event))

    def invite_listener(self, room_id, events):
        """
        Invite event listener
        """

        # get sender, room_name, and timestamp of invite
        sender = "unknown"
        sender_name = "unknown"
        room_name = room_id
        tstamp = int(time.time())
        for event in events["events"]:
            # get sender of invite
            if event["type"] == "m.room.join_rules" and \
               event["content"]["join_rule"] == "invite":
                sender = event["sender"]
                try:
                    sender_name = \
                            self.client.get_user(sender).get_display_name()
                except MatrixRequestError as error:
                    sender_name = sender
                    self.account.logger.error(error)

            # try to get timestamp
            if "origin_server_ts" in event:
                tstamp = int(int(event["origin_server_ts"])/1000)

            # try to get room name
            if event["type"] == "m.room.name":
                # it is a normal room
                room_name = event["content"]["name"]
        # if we did not find a room.name entry, assume it's a direct chat...
        if room_name == room_id:
            # ... and use sender name as direct chat name
            room_name = sender_name

        # construct invite data structure
        invite = room_id, room_name, sender, sender_name, tstamp

        # add event to event list
        self.room_invites[room_id] = invite

    def leave_listener(self, room_id, event):
        """
        Leave event listener
        """

        self.account.logger.debug("leave: {} {}".format(room_id, event))

    def ephemeral_listener(self, event):
        """
        Ephemeral event listener
        """

        self.account.logger.debug("ephemeral: {}".format(event))

    def message(self, msg):
        """
        Message handler
        """

        # if filter_own is set, skip own messages
        if self.filter_own and msg["sender"] == self.user:
            return

        # save timestamp and message in messages list and history
        tstamp = int(int(msg["origin_server_ts"])/1000)
        formatted_msg = based.format_message(
            self.account, tstamp, msg["sender"], msg["room_id"],
            msg["content"]["body"])
        self.lock.acquire()
        self.messages.append(formatted_msg)
        self.history.append(formatted_msg)
        self.lock.release()

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

        self.lock.acquire()
        # create a copy of the history
        history = self.history[:]
        self.lock.release()

        # return the copy of the history
        return history

    def get_messages(self):
        """
        Read incoming messages
        """

        self.lock.acquire()
        # create a copy of the message list, and flush the message list
        messages = self.messages[:]
        self.messages = []
        self.lock.release()

        # return the copy of the message list
        return messages

    def enqueue_command(self, cmd, params):
        """
        Enqueue a command in the command queue
        Tuple consists of:
            command and its parameters
        """

        self.lock.acquire()
        # just add message tuple to queue
        self.queue.append((cmd, params))
        self.lock.release()

    def handle_queue(self):
        """
        Handle all queued commands
        """

        # create temporary copy and flush queue
        self.lock.acquire()
        queue = self.queue[:]
        self.queue = []
        self.lock.release()

        for cmd, params in queue:
            if cmd == Callback.SEND_MESSAGE:
                self._send_message(params)
            if cmd == Callback.SET_STATUS:
                self._set_status(params[0])
            if cmd == Callback.GET_STATUS:
                self._get_status()
            if cmd == Callback.CHAT_LIST:
                self._chat_list()
            if cmd == Callback.CHAT_JOIN:
                self._chat_join(params[0])
            if cmd == Callback.CHAT_PART:
                self._chat_part(params[0])
            if cmd == Callback.CHAT_USERS:
                self._chat_users(params[0])
            if cmd == Callback.CHAT_INVITE:
                self._chat_invite(params[0], params[1])

    def _send_message(self, message_tuple):
        """
        Send a single message
        """

        # if we are offline, send nothing
        # TODO: remove this?
        if self.status == "offline":
            return

        # create message from message tuple and send it
        dest, msg, html_msg, mtype = message_tuple

        rooms = self._get_rooms()
        for room in rooms.values():
            if dest in (room.display_name, room.room_id):
                try:
                    room.send_html(html_msg, body=msg, msgtype='m.text')
                except MatrixRequestError as error:
                    # TODO: return error to connected user?
                    self.account.logger.error(error)
                return

    def _set_status(self, status):
        """
        Set the current status of the account
        """

        # TODO: do something when status changes, e.g., from offline to online?
        self.status = status

    def _get_status(self):
        """
        Get the current status of the account
        """

        self.lock.acquire()
        self.messages.append(Format.STATUS.format(self.account.aid,
                                                  self.status))
        self.lock.release()

    def _chat_list(self):
        """
        List active chats of account
        """

        rooms = self._get_rooms()
        for room in rooms.values():
            self.lock.acquire()
            self.messages.append(Format.CHAT_LIST.format(
                self.account.aid, room.room_id, escape_name(room.display_name),
                self.user))
            self.lock.release()

    def _chat_create(self, name):
        """
        Create a group chat room with name <name>
        """

        try:
            room = self.client.create_room()
            room.set_room_name(name)
        except MatrixRequestError as error:
            self.lock.acquire()
            self.messages.append(Format.ERROR.format(
                "code: {} content: {}".format(error.code, error.content)))
            self.lock.release()

    def _chat_join(self, chat):
        """
        Join chat on account
        """

        try:
            chat = unescape_name(chat)
            self.client.join_room(chat)
        except MatrixRequestError as error:
            # joining an existing room failed.
            # if chat is not a room id, try to create a new room
            if not chat.startswith("!") or ":" not in chat:
                self._chat_create(chat)
                return
            self.lock.acquire()
            self.messages.append(Format.ERROR.format(
                "code: {} content: {}".format(error.code, error.content)))
            self.lock.release()

    def _chat_part(self, chat):
        """
        Leave chat on account
        """

        # part an already joined room
        rooms = self._get_rooms()
        for room in rooms.values():
            if unescape_name(chat) == room.display_name or \
               unescape_name(chat) == room.room_id:
                try:
                    room.leave()
                except MatrixRequestError as error:
                    self.lock.acquire()
                    self.messages.append(Format.ERROR.format(
                        "code: {} content: {}".format(error.code,
                                                      error.content)))
                    self.lock.release()
                    return
                return
        # part a room we are invited to
        # TODO: add locking
        for invite in self.room_invites.values():
            room_id, room_name, _sender, _sender_name, _tstamp = invite
            if unescape_name(chat) == room_name or \
               unescape_name(chat) == room_id:
                try:
                    self.client.api.leave_room(room_id)
                except MatrixRequestError as error:
                    self.lock.acquire()
                    self.messages.append(Format.ERROR.format(
                        "code: {} content: {}".format(error.code,
                                                      error.content)))
                    self.lock.release()
                    return
                # remove room from invites
                self.room_invites = {k: v for k, v in self.room_invites.items()
                                     if k != room_id}
                return

        return

    def _chat_users(self, chat):
        """
        Get list of users in chat on account
        """

        roster = {}
        rooms = self._get_rooms()
        for room_id, room in rooms.items():
            if unescape_name(chat) == room.display_name or \
               unescape_name(chat) == room_id:
                try:
                    roster = self.client.api.get_room_members(room_id)
                except MatrixRequestError as error:
                    self.account.logger.error(error)
                    roster = {}

        # TODO: use roster['chunk'] instead?
        for chunk in roster.values():
            for user in chunk:
                if user['type'] != 'm.room.member':
                    continue
                if user['content'] and \
                   user['content']['membership'] in ('join', 'invite') and \
                   'displayname' in user['content']:
                    name = escape_name(user['content']['displayname'])
                    status = user['content']['membership']
                    if user['content']['membership'] == 'join':
                        # this member is already in the room
                        user_id = user['user_id']
                    else:
                        # this member is only invited to the room.
                        # user['user_id'] is the sender of the invite,
                        # use fake user id.
                        user_id = "@{}:<invited>".format(name)
                    self.lock.acquire()
                    self.messages.append(Format.CHAT_USER.format(
                        self.account.aid, chat, user_id, name, status))
                    self.lock.release()

    def _chat_invite(self, chat, user_id):
        """
        Invite user to chat
        """

        rooms = self._get_rooms()
        for room in rooms.values():
            if unescape_name(chat) == room.display_name or \
               unescape_name(chat) == room.room_id:
                try:
                    room.invite_user(user_id)
                except MatrixRequestError as error:
                    self.lock.acquire()
                    self.messages.append(Format.ERROR.format(
                        "code: {} content: {}".format(error.code,
                                                      error.content)))
                    self.lock.release()
                    return

    def update_buddies(self):
        """
        Create a "safe" copy of roster
        """

        # if we are offline, there are no buddies
        if self.status == "offline":
            self.lock.acquire()
            self.buddies = []
            self.lock.release()
            return

        # get buddies/rooms
        buddies = []
        rooms = self._get_rooms()
        for room in rooms.values():
            name = escape_name(room.display_name)

            # use special status for group chats
            status = "GROUP_CHAT"

            # add buddies to buddy list
            buddy = based.Buddy(name=room.room_id, alias=name, status=status)
            buddies.append(buddy)

            # cleanup old invites
            if room.room_id in self.room_invites:
                # seems like we are in the room now, remove invite
                del self.room_invites[room.room_id]

        # handle pending room invites as temporary buddies
        for invite in self.room_invites.values():
            room_id, room_name, _sender, _sender_name, _tstamp = invite
            status = "GROUP_CHAT_INVITE"
            buddy = based.Buddy(name=room_id, alias=room_name, status=status)
            buddies.append(buddy)

        self.lock.acquire()
        # flush buddy list
        self.buddies = buddies
        self.lock.release()

    def process(self, timeout=None):
        """
        Process client for timeout seconds
        """

        if not timeout or self.status == "offline":
            return

        try:
            self.client.listen_for_events(timeout_ms=int(timeout * 1000))
        except MatrixRequestError as error:
            self.account.logger.error(error)

    def _get_rooms(self):
        """
        Get list of rooms
        """

        try:
            rooms = self.client.get_rooms()
        except MatrixRequestError as error:
            self.account.logger.error(error)
            rooms = []
        return rooms


def update_buddies(account_id, _cmd, _params):
    """
    Read buddies from client connection
    """

    try:
        client = CONNECTIONS[account_id]
    except KeyError:
        # no active connection
        return ""

    # TODO: rework this?
    # clear buddy list
    client.account.buddies = []

    # parse buddy list and insert buddies into buddy list
    client.lock.acquire()
    for buddy in client.buddies:
        client.account.buddies.append(buddy)
    client.lock.release()

    return ""


def get_messages(account_id, _cmd, _params):
    """
    Read messages from client connection
    """

    try:
        client = CONNECTIONS[account_id]
    except KeyError:
        # no active connection
        return ""

    # get and return messages
    return "".join(client.get_messages())


def collect_messages(account_id, _cmd, _params):
    """
    Collect all messages from client connection
    """

    try:
        client = CONNECTIONS[account_id]
    except KeyError:
        # no active connection
        return ""

    # collect and return messages
    return "".join(client.collect())


def enqueue(account_id, cmd, params):
    """
    Helper for adding commands to the command queue of the account/client
    """

    try:
        client = CONNECTIONS[account_id]
    except KeyError:
        # no active connection
        return ""

    client.enqueue_command(cmd, params)

    return ""


def send_message(account_id, cmd, params):
    """
    send a message to a destination  on an account
    """

    # parse parameters
    if len(params) > 2:
        dest, msg, msg_type = params
    else:
        dest, msg = params
        msg_type = "chat"

    # nuqql sends a html-escaped message; construct "plain-text" version and
    # xhtml version using nuqql's message and use them as message body later
    html_msg = \
        '<body xmlns="http://www.w3.org/1999/xhtml">{}</body>'.format(msg)
    msg = html.unescape(msg)
    msg = "\n".join(re.split("<br/>", msg, flags=re.IGNORECASE))

    # send message
    enqueue(account_id, cmd, (unescape_name(dest), msg, html_msg, msg_type))

    return ""


def chat_send(account_id, _cmd, params):
    """
    Send message to chat on account
    """

    chat, msg = params
    # TODO: use cmd to infer msg type in send_message and remove this function?
    return send_message(account_id, Callback.SEND_MESSAGE,
                        (chat, msg, "groupchat"))


def escape_name(name):
    """
    Escape "invalid" charecters in name, e.g., space.
    """

    # escape spaces etc.
    return urllib.parse.quote(name)


def unescape_name(name):
    """
    Convert name back to unescaped version.
    """

    # unescape spaces etc.
    return urllib.parse.unquote(name)


def run_client(account, ready, running):
    """
    Run client connection in a new thread,
    as long as running Event is set to true.
    """

    # get event loop for thread
    # TODO: remove this here?
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # create a new lock for the thread
    lock = Lock()

    # parse user to get url and username
    user, url = account.user.split("@", maxsplit=1)
    url = "http://" + url

    # init client connection
    client = NuqqlClient(account, lock)

    # save client connection in active connections dictionary
    CONNECTIONS[account.aid] = client

    # thread is ready to enter main loop, inform caller
    ready.set()

    # start client connection
    client.connect(url, user, account.password)

    # enter main loop, and keep running until "running" is set to false
    # by the KeyboardInterrupt
    while running.is_set():
        # process client for 0.1 seconds, then send pending outgoing
        # messages and update the (safe copy of the) buddy list
        client.process(timeout=0.1)
        client.handle_queue()
        client.update_buddies()


def add_account(account_id, _cmd, params):
    """
    Add a new account (from based) and run a new client thread for it
    """

    # event to signal thread is ready
    ready = Event()

    # event to signal if thread should stop
    running = Event()
    running.set()

    # create and start thread
    account = params[0]
    new_thread = Thread(target=run_client, args=(account, ready, running))
    new_thread.start()

    # save thread in active threads dictionary
    THREADS[account_id] = (new_thread, running)

    # wait until thread initialized everything
    ready.wait()

    return ""


def del_account(account_id, _cmd, _params):
    """
    Delete an existing account (in based) and
    stop matrix client thread for it
    """

    # stop thread
    thread, running = THREADS[account_id]
    running.clear()
    thread.join()

    # cleanup
    del CONNECTIONS[account_id]
    del THREADS[account_id]

    return ""


def main():
    """
    Main function, initialize everything and start server
    """

    # parse command line arguments
    args = based.get_command_line_args()

    # load accounts
    based.load_accounts()

    # initialize loggers
    based.init_loggers()

    # start a client connection for every matrix account in it's own thread
    for acc in based.get_accounts().values():
        if acc.type == "matrix":
            add_account(acc.aid, Callback.ADD_ACCOUNT, (acc, ))

    # register callbacks
    based.register_callback(Callback.ADD_ACCOUNT, add_account)
    based.register_callback(Callback.DEL_ACCOUNT, del_account)
    based.register_callback(Callback.UPDATE_BUDDIES, update_buddies)
    based.register_callback(Callback.GET_MESSAGES, get_messages)
    based.register_callback(Callback.SEND_MESSAGE, send_message)
    based.register_callback(Callback.COLLECT_MESSAGES, collect_messages)
    based.register_callback(Callback.SET_STATUS, enqueue)
    based.register_callback(Callback.GET_STATUS, enqueue)
    based.register_callback(Callback.CHAT_LIST, enqueue)
    based.register_callback(Callback.CHAT_JOIN, enqueue)
    based.register_callback(Callback.CHAT_PART, enqueue)
    based.register_callback(Callback.CHAT_SEND, chat_send)
    based.register_callback(Callback.CHAT_USERS, enqueue)
    based.register_callback(Callback.CHAT_INVITE, enqueue)

    # run the server for the nuqql connection
    try:
        based.run_server(args)
    except KeyboardInterrupt:
        # try to terminate all threads
        for thread, running in THREADS.values():
            running.clear()
            thread.join()
        sys.exit()


if __name__ == '__main__':
    main()
