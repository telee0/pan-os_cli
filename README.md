# pan-os_cli v1.0
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

If you use an IDE for the scripts, configure the command line and environment variables accordingly.

Here is an example for PyCharm.

- Script path: pan-os_cli\pan-cli.py
- Parameters: -c conf/cli.py -v 192.168.1.254
- Environment variables: PAPASS=pass123

If you use shell like bash, just run the main script per the following usage.

```
[terence@centos-1 pan-os_cli]$ python3 pan-cli.py -c conf/cli-86.py -v 192.168.1.86
usage: pan-cli.py [-h] [-c [CONF]] [-v] [target]

Script to repeat PAN-OS CLI over SSH.

positional arguments:
  target                IP of target device

optional arguments:
  -h, --help            show this help message and exit
  -c [CONF], --conf [CONF]
                        config file
  -v, --verbose         verbose mode

Namespace(conf='conf/cli-86.py', target='192.168.1.86', verbose=True) 

-- initialize the environment..
-- connect to 192.168.1.86 as admin..
-- sleep for 30 seconds..
-- submit CLI set #0..
-- submit CLI set #1..
-- sleep for 20 seconds..
-- sleep for 20 seconds..
-- sleep for 20 seconds..
-- sleep for 20 seconds..
-- sleep for 20 seconds..
-- submit CLI set #2..
-- analyze data..
-- generate output at job-241054/..
[terence@centos-1 pan-os_cli]$ cd job-241054/
[terence@centos-1 job-241054]$ ls -la 
total 120
drwxrwxr-x 2 terence terence     96 Apr 24 10:57 .
drwxrwxr-x 6 terence terence    117 Apr 24 10:54 ..
-rw-rw-r-- 1 terence terence 103360 Apr 24 10:57 cli-241054.log
-rw-rw-r-- 1 terence terence   2083 Apr 24 10:57 cnf-241054.json
-rw-rw-r-- 1 terence terence   5888 Apr 24 10:57 job-241054.log
-rw-rw-r-- 1 terence terence    855 Apr 24 10:57 sta-241054.json
[terence@centos-1 job-241054]$
```

Finally, these parameters can be overriden in some ways.

- cf['hostname']: overriden by "target" on command line
- cf['username']: if empty, "admin" is assumed
- cf['password']: if empty, specified through the environment variable from cf['passenv'] (initially PAPASS)
- cf['verbose']: overriden by "-v" on command line

