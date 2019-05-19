# nuqql-matrixd

nuqql-matrixd is a network daemon that implements the nuqql interface and uses
the [Matrix Python SDK](https://github.com/matrix-org/matrix-python-sdk) to
connect to Matrix chat networks. It can be used as a backend for
[nuqql](https://github.com/hwipl/nuqql) or as a standalone chat client daemon.

nuqql-matrixd is a fork of [nuqql-based](https://github.com/hwipl/nuqql-based)
that adds the Matrix Python SDK for Matrix support. Thus, the [Matrix Python
SDK](https://github.com/matrix-org/matrix-python-sdk) is a requirement to run
nuqql-matrixd.

You can run nuqql-matrixd by executing *matrixd.py*, e.g., with
`./matrixd.py`.

By default, it listens on TCP port 32000 on your local host. So, you can
connect with telnet to it, e.g., with `telnet localhost 32000`.

In the telnet session you can:
* add Matrix accounts with: `account add matrix <username> <password>`.
* retrieve the list of accounts and their numbers/IDs with `account list`.
* retrieve your buddy/room list with `account <id> buddies` or `account <id>
  chat list`
* send a message to a room with `account <id> chat send <room> <message>`


## Changes

* devel:
  * ...
