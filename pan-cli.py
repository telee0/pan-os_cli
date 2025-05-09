"""

pan-os_cli v2.0 [20250420]

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
# from matplotlib import ticker
from paramiko_expect import SSHClientInteraction

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
import numpy as np
from scipy.interpolate import make_interp_spline, PchipInterpolator

verbose, debug = True, False

sess_ = None

cf, cli, metrics, dp = {}, [], {}, {}

sess = {
    'log_buf': [],
    'step': 0,
}


def duration_to_seconds(duration_str):
    pattern = re.compile(r'\s*(?:(\d+)\s*[dD]\s*)?(?:(\d+)\s*[hH]\s*)?(?:(\d+)\s*[mM]\s*)?(?:(\d+)\s*[sS]\s*)?')

    match = pattern.match(duration_str)

    if not match:
        return 30  # raise ValueError("Invalid duration format")

    days = int(match.group(1)) if match.group(1) else 0
    hours = int(match.group(2)) if match.group(2) else 0
    minutes = int(match.group(3)) if match.group(3) else 0
    seconds = int(match.group(4)) if match.group(4) else 0

    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def init():
    global cf
    global sess, args
    global verbose, debug

    sess['step'] = 0

    verbose = args.verbose or cf['verbose'] if 'verbose' in cf else verbose
    debug = cf['debug'] if 'debug' in cf else debug

    log(f"-- [{sess['step']}] initializing the environment..", echo=True)

    h, u, p, e = 'hostname', 'username', 'password', 'passenv'
    x = (h, u, p)
    y = (None, 'admin', None)  # default
    z = (args.host, args.user, os.getenv(cf[e]))  # specified

    for i, attr in enumerate(x):
        sess[attr] = z[i] or cf[attr] or y[i]
        value = sess[attr]
        if verbose:
            print(f"\tinit: value = {value}")
        if not value:
            print("init: access undefined or empty")
            print(f"init: check {args.conf} for details ('{attr}')")
            exit(1)

    # convert duration into seconds
    if 'duration' in cf and len(cf['duration']) > 0:
        sess['duration'] = duration_to_seconds(cf['duration'])
        log(f"\tinit: (max) duration {cf['duration']} = {sess['duration']}s", echo=verbose)

    log(f"\tinit: (max) iterations {cf['iterations']}", echo=verbose)

    ddhhmm = datetime.now().strftime('%d%H%M')

    for f in ('job_dir', 'cnf_file', 'cli_file', 'sta_file', 'log_file', 'sess_file'):
        sess[f] = cf[f].format(ddhhmm) if f in cf else f"{f}-{ddhhmm}"

    # prepare the directory structure for job files
    #
    job_dir = sess['job_dir']
    makedirs(job_dir, exist_ok=True)
    os.chdir(job_dir)

    # initialize the session (context)
    #
    sess['timestamps'] = []

    log(f"\tverbose = {verbose}, debug = {debug}", echo=verbose)


def log(message, echo=False, flush=False):
    global sess

    t = datetime.now().strftime('%H:%M:%S')
    message = f"[{t}] " + message
    if echo:
        print(message)
    sess['log_buf'].append(message)
    if len(sess['log_buf']) > cf['log_buf_size'] or flush:
        with open(sess['log_file'], 'a') as f:
            sess['log_buf'].append("")
            f.write("\n".join(sess['log_buf']))
        sess['log_buf'].clear()
        if len(sess['log_buf']) > 0:
            print(f"log: entries not written to {cf['log_file']}")
            exit(1)


# check here for more use cases
#
# https://github.com/fgimian/paramiko-expect/blob/master/examples/paramiko_expect-demo.py

def send_cli(interact, cli_idx):
    global sess

    output = []

    cli_list = cli[cli_idx]
    cli_tuple = (cli_list, 1) if type(cli_list) is list else cli_list  # wrap the CLI list in a tuple, repeat it once
    cli_, iterations = cli_tuple

    prompt = cf['prompt']
    time_interval = cf['time_interval']

    log(f"\tsend_cli: {len(cli_)} entries from set #{cli_idx} for {iterations} (max) iterations..", echo=verbose)

    for i in range(iterations):
        t0 = datetime.now()
        for j, c_ in enumerate(cli_):
            log(f"[{sess['step']}_{i}/{iterations}_{j}] c = {c_}")

            c = (c_,) if isinstance(c_, str) else c_  # wrap the CLI command in a tuple

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
                    sess['timestamps'].append(datetime.now())

                output.append(interact.current_output_clean)

        log(f"-- [{sess['step']}_{i+1}/{iterations}] CLI set executed in {datetime.now() - t0}", echo=verbose)

        # stop at command set level if time elapsed has exceeded sess['duration_seconds']
        #
        t = (datetime.now() - sess['start_time']).total_seconds()
        if t >= sess['duration']:
            log(f"\tt = {t} s", echo=debug)
            break

        if i < iterations - 1:
            log(f"\tsend_cli: sleep for {time_interval} seconds..", echo=verbose)
            time.sleep(time_interval)

    return output


def collect_data():
    global sess

    sess['step'] += 1

    output = []

    client = None

    try:
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=sess['hostname'], username=sess['username'], password=sess['password'])
    except Exception as e:
        print("collect_data:", e)
        client.close()
        sess['close_time'] = datetime.now()
        exit(1)

    sess['connect_time'] = datetime.now()
    log(f"-- [{sess['step']}] connected to host {sess['hostname']} as {sess['username']}..", echo=True)

    time_delay = cf['time_delay']

    try:
        with SSHClientInteraction(client, timeout=10, display=False) as interact:
            log(f"\tcollect_data: sleep for {time_delay} seconds..", echo=verbose)
            time.sleep(max(3, time_delay))  # wait for at least 3 seconds
            interact.send("")
            for i in range(len(cli)):
                sess['step'] += 1
                log(f"-- [{sess['step']}] submitting CLI set #{i}..", echo=True)
                t = datetime.now()
                output += send_cli(interact, i)
                log(f"-- [{sess['step']}] total execution time for CLI set #{i}: {datetime.now() - t}", echo=verbose)
        if debug:
            log("\n".join(output), echo=debug)
    except Exception as e:
        print(e)
    finally:
        client.close()
        sess['close_time'] = datetime.now()

    return output


def write_files(data, stats=None):
    global sess

    sess['step'] += 1

    log(f"-- [{sess['step']}] generating output at {sess['job_dir']}/..", echo=True)

    file = sess['cnf_file']  # .format(ddhhmm)
    with open(file, 'a') as f:
        username, cf['username'] = cf['username'], ''
        password, cf['password'] = cf['password'], ''
        f.write(json.dumps({'cf': cf, 'cli': cli, 'metrics': metrics, 'dp': dp}, indent=4))
        # json.dump({'cf': cf, 'cli': cli, 'metrics': metrics}, f)
        cf['username'], cf['password'] = username, password
        log(f"\tfile {file} saved", echo=verbose)

    file = sess['cli_file']  # .format(ddhhmm)
    with open(file, 'a') as f:
        f.write("\n".join(data))
        log(f"\tfile {file} saved", echo=verbose)

    if stats is not None:
        file = sess['sta_file']  # .format(ddhhmm)
        with open(file, 'a') as f:
            f.write(json.dumps(stats, indent=4, default=str))
            log(f"\tfile {file} saved", echo=verbose)


def analyze(data):
    global sess, metrics

    sess['step'] += 1

    log(f"-- [{sess['step']}] analyzing data..", echo=True)

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
                    log(f"matches: {matches}", echo=debug)
            if debug:
                log(f"{i} - text = {text}", echo=debug)
                log("-" * 80, echo=debug)
        if len(results[key]) == 0:  # delete empty matches from the results
            del results[key]

    for i, key in enumerate(results.keys()):
        values = results[key]
        v0 = float(values[0])
        s = {
            'min': v0, 'max': v0,
            'ave': 0,
            'val': list(zip(sess['timestamps'], values)),
            'cnt': len(values),
        }
        for value in values:
            v = float(value)
            s['min'] = min(s['min'], v)
            s['max'] = max(s['max'], v)
            s['ave'] += v
        s['ave'] /= s['cnt']
        output[key] = s
        log(f"\tmetrics: {key}: {s}", echo=verbose)

    return output


def analyze_dp(data):
    global sess

    sess['step'] += 1

    log(f"-- [{sess['step']}] analyzing DP data..", echo=True)

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
                    timestamp = sess['timestamps'][t]
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
        if verbose:
            _, values_0 = next(iter(output[dp_name]['_'].items()))
            log(f"\tanalyze_dp: DP {dp_name}: {len(values_0)} cores", echo=verbose)
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

    sess['dp_output'] = output

    return output


def plot_dp(data):
    global sess

    sess['step'] += 1

    log(f"-- [{sess['step']}] plotting DP..", echo=True)

    df_list = []
    plot_groups = {'0': []}

    plt.style.use('default')

    for dp_name in data.keys():
        plot_groups[dp_name] = []
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
        # core_groups.insert(0, [core for core_group in core_groups for core in core_group]) # group with all cores

        log(f"\tplot_dp: DP {dp_name}: core_groups: {core_groups}", echo=verbose)

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

            plot_file = dp['plot_file'].format(dp_name, i)
            plot_groups[dp_name].append(plot_file)

            if i == 0:
                plot_groups['0'].append(plot_file)
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
            plt.savefig(plot_file)
            plt.close()

            log(f"\tplot {plot_file} saved", echo=verbose)

    #
    # export data to CSV

    pd.concat(df_list).to_csv(dp['csv_file'], index=False)
    log(f"\tfile {dp['csv_file']} saved", echo=verbose)

    #
    # merge the summary plots

    merge_plots(plot_groups['0'], dp['plot_file_merged'], grid_size=dp['plot_grid_size'])


def read_conf(cf_path):
    if not exists(cf_path):
        log(f"read_conf: {cf_path}: file not found", echo=True)
        exit(1)
    name = "conf"
    spec = importlib.util.spec_from_file_location(name, cf_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)


def plot_stats(stats):
    global metrics

    plt.style.use('seaborn-v0_8')
    # plt.style.use('ggplot')
    colors = plt.rcParams['axes.prop_cycle'].by_key()['color']

    plot_files = []

    for i, metric in enumerate(metrics.keys()):
        if metric not in stats:  # i also skipped
            continue

        plot_file = cf['plot_file'].format(i, metric)
        data = stats[metric]['val']

        # Split into two lists
        timestamps, values = zip(*data)

        x = np.array([mdates.date2num(ts) for ts in timestamps])
        y = np.array([float(v) for v in values])

        x_smooth = np.linspace(x.min(), x.max(), 300)
        pchip = PchipInterpolator(x, y)
        y_smooth = pchip(x_smooth)
        # spline = make_interp_spline(x, y, k=2)  # avoid negative area
        # y_smooth = spline(x_smooth)

        color = colors[i % len(colors)]

        plt.figure(figsize=(10, 5))
        plt.plot(x_smooth, y_smooth, '-', label=metric)
        plt.fill_between(x_smooth, y_smooth, step='mid', alpha=0.4, color=color)

        ax = plt.gca()
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        plt.gcf().autofmt_xdate()

        plt.xlabel("time")
        plt.ylabel(metric)
        plt.title(f"Plot {i} - {metric}")
        # plt.legend()
        plt.grid(which='both', linestyle='--', linewidth=0.4, alpha=0.4)
        # plt.grid(True)
        plt.tight_layout()
        plt.savefig(plot_file)
        plt.close()

        plot_files.append(plot_file)

    merge_plots(plot_files, cf['plot_file_merged'], grid_size=dp['plot_grid_size'])


def merge_plots(source, target, grid_size=(1,1)):
    n_plots = len(source)
    n_rows, n_cols = grid_size  # (n_plots + 1) // 2, 2

    if n_rows * n_cols <= 1 or n_plots <= 1:
        return

    log(f"\tmerging {n_plots} plots", echo=verbose)

    for i in range(0, n_plots, n_rows * n_cols):
        plot_file_merged = target.format(i)  # f"p-{i}.png"
        fig, axs = plt.subplots(n_rows, n_cols, figsize=(n_cols * 6, n_rows * 4))
        axs = axs.flatten()
        n = min(i + n_rows * n_cols, n_plots)
        for j in range(i, n):
            plot_file = source[j]  # f"p{j}-{m[j]}.png"
            image = plt.imread(plot_file)
            axs[j-i].imshow(image)
            axs[j-i].axis('off')
        for j in range(n, i + n_rows * n_cols):
            axs[j-i].axis('off')
        plt.tight_layout()
        plt.savefig(plot_file_merged)
        plt.close()


if __name__ == '__main__':

    sess['start_time'] = datetime.now()

    parser = argparse.ArgumentParser(prog='pan-cli.py', description='Script to repeat CLI over SSH.', add_help=False)
    parser.add_argument('-c', '--conf', nargs='?', type=str, default="conf/cli.py", help="config")
    parser.add_argument('-h', '--host', type=str, help="host")
    parser.add_argument('-u', '--user', type=str, help="user")
    parser.add_argument('-v', '--verbose', action='store_true', help="verbose")
    # parser.add_argument('target', nargs='?', help="IP of target device")
    parser.add_argument('-?', '--help', action='help', help='show this help message and exit')
    parser.print_help()
    print()

    args = parser.parse_args()

    if verbose:
        print(args, "\n")

    read_conf(args.conf)
    from conf import cf, cli, metrics, dp

    init()
    data_ = collect_data()
    stats_ = analyze(data_)
    plot_stats(stats_)
    write_files(data_, stats_)

    data_dp_ = analyze_dp(data_)
    plot_dp(data_dp_)

    sess['step'] += 1
    sess['end_time'] = datetime.now()

    log(f"-- [{sess['step']}] exiting..", echo=True)
    log(f"\ttime connected: {sess['close_time'] - sess['connect_time']} / {cf['duration']}", echo=True)
    log(f"\ttime elapsed: {sess['end_time'] - sess['start_time']} / {cf['duration']}", echo=True)

    if verbose:
        for key in sess:
            if key not in ('log_buf', 'dp_output'):
                log(f"\tsess.{key}: {sess[key]}", echo=verbose)
        if 'dp' in sess['dp_output']:
            log(f"\tsess.dp_output.dp.keys: {sess['dp_output']['dp'].keys()}", echo=verbose)

    log(f"-- [{sess['step']}] job {sess['job_dir']} completed", echo=True, flush=True)
