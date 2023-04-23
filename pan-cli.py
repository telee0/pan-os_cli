"""

pan-os_cli v1.0 [20230421]

Script to repeat CLI commands on PAN-OS over SSH

by Terence LEE <telee.hk@gmail.com>

https://github.com/telee0/pan-os_cli
https://pexpect.readthedocs.io/en/stable/index.html

"""

import argparse
import importlib.util
import json
import os
import re
import sys
import time
from datetime import datetime
from os import makedirs
from os.path import exists

import paramiko
from paramiko_expect import SSHClientInteraction

# from cli import cf, cli, metrics

verbose, debug = False, False
step = 0
log_buf = []


def init():
    global step
    global args
    global verbose, debug

    step = 0

    verbose = (cf['verbose'] and args.verbose) if 'verbose' in cf else verbose
    debug = cf['debug'] if 'debug' in cf else debug

    print(f"-- initialize the environment..")

    h, u, p, e = 'hostname', 'username', 'password', 'passenv'

    if args.target is not None:
        cf[h] = args.target  # overriden by the command line parameter 'target'

    if u not in cf or len(cf[u]) <= 0:
        cf[u] = 'admin'  # default 'admin'

    if p not in cf or len(cf[p]) <= 0:
        cf[p] = os.getenv(cf[e]) if e in cf else None  # password from the env variable

    if cf[p] is None or len(cf[p]) <= 0:
        print("init: access not specified or empty")
        print("init: check {0} for details ('{1}')".format(args.conf, e))
        exit(1)

    t = datetime.now().strftime('%Y%m%d%H%M')
    ddhhmm = t[6:12]

    for f in ['job_dir', 'cnf_file', 'cli_file', 'sta_file', 'log_file']:
        if f not in cf:
            cf[f] = f
        cf[f] = cf[f].format(ddhhmm)

    # prepare the directory structure for job files
    #
    job_dir = cf['job_dir']  # .format(ddhhmm)
    makedirs(job_dir, exist_ok=True)
    os.chdir(job_dir)

    log("[{0:02.2f}] verbose = {1}, debug = {2}".format(step, verbose, debug))


def log(message, flush=False):
    global log_buf

    t = datetime.now().strftime('%H:%M:%S')
    message = f"[{t}] " + message
    log_buf.append(message)
    # print("message:", message)
    if len(log_buf) > cf['log_buf_size'] or flush:
        with open(cf['log_file'], 'a') as f:
            f.write("\n".join(log_buf))
        log_buf.clear()
        if len(log_buf) > 0:
            print(f"log: entries not written to {cf['log_file']}")
            exit(1)


# check here for more use cases
#
# https://github.com/fgimian/paramiko-expect/blob/master/examples/paramiko_expect-demo.py

def send_cli(interact, cli_idx):
    global step

    output = []

    cli_list = cli[cli_idx]
    cli_tuple = (cli_list, 1) if type(cli_list) is list else cli_list  # convert list to tuple in case
    cli_, iterations = cli_tuple

    prompt = cf['prompt']
    time_interval = cf['time_interval']

    for i in range(iterations):
        for j, c_ in enumerate(cli_):
            if verbose:
                log("[{0}.{1:02d}.{2:02d}] c = {3}".format(step, i, j, c_))

            c = (c_,) if isinstance(c_, str) else c_  # convert it back to a tuple in case of a string

            command, count, timeout = c[0], 1, cf['cli_timeout']

            c_len = len(c)
            if c_len >= 2:
                count = max(count, int(c[1]))  # make sure at least once
                if c_len >= 3:
                    timeout = c[2]

            for _ in range(count):  # repeat_count of each command line
                if timeout > 0:
                    interact.expect([prompt], timeout=timeout)
                interact.send(command)
                output.append(interact.current_output_clean)

        if i < iterations - 1:
            print(f"-- sleep for {time_interval} seconds..")
            time.sleep(time_interval)

    return output


def collect_data():
    global step

    step += 1

    output = []

    client = None

    # SSH to login
    #
    try:
        if verbose:
            print(f"-- connect to {cf['hostname']} as {cf['username']}..")
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=cf['hostname'], username=cf['username'], password=cf['password'])
    except Exception as e:
        print("collect_data:", e)
        client.close()
        exit(1)

    time_delay = cf['time_delay']

    try:
        with SSHClientInteraction(client, timeout=10, display=False) as interact:
            print(f"-- sleep for {time_delay} seconds..")
            time.sleep(max(3, time_delay))  # wait for at least 3 seconds
            interact.send("")
            for i in range(len(cli)):
                step += 1
                print(f"-- submit CLI set #{i}..")
                output += send_cli(interact, i)
        if debug:
            print("\n".join(output))
    except Exception as e:
        print(e)
    finally:
        client.close()

    return output


def write_files(data, stats=None):
    global step

    step += 1

    if verbose:
        print(f"-- generate output at {cf['job_dir']}/..")

    file = cf['cnf_file']  # .format(ddhhmm)
    with open(file, 'a') as f:
        username, cf['username'] = cf['username'], ''
        password, cf['password'] = cf['password'], ''
        f.write(json.dumps({'cf': cf, 'cli': cli, 'metrics': metrics}, indent=4))
        # json.dump({'cf': cf, 'cli': cli, 'metrics': metrics}, f)
        cf['username'], cf['password'] = username, password
        if verbose:
            log("[{0:02.2f}] file = {1}".format(step, file))

    file = cf['cli_file']  # .format(ddhhmm)
    with open(file, 'a') as f:
        f.write("\n".join(data))
        if verbose:
            log("[{0:02.2f}] file = {1}".format(step, file))

    if stats is not None:
        file = cf['sta_file']  # .format(ddhhmm)
        with open(file, 'a') as f:
            f.write(json.dumps(stats, indent=4))
            if verbose:
                log("[{0:02.2f}] file = {1}".format(step, file))


def analyze(data):
    global step

    step += 1

    if verbose:
        print(f"-- analyze data..")

    output = {}   # stats
    results = {}  # results extracted from data

    for key in metrics.keys():
        pattern = metrics[key]
        results[key] = []
        for i, text in enumerate(data):
            matches = re.findall(pattern, text)
            if matches:
                for m in matches:
                    results[key].append(m)
                    break  # skip the rest of the matches
                if debug:
                    print("matches:", matches)
            if debug:
                print(f"{i} - text =", text)
                print("-" * 80)
        if len(results[key]) == 0:  # delete empty matches from the results
            del results[key]

    for i, key in enumerate(results.keys()):
        values = results[key]
        v0 = float(values[0])
        s = {
            'min': v0, 'max': v0,
            'ave': 0,
            'cnt': len(values)
        }
        for value in values:
            v = float(value)
            s['min'] = min(s['min'], v)
            s['max'] = max(s['max'], v)
            s['ave'] += v
        s['ave'] /= s['cnt']
        if verbose:
            j = i * 2
            log("[{0}.{1:02d}] metrics = {2}: {3}".format(step, j, key, values))
            log("[{0}.{1:02d}] stats   = stats: [{2}]".format(step, j + 1, s))
        output[key] = s

    return output


def read_conf(cf_path):
    if not exists(cf_path):
        print("{0}: file not found".format(cf_path))
        exit(1)
    name = "conf"
    spec = importlib.util.spec_from_file_location(name, cf_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog='pan-cli.py', description='Script to repeat PAN-OS CLI over SSH.')
    parser.add_argument('-c', '--conf', nargs='?', type=str, default="conf/cli.py", help="config file")
    parser.add_argument('-v', '--verbose', action='store_true', help="verbose mode")
    parser.add_argument('target', nargs='?', help="IP of target device")
    parser.print_help()
    print()

    args = parser.parse_args()

    if not debug:
        print(args, "\n")

    read_conf(args.conf)
    from conf import cf, cli, metrics

    init()
    data_ = collect_data()
    stats_ = analyze(data_)
    write_files(data_, stats_)

    step += 1

    if verbose:
        log("[{0:02.2f}] job_dir = {1}".format(step, cf['job_dir']), flush=True)
