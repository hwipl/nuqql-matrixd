"""
matrixd backend client
"""

import time

from typing import TYPE_CHECKING, Dict, List, Tuple
from threading import Lock
from types import SimpleNamespace

# matrix imports
from matrix_client.client import MatrixClient           # type: ignore
from matrix_client.errors import MatrixRequestError     # type: ignore
from matrix_client.errors import MatrixHttpLibError     # type: ignore

# matrixd import
from nuqql_matrixd.matrix import parse_account_user, escape_name, unescape_name

# nuqq-based imports
from nuqql_based.message import Message
from nuqql_based.callback import Callback

if TYPE_CHECKING:   # imports for typing
    from nuqql_based.account import Account


class BackendClient:
    """
    Backend Client Class for connections to the IM network
    """

    def __init__(self, account: "Account", lock: Lock) -> None:
        # account
        self.account = account

        # parse user to get url and username
        url, user, domain = parse_account_user(account.user)

        # initialize matrix client connection
        self.client = MatrixClient(url)

        # add matrix client event handlers
        self.client.add_listener(self.listener)
        self.client.add_presence_listener(self.presence_listener)
        self.client.add_invite_listener(self.invite_listener)
        self.client.add_leave_listener(self.leave_listener)
        self.client.add_ephemeral_listener(self.ephemeral_listener)

        # construct matrix user name with user and domain name
        self.user = "@{}:{}".format(user, domain)

        # sync token and connection config
        self.token = None
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
        self.queue: List[Tuple[Callback, Tuple]] = []

        # separate data structure for managing room invites
        self.room_invites: Dict[str, Tuple[str, str, str, str, str]] = {}

    def connect(self) -> None:
        """
        Connect to server
        """

        # parse user to get url and username
        _url, username, _domain = parse_account_user(self.account.user)

        try:
            # login and limit sync to only retrieve 0 events per room, so we do
            # not get old messages again. this changes the sync_filter. so, we
            # have to save the defaults and apply them after login to get
            # events again.
            sync_filter = self.client.sync_filter
            self.token = self.client.login(
                username=username, password=self.account.password, limit=0)
            self.client.sync_filter = sync_filter
            self.status = "online"

        except (MatrixRequestError, MatrixHttpLibError) as error:
            self.account.logger.error(error)
            self.status = "offline"

    def listener_exception(self, exception: Exception) -> None:
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

    def message(self, msg) -> None:
        """
        Message handler
        """

        # if filter_own is set, skip own messages
        if self.config.filter_own and msg["sender"] == self.user:
            return

        # save timestamp and message in messages list and history
        tstamp = str(int(int(msg["origin_server_ts"])/1000))
        formatted_msg = Message.chat_msg(
            self.account, tstamp, msg["sender"], msg["room_id"],
            msg["content"]["body"])
        self.account.receive_msg(formatted_msg)

    def muc_message(self, msg) -> None:
        """
        Groupchat message handler.
        """
        # TODO: if we do nothing extra here, move it into normal message
        # handler above?

    def _muc_presence(self, presence, status) -> None:
        """
        Group chat presence handler
        """

        # get chat and our nick in the chat

    def muc_online(self, presence) -> None:
        """
        Group chat online presence handler
        """

        self._muc_presence(presence, "online")

    def muc_offline(self, presence) -> None:
        """
        Group chat offline presence handler
        """

        self._muc_presence(presence, "offline")

    def enqueue_command(self, cmd: Callback, params: Tuple) -> None:
        """
        Enqueue a command in the command queue
        Tuple consists of:
            command and its parameters
        """

        self.lock.acquire()
        # just add message tuple to queue
        self.queue.append((cmd, params))
        self.lock.release()

    def handle_queue(self) -> None:
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

    def _send_message(self, message_tuple: Tuple) -> None:
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

    def _set_status(self, status: str) -> None:
        """
        Set the current status of the account
        """

        # TODO: do something when status changes, e.g., from offline to online?
        self.status = status

    def _get_status(self) -> None:
        """
        Get the current status of the account
        """

        self.account.receive_msg(Message.status(self.account, self.status))

    def _chat_list(self) -> None:
        """
        List active chats of account
        """

        rooms = self._get_rooms()
        for room in rooms.values():
            self.account.receive_msg(Message.chat_list(
                self.account, room.room_id, escape_name(room.display_name),
                self.user))

    def _chat_create(self, name: str) -> None:
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

    def _chat_join(self, chat: str) -> None:
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

    def _chat_part(self, chat: str) -> None:
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

    def _chat_users(self, chat: str) -> None:
        """
        Get list of users in chat on account
        """

        roster: Dict = {}
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

    def _chat_invite(self, chat: str, user_id: str) -> None:
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

    def update_buddies(self) -> None:
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

    def _get_rooms(self) -> Dict:
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
