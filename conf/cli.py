"""

pan-os_cli v2.1 [20260515]
pan-os_cli v2.0 [20250420]

Script to repeat CLI commands on PAN-OS over SSH

by Terence LEE <telee.hk@gmail.com>

https://github.com/telee0/pan-os_cli
https://pexpect.readthedocs.io/en/stable/index.html

"""

cf = {
    'hostname': '192.168.1.1',          # host name or IP of the target device
    'username': 'admin',                # sensitive and not exported, default admin
    'password': '',                     # sensitive and not exported, either here or through the env variable cf['passenv']
    'passenv': 'PAPASS',                # name of the environment variable for the password
    'prompt': r'.*>\s+',                # regex for the prompt

    # max duration (? d ? h ? m ? s) <= time_delay + time_interval * (iterations - 1)

    'duration': '0h2m0s',              # max duration in (? d ? h ? m ? s)
    'iterations': 999,                  # max number of iterations
    'time_delay': 10,                   # initial delay in seconds
    'time_interval': 10,                # interval in seconds between iterations

    'cli_timeout': 5,                   # timeout > 0 or the prompt will not be expected for the next command
    'tty_size': (200, 40),              # terminal size for screenful CLI output capture
    'log_buf_size': 99,                 # log buffer size in message count

    'job_dir':  'job-{}-{}',            # job folder
    'log_file': 'job-{}.log',           # job log
    'cnf_file': 'cf-{}.json',           # config dump
    'cli_file': 'cli-{}.log',           # CLI output
    'sta_file': 'sta-{}.json',          # stats
    'ctx_file': 'ctx-{}.json',

    'plot_file': 'p{0}-{1}.png',        # stats plot file names
    'plot_file_merged': 'p-{0}.png',    # state merged plot file names
    'plot_grid_size': (3, 3),           # (rows, columns) for merged summary plots

    'version': '2.1',

    'verbose': True,
    'debug': False,
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
    'show chassis power',
]

# CLI tuples:
#
# (command_line,) or just command_line   # command_line for once (remember the trailing comma ',' for tuple)
# (command_line, repeat_count)           # command_line for repeat_count times
# (command_line, repeat_count, timeout)  # command_line for repeat_count times, custom timeout (0 => no_prompt)
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
    # 'debug dataplane show ssl-decrypt ssl-stats',
    # ('show session all filter count yes ssl-decrypt yes', 1, 10),  # to trace decrypted sessions
    # ('show session all filter count yes ssl-decrypt no', 1, 10),   #
    # 'show counter global | match proxy_process',                   # target global counters
    # 'show counter global | match session_installed',               #
    # 'show counter global filter delta yes severity warn',
    'show interface ethernet1/1 | match "received"',
    # 'show interface ethernet1/1 | match "bytes received"',
    # 'show interface ethernet1/43 | match "bytes received"',
    'show session distribution policy',                              # chassis models
    # 'show interface all | match ^node',                             # pa-7500 cluster
    # 'show cluster nodes',                                           # pa-7500 cluster
    # 'show vpn ipsec-sa summary | match "tunnels found"',
    # 'show global-protect-gateway statistics',
    # 'show lockless-qos enable',
    # 'show lockless-qos if-core-mapping',
    ('show clock',),
]

# c2 is assumed to be the last command set after c1, but there can be c3, c4, ..
#
c2 = [
    # 'show clock',
    'exit',
]

cli = [
    c0,
    (c1, cf['iterations']),  # c1 may be different for POC's e.g. cli = [c0, c_poc12345, c2]
    c2
]

# dictionary of search patterns for runtime metrics such as allocated sessions, packet rate, etc.
# These search patterns are regex for locating target numbers from output files
#
metrics = {
    'activeTCPSessions':    r'active TCP sessions:\s+(\d+)',
    'activeUDPSessions':    r'active UDP sessions:\s+(\d+)',
    'allocatedSessions':    r'allocated sessions:\s+(\d+)',
    'connectionRate':       r'connection establish rate:\s+(\d+) cps',
    'eth1BytesReceived':    r'bytes received\s+(\d+)',
    'eth1PacketsReceived':  r'packets received\s+(\d+)',
    'flow_ctrl':            r'flow_ctrl\s+:\s+(\d+)%',
    'packetRate':           r'Packet rate:\s+(\d+)\/s',
    'sessionTableUtil':     r'Session table utilization:\s+(\d+)%',
    'systemResources': (    # %Cpu(s): 19.1 us,  2.7 sy,  0.0 ni, 78.2 id,  0.0 wa,  0.0 hi,  0.0 si,  0.0 st
        r'%Cpu\(s\):\s*'
        r'([\d.]+)\s+us,\s*'
        r'([\d.]+)\s+sy,\s*'
        r'([\d.]+)\s+ni,\s*'
        r'([\d.]+)\s+id,\s*'
        r'([\d.]+)\s+wa,\s*'
        r'([\d.]+)\s+hi,\s*'
        r'([\d.]+)\s+si,\s*'
        r'([\d.]+)\s+st',
        ['us', 'sy', 'ni', 'id', 'wa', 'hi', 'si', 'st'],
    ),
    'throughputKbps':       r'Throughput:\s+(\d+) kbps',
    # 'vpnIPSecTunnels':      r'Total (\d+) tunnels found',
}

metrics2 = {  # derived metrics
    'eth1PacketSizesAverage':   "eth1BytesReceived / eth1PacketsReceived",
    'systemResourcesBusy':      "systemResources[:, 0] + systemResources[:, 1]",
    'systemResourcesUsSy':      "100 - systemResources[:, 3]",
}

dp = {
    'command':              r'show\s+running\s+resource-monitor',
    'dp_name':              r'^DP\s+(s\d+dp\d+):',
    'cpu_load':             r'CPU load \(%\) during last (\d+) seconds:',
    'core':                 'core',
    'dp_name_default':      'dp0',  # do not use dp use dp0
    'cores_per_group':      8,
    'aggregate':            ('ave', 'max'),  # , 'min'),  # , 'sum', 'cnt'),
    'csv_file':             "dp.csv",
    'json_file':            "dp.json",
    'plot_file':            "{0}-{1}.png",
    'plot_file_merged':     "dp-{0}.png",
    'plot_grid_size':       cf['plot_grid_size'],  # (3, 3),  # (rows, columns) for merged summary plots
    'skip_first_row':       True,  # address the issue where the most recent data row is incomplete (all low values)
    'skip_dp_names':        ["s1dp0", "s2dp0"],  # currently not used
}

if __name__ == '__main__':
    pass
