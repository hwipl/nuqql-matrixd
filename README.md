# nuqql-matrixd

nuqql-matrixd is a network daemon that implements the nuqql interface and uses
the [Matrix Python SDK](https://github.com/matrix-org/matrix-python-sdk) to
connect to Matrix chat networks. It can be used as a backend for
[nuqql](https://github.com/hwipl/nuqql) or as a standalone chat client daemon.

nuqql-matrixd's dependencies are:
* [nuqql-based](https://github.com/hwipl/nuqql-based)
* [Matrix Python SDK](https://github.com/matrix-org/matrix-python-sdk)
* [daemon](https://pypi.org/project/python-daemon/) (optional)


## Quick Start

You can install nuqql-matrixd and its dependencies, for example, with pip for
your user only with the following command:

```console
$ pip install --user nuqql-matrixd
```

After the installation, you can run nuqql-matrixd by running the
`nuqql-matrixd` command:

```console
$ nuqql-matrixd
```

By default, it listens on TCP port 32000 on your local host. So, you can
connect with, e.g., telnet to it with the following command:

```console
$ telnet localhost 32000
```

In the telnet session you can:
* add Matrix accounts with: `account add matrix <account> <password>`.
  * Note: the format of `<account>` is `<username>@<homeserver>`, e.g.,
    `dummy_user@matrix.org`.
* retrieve the list of accounts and their numbers/IDs with `account list`.
* retrieve your buddy/room list with `account <id> buddies` or `account <id>
  chat list`
* send a message to a room with `account <id> chat send <room> <message>`


## Usage

See `nuqql-matrixd --help` for a list of command line arguments:

```
usage: nuqql-matrixd [-h] [--version] [--af {inet,unix}] [--address ADDRESS]
[--port PORT] [--sockfile SOCKFILE] [--dir DIR] [-d] [--loglevel
{debug,info,warn,error}] [--disable-history]

Run nuqql backend.

optional arguments:
  -h, --help            show this help message and exit
  --version             show program's version number and exit
  --af {inet,unix}      socket address family: "inet" for AF_INET, "unix" for
                        AF_UNIX
  --address ADDRESS     AF_INET listen address
  --port PORT           AF_INET listen port
  --sockfile SOCKFILE   AF_UNIX socket file in DIR
  --dir DIR             working directory
  -d, --daemonize       daemonize process
  --loglevel {debug,info,warn,error}
                        Logging level
  --disable-history     disable message history
```


## Changes

* v0.4.0:
  * Update nuqql-based to v0.2.0
* v0.3:
  * Use nuqql-based as dependency and adapt to nuqql-based changes
  * Add setup.py for installation and package distribution
  * Add python type annotations
  * Restructure code
  * Cleanups, fixes, and improvements
* v0.2:
  * Allow specification of the homeserver url in the account user when adding
    an account. Thus, the following account users are possible:
    * `<user>@<domain>` (defaults to https)
    * `<user>@http://<domain>[:<port>]`
    * `<user>@https://<domain>[:<port>]`
  * Save sync token for each account in a file. So, only messages newer than
    the last sync are retrieved after a restart of the backend.
  * Add new commands:
    * `bye`: disconnect from the backend.
    * `quit`: quit the backend.
    * `help`: show list of commands and their description.
  * Add and use "chat msg" message format for group chat messages
  * Store accounts in .ini file `accounts.ini` in the backend's working
    directory. Note: existing accounts have to be re-added to the backend to
    be usable with the .ini file.
  * Add configuration file support: in addition to the command line arguments,
    configuration parameters can now be set in the .ini file `config.ini` in
    the backend's working directory.
  * Add `loglevel` configuration parameter to command line arguments and
    configuration file for setting the logging level to `debug`, `info`,
    `warn`, or `error`. Default: `warn`.
  * Make daemon python module optional
  * Fixes and improvements
* v0.1:
  * First/initial release.
