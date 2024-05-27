"""

pan-os_cli v1.1 [20240521]

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
from datetime import datetime, timedelta
from os import makedirs
from os.path import exists

import paramiko
from paramiko_expect import SSHClientInteraction

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from scipy.interpolate import make_interp_spline

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
        cf[h] = args.target  # overriden with the command line parameter 'target'

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

    # initialize dp
    #
    dp['timestamps'] = []
    dp['output'] = {}

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

                match = re.search(dp['command'], command)
                if match is not None:
                    dp['timestamps'].append(datetime.now())

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


def analyze_dp(data):
    global step

    step += 1

    if verbose:
        print(f"-- analyze DP data..")

    output = {}
    dp_name = dp['dp_name_default']
    t, timestamp, s, seconds = 0, None, None, None

    for text in data:
        found = False
        lines = text.split('\n')
        i, n = 0, len(lines)
        while i < n:
            line = lines[i]
            i += 1
            match = re.search(dp['dp_name'], line)
            if match is not None:
                dp_name = match.group(1)
                continue
            match = re.search(dp['cpu_load'], line)
            if match is not None:
                found = True
                seconds = min(cf['time_interval'], int(match.group(1)))  # seconds = number of data rows
            else:
                continue
            if dp_name not in output:
                output[dp_name] = {}
                for aggregate in ('min', 'max', 'ave'):
                    output[dp_name][aggregate] = []
            cores = []
            while i < n:
                line = lines[i]
                i += 1
                if line.startswith(dp['core']):  # core   0   1   2   3
                    cores = line.split()
                    for core in cores[1:]:
                        if core not in output[dp_name]:
                            output[dp_name][core] = []
                    timestamp = dp['timestamps'][t]
                    s = seconds
                else:
                    values = line.split()
                    if len(values) > 0:
                        if s > 0:
                            is_first_row = (s == seconds)
                            timestamp -= timedelta(seconds=1)
                            s -= 1
                            if is_first_row and dp['skip_first_row']:  # skip the first data row (usually incomplete)
                                pass
                            else:
                                for j, core in enumerate(cores[1:]):
                                    value = values[j]
                                    if value.isdigit():  # '*' ignored
                                        value = int(value)
                                        output[dp_name][core].append((timestamp, value))
                                        if '_' not in output[dp_name]:
                                            output[dp_name]['_'] = {}
                                        if timestamp not in output[dp_name]['_']:
                                            output[dp_name]['_'][timestamp] = []
                                        output[dp_name]['_'][timestamp].append(value)
                    else:
                        break
        if found:
            t += 1

    for dp_name in output.keys():
        for timestamp in output[dp_name]['_'].keys():
            values = output[dp_name]['_'][timestamp]
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
            for aggregate in ('min', 'max', 'ave'):
                output[dp_name][aggregate].append((timestamp, s[aggregate]))

    dp['output'] = output

    return output


def plot_dp(data):
    global step

    step += 1

    if verbose:
        print(f"-- plotting DP..")

    df_list = []

    for dp_name in data.keys():
        data_dp = data[dp_name]

        core_max = 0
        for core in data_dp.keys():
            if core.isdigit():
                core_max = max(core_max, int(core))  # safe to determine max core id

        core_groups = []
        for i in range(0, core_max, dp['cores_per_group']):
            core_group = []
            for j in range(i, i + dp['cores_per_group']):
                core = str(j)
                if core in data_dp and len(data_dp[core]) > 0:
                    core_group.append(core)
            core_groups.append(core_group)
        core_groups.insert(0, [a for a in dp['aggregate'] if a in data_dp])
        # core_groups.insert(0, [core for core_group in core_groups for core in core_group])  # group with all cores

        if verbose:
            print(f"-- DP {dp_name}: core_groups:", core_groups)

        for i, core_group in enumerate(core_groups):
            if len(core_group) == 0:
                continue

            plt.figure(figsize=(12, 8))

            for core in core_group:
                data_core = data_dp[core]
                df = pd.DataFrame(data_core, columns=['timestamp', 'load'])
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df = df.sort_values(by='timestamp')

                df['dp'] = dp_name
                df['core'] = core
                df_list.append(df)

                x = (df['timestamp'] - df['timestamp'].min()) / np.timedelta64(1, 's')
                y = df['load']

                x_smooth = np.linspace(x.min(), x.max(), 300)
                spline = make_interp_spline(x, y, k=3)
                y_smooth = spline(x_smooth)

                x_smooth_datetime = pd.to_datetime(df['timestamp'].min()) + pd.to_timedelta(x_smooth, unit='s')

                if i > 0:
                    plt.plot(x_smooth_datetime, y_smooth, label=f'Core {core}')
                else:
                    plt.plot(x_smooth_datetime, y_smooth, '-', label=f'Core all {core}')
                    # plt.plot(x_smooth_datetime, y_smooth, 'o-', label=f'Core all {core}')
                    # plt.step(x_smooth_datetime, y_smooth, where='mid', label=f'Core all {core}')
                    plt.fill_between(x_smooth_datetime, y_smooth, step='mid', alpha=0.4)  # , color='skyblue')

            if i == 0:
                plt.title(f"DP Utilization ({dp_name})")
            else:
                plt.title(f"DP Utilization ({dp_name}) - Group {i}")
            # plt.xlabel('Time')
            plt.ylabel('CPU load (%)')
            plt.xticks(rotation=45)
            plt.yticks(np.arange(0, 101, 20))
            plt.ylim(0, 100)
            # plt.grid(True)
            plt.grid(which='both', linestyle='--', linewidth=0.4, alpha=0.4)
            plt.legend()
            plt.tight_layout()
            plt.savefig(dp['plot_file'].format(dp_name, i))
            plt.close()

    pd.concat(df_list).to_csv(dp['csv_file'], index=False)


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
    from conf import cf, cli, metrics, dp

    init()
    data_ = collect_data()
    stats_ = analyze(data_)
    write_files(data_, stats_)

    data_dp_ = analyze_dp(data_)
    plot_dp(data_dp_)

    step += 1

    if verbose:
        log("[{0:02.2f}] job_dir = {1}".format(step, cf['job_dir']), flush=True)
