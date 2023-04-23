# pan-os_cli
Scripts to repeat CLI commands on PAN-OS over SSH

pan-cli.py will submit a list of CLI (blocks), each repeated for a different number of times:

In the following example, c0 and c1 will not be repeated (once only) and c1 will be repeated 5 times.

`cli = [c0, (c1, 5), c2]`

Each of these CLI blocks has a similar structure. For example, c1 contains the list of command lines,
each repeated for a different number of times:

For example, `show session all` will list sessions in pages, so there needs a space ` ` for the next page or `q` to stop.

The last tuple member in ('q', 1, 0) is 0. Any non-positive value will cause it not wait for the prompt.

```
c1 = [
    'show session info',
    'set cli pager on',
    'show session all',
    (' ', 2, 0),  # space for the next page, totally 3 pages
    ('q', 1, 0),  # q to stop
    'set cli pager off',
    'show running resource-monitor second last 30',
    'show system resources | match ": "',
    'show interface ethernet1/1 | match "bytes received"',
    'show vpn ipsec-sa summary | match "tunnels found"',
    'show global-protect-gateway statistics',
    'debug dataplane show ssl-decrypt ssl-stats',
    ('show clock',),
]
```

If you use an IDE (e.g. PyCharm) for the scripts, configure the command line and environment variables accordingly.

Here is an example.

- Script path: pan-os_cli\pan-cli.py
- Parameters: -c conf/cli.py -v 192.168.1.254
- Environment variables: PAPASS=pass123

If you use shell like bash, just run the main script per the following usage.

```
usage: pan-cli.py [-h] [-c [CONF]] [-v] [target]

Script to repeat PAN-OS CLI over SSH.

positional arguments:
  target                IP of the target device

options:
  -h, --help            show this help message and exit
  -c [CONF], --conf [CONF]
                        config file
  -v, --verbose         verbose mode

```

Finally, these parameters can be overriden in some ways.

- cf['hostname']: overriden by the target on command line
- cf['username']: if empty, 'admin' is assumed
- cf['password']: if empty, specified through the environment variable from cf['passenv']

