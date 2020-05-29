"""
matrix specific stuff
"""

import urllib.parse
import logging
import time

from typing import Callable, Dict, List, Tuple

# matrix imports
from matrix_client.client import MatrixClient as _MatrixClient  # type: ignore
from matrix_client.errors import MatrixRequestError             # type: ignore
from matrix_client.errors import MatrixHttpLibError             # type: ignore


class MatrixClient:
    """
    Matrix client class
    """

    def __init__(self, url: str, message_handler: Callable,
                 membership_handler: Callable) -> None:
        self.client = _MatrixClient(url)
        self.token = ""
        self.status = "offline"

        # separate data structure for managing room invites
        self.room_invites: Dict[str, Tuple[str, str, str, str, str]] = {}

        # add matrix client event handlers
        self.client.add_listener(self.listener)
        self.client.add_presence_listener(self.presence_listener)
        self.client.add_invite_listener(self.invite_listener)
        self.client.add_leave_listener(self.leave_listener)
        self.client.add_ephemeral_listener(self.ephemeral_listener)

        # handlers
        self.message_handler = message_handler
        self.membership_handler = membership_handler

    def listener(self, event):
        """
        Event listener
        """

        logging.debug("listener: %s", event)
        if event["type"] == "m.room.message":
            self.message(event)
        if event["type"] == "m.room.member":
            self._membership_event(event)

    def message(self, msg) -> None:
        """
        Message handler
        """

        # save timestamp and message in messages list and history
        tstamp = str(int(int(msg["origin_server_ts"])/1000))
        self.message_handler(tstamp, msg["sender"], msg["room_id"],
                             msg["content"]["body"])

    def _membership_event(self, event):
        """
        Handle membership event
        """

        # parse event
        sender = event["sender"]
        sender_name = self.get_display_name(sender)

        room_id = event["room_id"]
        room_name = room_id
        membership = event["content"]["membership"]
        tstamp = int(int(event["origin_server_ts"])/1000)

        # get room name
        rooms = self.client.get_rooms()
        room_name = rooms[room_id].display_name

        # get invited user if present
        invited_user = ""
        if membership == "invite":
            invited_user = event["content"]["displayname"]
        if membership == "join":
            invited_user = event["content"]["displayname"]

        self.membership_handler(membership, tstamp, sender, sender_name,
                                room_id, room_name, invited_user)

    @staticmethod
    def presence_listener(event):
        """
        Presence event listener
        """

        logging.debug("presence: %s", event)

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
                sender_name = self.get_display_name(sender)

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

    @staticmethod
    def leave_listener(room_id, event):
        """
        Leave event listener
        """

        logging.debug("leave: %s %s", room_id, event)

    @staticmethod
    def ephemeral_listener(event):
        """
        Ephemeral event listener
        """

        logging.debug("ephemeral: %s", event)

    def listener_exception(self, exception: Exception) -> None:
        """
        Handle listener exception
        """

        error = "Stopping listener because exception occured " \
                "in listener: {}".format(exception)
        logging.error(error)
        self.client.should_listen = False
        self.status = "offline"

    def connect(self, username: str, password: str, sync_token: str) -> str:
        """
        Connect to matrix server
        """

        # if there is an old listener, stop it
        if self.client:
            self.client.stop_listener_thread()

        try:
            # login and limit sync to only retrieve 0 events per room, so we do
            # not get old messages again. this changes the sync_filter. so, we
            # have to save the defaults and apply them after login to get
            # events again.
            sync_filter = self.client.sync_filter
            self.token = self.client.login(
                username=username, password=password, limit=0)
            self.client.sync_filter = sync_filter
            self.status = "online"

            # set sync token
            self.client.sync_token = sync_token

            # start listener thread in the matrix client
            self.client.start_listener_thread(
                exception_handler=self.listener_exception)

        except (MatrixRequestError, MatrixHttpLibError) as error:
            logging.error(error)
            self.status = "offline"

        return self.status  # remove return?

    def stop(self) -> None:
        """
        Stop client
        """

        self.client.stop_listener_thread()

    def sync_token(self) -> str:
        """
        Get sync token of client connection
        """

        return self.client.sync_token

    def get_rooms(self) -> Dict:
        """
        Get list of rooms
        """

        try:
            rooms = self.client.get_rooms()
        except MatrixRequestError as error:
            logging.error(error)
            rooms = {}
        except MatrixHttpLibError as error:
            self.status = "offline"
            logging.error(error)
            rooms = {}

        return rooms

    def get_invites(self) -> Dict:
        """
        Get room invites
        """

        # cleanup old invites
        rooms = self.get_rooms()
        for room in rooms.values():
            if room.room_id in self.room_invites:
                # seems like we are in the room now, remove invite
                del self.room_invites[room.room_id]

        return self.room_invites

    def get_display_name(self, user: str) -> str:
        """
        Get the display name of user
        """

        try:
            display_name = self.client.get_user(user).get_display_name()
        except MatrixRequestError as error:
            display_name = user
            logging.error(error)
        except MatrixHttpLibError as error:
            display_name = user
            self.status = "offline"
            logging.error(error)

        return display_name

    def send_message(self, dest_room: str, msg: str, html_msg: str) -> None:
        """
        Send msg to dest_room
        """

        rooms = self.get_rooms()
        for room in rooms.values():
            if dest_room in (room.display_name, room.room_id):
                try:
                    room.send_html(html_msg, body=msg, msgtype='m.text')
                except MatrixRequestError as error:
                    # TODO: return error to connected user?
                    logging.error(error)
                except MatrixHttpLibError as error:
                    self.status = "offline"
                    logging.error(error)
                return

    def create_room(self, room_name: str) -> str:
        """
        Create chat room that is identified by room_name
        """

        try:
            room = self.client.create_room()
            room.set_room_name(room_name)
        except MatrixRequestError as error:
            return "code: {} content: {}".format(error.code, error.content)
        except MatrixHttpLibError as error:
            self.status = "offline"
            logging.error(error)

        return ""

    def join_room(self, room_name: str) -> str:
        """
        Join chat room that is identified by room_name
        """

        try:
            room_name = unescape_name(room_name)
            self.client.join_room(room_name)
        except MatrixRequestError as error:
            # joining an existing room failed.
            # if chat is not a room id, try to create a new room
            if not room_name.startswith("!") or ":" not in room_name:
                return self.create_room(room_name)
            return "code: {} content: {}".format(error.code, error.content)
        except MatrixHttpLibError as error:
            self.status = "offline"
            logging.error(error)

        return ""

    def part_room(self, room_name: str) -> str:
        """
        Leave chat room identified by room_name
        """

        # part an already joined room
        rooms = self.get_rooms()
        for room in rooms.values():
            if unescape_name(room_name) == room.display_name or \
               unescape_name(room_name) == room.room_id:
                try:
                    room.leave()
                except MatrixRequestError as error:
                    return "code: {} content: {}".format(error.code,
                                                         error.content)
                except MatrixHttpLibError as error:
                    self.status = "offline"
                    logging.error(error)
                return ""
        # part a room we are invited to
        # TODO: add locking
        for invite in self.room_invites.values():
            room_id, room_name, _sender, _sender_name, _tstamp = invite
            if unescape_name(room_name) == room_name or \
               unescape_name(room_name) == room_id:
                try:
                    self.client.api.leave_room(room_id)
                except MatrixRequestError as error:
                    return "code: {} content: {}".format(error.code,
                                                         error.content)
                except MatrixHttpLibError as error:
                    self.status = "offline"
                    logging.error(error)
                # remove room from invites
                self.room_invites = {k: v for k, v in self.room_invites.items()
                                     if k != room_id}
                return ""

        return ""

    def list_room_users(self, room_name: str) -> List[Tuple[str, str, str]]:
        """
        List users in room identified by room_name
        """

        roster: Dict = {}
        rooms = self.get_rooms()
        for room_id, room in rooms.items():
            if unescape_name(room_name) == room.display_name or \
               unescape_name(room_name) == room_id:
                try:
                    roster = self.client.api.get_room_members(room_id)
                except MatrixRequestError as error:
                    logging.error(error)
                    roster = {}
                except MatrixHttpLibError as error:
                    self.status = "offline"
                    logging.error(error)
                    roster = {}

        user_list = []
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
                    user_list.append((user_id, name, status))

        return user_list

    def invite_room(self, room_name: str, user_id: str) -> str:
        """
        Invite user with user_id to room with room_name
        """

        rooms = self.get_rooms()
        for room in rooms.values():
            if unescape_name(room_name) == room.display_name or \
               unescape_name(room_name) == room.room_id:
                try:
                    room.invite_user(user_id)
                except MatrixRequestError as error:
                    return "code: {} content: {}".format(error.code,
                                                         error.content)
                except MatrixHttpLibError as error:
                    self.status = "offline"
                    logging.error(error)

        return ""


def escape_name(name: str) -> str:
    """
    Escape "invalid" charecters in name, e.g., space.
    """

    # escape spaces etc.
    return urllib.parse.quote(name)


def unescape_name(name: str) -> str:
    """
    Convert name back to unescaped version.
    """

    # unescape spaces etc.
    return urllib.parse.unquote(name)


def parse_account_user(acc_user: str) -> Tuple[str, str, str]:
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
