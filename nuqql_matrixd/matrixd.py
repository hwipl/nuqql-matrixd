#!/usr/bin/env python3

"""
matrixd
"""

import asyncio
import html
import re
import urllib.parse
import time
import os
import stat

from threading import Thread, Lock, Event
from types import SimpleNamespace

# matrix imports
from matrix_client.client import MatrixClient
from matrix_client.errors import MatrixRequestError
from matrix_client.errors import MatrixHttpLibError

# nuqq-based imports
from nuqql_based.based import Based
from nuqql_based.message import Message
from nuqql_based.callback import Callback


class BackendClient():
    """
    Backend Client Class for connections to the IM network
    """

    def __init__(self, account, lock):
        # account
        self.account = account

        # server connection
        self.client = None
        self.token = None
        self.user = ""
        self.config = SimpleNamespace(
            # Send regular message to client for membership events?
            membership_message_msg=True,
            # Send user message to client for membership events?
            membership_user_msg=True,
            # Filter own messages?
            filter_own=True
        )

        # data structures
        self.lock = lock
        self.status = "offline"
        self.queue = []

        # separate data structure for managing room invites
        self.room_invites = {}

        # misc
        # room = client.create_room("my_room_alias")
        # room.send_text("Hello!")

    def connect(self, url, username, domain, password):
        """
        Connect to server
        """

        try:
            # initialize matrix client connection
            # construct matrix user name with user and domain name
            self.user = "@{}:{}".format(username, domain)
            self.client = MatrixClient(url)

            # add event handlers
            self.client.add_listener(self.listener)
            self.client.add_presence_listener(self.presence_listener)
            self.client.add_invite_listener(self.invite_listener)
            self.client.add_leave_listener(self.leave_listener)
            self.client.add_ephemeral_listener(self.ephemeral_listener)

            # login and limit sync to only retrieve 0 events per room, so we do
            # not get old messages again. this changes the sync_filter. so, we
            # have to save the defaults and apply them after login to get
            # events again.
            sync_filter = self.client.sync_filter
            self.token = self.client.login(username=username,
                                           password=password, limit=0)
            self.client.sync_filter = sync_filter
            self.status = "online"

        except (MatrixRequestError, MatrixHttpLibError) as error:
            self.account.logger.error(error)
            self.status = "offline"

    def listener_exception(self, exception):
        """
        Handle listener exception
        """

        error = "Stopping listener because exception occured " \
                "in listener: {}".format(exception)
        self.account.logger.error(error)
        self.client.should_listen = False
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
        except MatrixHttpLibError as error:
            self.status = "offline"
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
            user_msg = Message.chat_user(self.account, room_id, invited_user,
                                         invited_user, membership)
            msg = "*** {} invited {} to {}. ***".format(sender_name,
                                                        invited_user,
                                                        room_name)
        if membership == "join":
            invited_user = event["content"]["displayname"]
            user_msg = Message.chat_user(self.account, room_id, sender,
                                         invited_user, membership)
            msg = "*** {} joined {}. ***".format(invited_user, room_name)

        if membership == "leave":
            user_msg = Message.chat_user(self.account, room_id, sender,
                                         sender_name, membership)
            msg = "*** {} left {}. ***".format(sender_name, room_name)

        # generic event, return as message
        # TODO: change parsing in nuqql and use char + / + sender here?
        formatted_msg = Message.CHAT_MSG.format(self.account.aid, room_id,
                                                tstamp, sender, msg)

        # add event to event list
        if self.config.membership_user_msg:
            self.account.receive_msg(user_msg)
        if self.config.membership_message_msg:
            self.account.receive_msg(formatted_msg)

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
                except MatrixHttpLibError as error:
                    sender_name = sender
                    self.status = "offline"
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
        if self.config.filter_own and msg["sender"] == self.user:
            return

        # save timestamp and message in messages list and history
        tstamp = int(int(msg["origin_server_ts"])/1000)
        formatted_msg = Message.chat_msg(
            self.account, tstamp, msg["sender"], msg["room_id"],
            msg["content"]["body"])
        self.account.receive_msg(formatted_msg)

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
        dest, msg, html_msg, _mtype = message_tuple

        rooms = self._get_rooms()
        for room in rooms.values():
            if dest in (room.display_name, room.room_id):
                try:
                    room.send_html(html_msg, body=msg, msgtype='m.text')
                except MatrixRequestError as error:
                    # TODO: return error to connected user?
                    self.account.logger.error(error)
                except MatrixHttpLibError as error:
                    self.status = "offline"
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

        self.account.receive_msg(Message.status(self.account, self.status))

    def _chat_list(self):
        """
        List active chats of account
        """

        rooms = self._get_rooms()
        for room in rooms.values():
            self.account.receive_msg(Message.chat_list(
                self.account, room.room_id, escape_name(room.display_name),
                self.user))

    def _chat_create(self, name):
        """
        Create a group chat room with name <name>
        """

        try:
            room = self.client.create_room()
            room.set_room_name(name)
        except MatrixRequestError as error:
            self.account.receive_msg(Message.error(
                "code: {} content: {}".format(error.code, error.content)))
        except MatrixHttpLibError as error:
            self.status = "offline"
            self.account.logger.error(error)

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
            self.account.receive_msg(Message.error(
                "code: {} content: {}".format(error.code, error.content)))
        except MatrixHttpLibError as error:
            self.status = "offline"
            self.account.logger.error(error)

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
                    self.account.receive_msg(Message.error(
                        "code: {} content: {}".format(error.code,
                                                      error.content)))
                    return
                except MatrixHttpLibError as error:
                    self.status = "offline"
                    self.account.logger.error(error)
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
                    self.account.receive_msg(Message.error(
                        "code: {} content: {}".format(error.code,
                                                      error.content)))
                    return
                except MatrixHttpLibError as error:
                    self.status = "offline"
                    self.account.logger.error(error)
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
                except MatrixHttpLibError as error:
                    self.status = "offline"
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
                    self.account.receive_msg(Message.chat_user(
                        self.account, chat, user_id, name, status))

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
                    self.account.receive_msg(Message.error(
                        "code: {} content: {}".format(error.code,
                                                      error.content)))
                    return
                except MatrixHttpLibError as error:
                    self.status = "offline"
                    self.account.logger.error(error)

    def update_buddies(self):
        """
        Create a "safe" copy of roster
        """

        # if we are offline, there are no buddies
        if self.status == "offline":
            self.account.flush_buddies()
            return

        # get buddies/rooms
        buddies = []
        rooms = self._get_rooms()
        for room in rooms.values():
            name = escape_name(room.display_name)

            # use special status for group chats
            status = "GROUP_CHAT"

            # add buddies to buddy list
            buddy = (room.room_id, name, status)
            buddies.append(buddy)

            # cleanup old invites
            if room.room_id in self.room_invites:
                # seems like we are in the room now, remove invite
                del self.room_invites[room.room_id]

        # handle pending room invites as temporary buddies
        for invite in self.room_invites.values():
            room_id, room_name, _sender, _sender_name, _tstamp = invite
            status = "GROUP_CHAT_INVITE"
            buddy = (room_id, room_name, status)
            buddies.append(buddy)

        # update account's buddy list with buddies
        self.account.update_buddies(buddies)

    def _get_rooms(self):
        """
        Get list of rooms
        """

        try:
            rooms = self.client.get_rooms()
        except MatrixRequestError as error:
            self.account.logger.error(error)
            rooms = []
        except MatrixHttpLibError as error:
            self.status = "offline"
            self.account.logger.error(error)
            rooms = []
        return rooms


class BackendServer:
    """
    Backend server class, manages the BackendClients for connections to
    IM networks
    """

    def __init__(self):
        self.connections = {}
        self.threads = {}

        # set callbacks
        callbacks = [
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

        # start based
        self.based = Based("matrixd", callbacks)

    def start(self):
        """
        Start server
        """

        self.based.start()

    def enqueue(self, account_id, cmd, params):
        """
        add commands to the command queue of the account/client
        """

        try:
            client = self.connections[account_id]
        except KeyError:
            # no active connection
            return ""

        client.enqueue_command(cmd, params)

        return ""

    def send_message(self, account_id, cmd, params):
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
        self.enqueue(account_id, cmd, (unescape_name(dest), msg, html_msg,
                                       msg_type))

        return ""

    def chat_send(self, account_id, _cmd, params):
        """
        Send message to chat on account
        """

        chat, msg = params
        # TODO: use cmd to infer msg type in send_message and remove this
        # function?
        return self.send_message(account_id, Callback.SEND_MESSAGE,
                                 (chat, msg, "groupchat"))

    def load_sync_token(self, acc_id):
        """
        Load an old sync token from file if available
        """

        # make sure path and file exist
        self.based.config.get_dir().mkdir(parents=True, exist_ok=True)
        os.chmod(self.based.config.get_dir(), stat.S_IRWXU)
        sync_token_file = self.based.config.get_dir() / f"sync_token{acc_id}"
        if not sync_token_file.exists():
            open(sync_token_file, "a").close()

        # make sure only user can read/write file before using it
        os.chmod(sync_token_file, stat.S_IRUSR | stat.S_IWUSR)

        try:
            with open(sync_token_file, "r") as token_file:
                token = token_file.readline()
        except OSError:
            token = ""

        return token

    def update_sync_token(self, acc_id, old, new):
        """
        Update an existing sync token with a newer one
        """

        if old == new:
            # tokens are not different
            return old

        # update token file
        sync_token_file = self.based.config.get_dir() / f"/sync_token{acc_id}"

        try:
            with open(sync_token_file, "w") as token_file:
                token_file.write(new)
        except OSError:
            return old

        return new

    def delete_sync_token(self, acc_id):
        """
        Delete the sync token file for the account, called when account is
        removed
        """

        sync_token_file = self.based.config.get_dir() / f"/sync_token{acc_id}"
        if not sync_token_file.exists():
            return

        os.remove(sync_token_file)

    def run_client(self, account, ready, running):
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
        url, user, domain = parse_account_user(account.user)

        # init client connection
        client = BackendClient(account, lock)

        # save client connection in active connections dictionary
        self.connections[account.aid] = client

        # thread is ready to enter main loop, inform caller
        ready.set()

        # enter main loop, and keep running until "running" is set to false
        # by the KeyboardInterrupt
        while running.is_set():
            # if client is offline, (re)connect
            if client.status == "offline":
                # if there is an old listener, stop it
                if client.client:
                    client.client.stop_listener_thread()

                # start client connection
                client.connect(url, user, domain, account.password)

                # initialize sync token with last known value
                sync_token = self.load_sync_token(account.aid)
                client.client.sync_token = sync_token

                # start the listener thread in the matrix client
                client.client.start_listener_thread(
                    exception_handler=client.listener_exception)

                # skip other parts until the client is really online
                continue

            # send pending outgoing messages, update the (safe copy of the)
            # buddy list, update the sync token, then sleep a little bit
            client.handle_queue()
            client.update_buddies()
            sync_token = self.update_sync_token(account.aid, sync_token,
                                                client.client.sync_token)
            time.sleep(0.1)

        # stop the listener thread in the matrix client
        client.client.stop_listener_thread()

    def add_account(self, account_id, _cmd, params):
        """
        Add a new account (from based) and run a new client thread for it
        """

        # only handle matrix accounts
        account = params[0]
        if account.type != "matrix":
            return ""

        # event to signal thread is ready
        ready = Event()

        # event to signal if thread should stop
        running = Event()
        running.set()

        # create and start thread
        new_thread = Thread(target=self.run_client, args=(account, ready,
                                                          running))
        new_thread.start()

        # save thread in active threads dictionary
        self.threads[account_id] = (new_thread, running)

        # wait until thread initialized everything
        ready.wait()

        return ""

    def del_account(self, account_id, _cmd, _params):
        """
        Delete an existing account (in based) and
        stop matrix client thread for it
        """

        # stop thread
        thread, running = self.threads[account_id]
        running.clear()
        thread.join()

        # delete sync token file
        self.delete_sync_token(account_id)

        # cleanup
        del self.connections[account_id]
        del self.threads[account_id]

        return ""

    def stop_thread(self, account_id, _cmd, _params):
        """
        Quit backend/stop client thread
        """

        # stop thread
        print("Signalling account thread to stop.")
        _thread, running = self.threads[account_id]
        running.clear()

    def based_interrupt(self, _account_id, _cmd, _params):
        """
        KeyboardInterrupt event in based
        """

        for _thread, running in self.threads.values():
            print("Signalling account thread to stop.")
            running.clear()

    def based_quit(self, _account_id, _cmd, _params):
        """
        Based shut down event
        """

        print("Waiting for all threads to finish. This might take a while.")
        for thread, _running in self.threads.values():
            thread.join()


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


def parse_account_user(acc_user):
    """
    Parse the user configured in the account to extract the matrix user, domain
    and base url
    """

    # get user name and homeserver part from account user
    user, homeserver = acc_user.split("@", maxsplit=1)

    if homeserver.startswith("http://") or homeserver.startswith("https://"):
        # assume homeserver part contains url
        url = homeserver

        # extract domain name, strip http(s) from homeserver name
        domain = homeserver.split("//", maxsplit=1)[1]

        # strip port from remaining domain name
        domain = domain.split(":", maxsplit=1)[0]
    else:
        # assume homeserver part only contains the domain
        domain = homeserver

        # construct url, default to https
        url = "https://" + domain

    return url, user, domain


def main():
    """
    Main function, initialize everything and start server
    """

    server = BackendServer()
    server.start()


if __name__ == '__main__':
    main()
