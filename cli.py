"""

pan-os_cli v1.0 [20230421]

Script to repeat CLI commands on PAN-OS over SSH

by Terence LEE <telee.hk@gmail.com>

https://github.com/telee0/pan_scripts
https://pexpect.readthedocs.io/en/stable/index.html

"""

cf = {
    'hostname': '192.168.1.1',  # host IP
    'username': 'admin',       # sensitive and not exported
    'password': 'admin',     # sensitive and not exported
    'prompt': r'.*>\s+',          # regex so prefixed with an 'r'

    # total time == time_delay + time_intervals * (iterations - 1)

    'iterations': 5,             # number of iterations
    'time_delay': 1,             # initial delay in seconds
    'time_interval': 2,          # interval in seconds between iterations

    'cli': 'cli_1',              # currently not used
    'cli_timeout': 1,            # > 0 or the cli will not expect a prompt

    'job_dir':  'job-{}',        # job folder
    'cnf_file': 'cnf-{}.json',   # config dump
    'cli_file': 'cli-{}.log',    # CLI output
    'sta_file': 'sta-{}.json',   # stats
}

# cli = [c0, c1, c2], assigned as a list right after c0, c1 and c2 are defined here.
#
# c1 is designed to be repeated. We may specify a different c1 for different POC's e.g. cli = [c0, c_poc12345, c2]

# CLI commands, repeat count, repeat interval
#
c0 = [
    'show clock',
    'set cli pager off',
    'show system info',
]

# CLI tuples:
#
# (command_line,) or just command_line   # command_line for once (remember the trailing comma ',' when using a tuple)
# (command_line, repeat_count)           # command_line for repeat_time times
# (command_line, repeat_count, timeout)  # command_line for repeat_time times, custom timeout (0 => no_prompt)
#
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

# c2 is assumed to be the last command set after c1, but there can be c3, c4, ..
#
c2 = [
    'exit',
]

cli = [
    c0,
    (c1, cf['iterations']),  # c1 may be different for different POC's e.g. cli = [c0, c_poc12345, c2]
    c2
]

metrics = {
    'activeTCPSessions':   r'active TCP sessions:\s+(\d+)',
    'activeUDPSessions':   r'active UDP sessions:\s+(\d+)',
    'allocatedSessions':   r'allocated sessions:\s+(\d+)',
    'connectionRate':      r'connection establish rate:\s+(\d+) cps',
    'eth1_1BytesReceived': r'bytes received\s+(\d+)',
    'packetRate':          r'Packet rate:\s+(\d+)\/s',
    'vpnIPSecTunnels':     r'Total (\d+) tunnels found',
    'test': r'abcde(\d)',
    # 'test': r'(\wa\w+)\s',
}

if __name__ == '__main__':
    pass
