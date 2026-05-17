"""

pan-os_cli v2.1 [20260515]
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

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import paramiko
from paramiko_expect import SSHClientInteraction
from scipy.interpolate import make_interp_spline, PchipInterpolator

cf, cli, metrics, dp = {}, [], {}, {}

ctx = {  # context to store runtime data
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
    ctx['step'] = 0

    print(ctx['args'], "\n")

    log(f"-- [{ctx['step']}] initializing the environment..", echo=True)

    ctx['verbose'] = cf['verbose'] or ctx['args'].verbose
    ctx['debug'] = cf['debug']

    h, u, p, e = 'hostname', 'username', 'password', 'passenv'
    x = (h, u, p)
    y = (None, 'admin', None)  # default
    z = (ctx['args'].host, ctx['args'].user, os.getenv(cf[e]))  # specified

    for i, attr in enumerate(x):
        ctx[attr] = z[i] or cf[attr] or y[i]
        value = ctx[attr]
        if ctx['verbose']:
            print(f"\tinit: value = {value}")
        if not value:
            print("init: access undefined or empty")
            print(f"init: check {ctx['args'].conf} for details ('{attr}')")
            exit(1)

    # convert duration string into seconds
    #
    if 'duration' in cf and len(cf['duration']) > 0:
        ctx['duration'] = duration_to_seconds(cf['duration'])
        log(f"\tinit: (max) duration {cf['duration']} = {ctx['duration']}s", echo=ctx['verbose'])

    log(f"\tinit: (max) iterations {cf['iterations']}", echo=ctx['verbose'])

    ddhhmm = datetime.now().strftime('%d%H%M')

    for f in ('job_dir', 'cnf_file', 'cli_file', 'sta_file', 'log_file', 'ctx_file'):
        ctx[f] = cf[f].format(ddhhmm, ctx['hostname']) if f in cf else f"{f}-{ddhhmm}"

    # prepare the directory structure for job files
    #
    job_dir = ctx['job_dir']
    makedirs(job_dir, exist_ok=True)
    os.chdir(job_dir)

    ctx['timestamps'] = []

    log(f"\tverbose = {ctx['verbose']}, debug = {ctx['debug']}", echo=ctx['verbose'])


def log(message, echo=False, flush=False):
    curr_time = datetime.now()
    t = int((curr_time - ctx['start_time']).total_seconds())
    elapsed = f"{t // 3600:02d}:{(t % 3600) // 60:02d}:{t % 60:02d}"

    message = f"[{curr_time.strftime('%H:%M:%S')} | {elapsed}] " + message
    if echo:
        print(message)
    ctx['log_buf'].append(message)
    if len(ctx['log_buf']) > cf['log_buf_size'] or flush:
        with open(ctx['log_file'], 'a') as f:
            ctx['log_buf'].append("")
            f.write("\n".join(ctx['log_buf']))
        ctx['log_buf'].clear()
        if len(ctx['log_buf']) > 0:
            print(f"log: entries not written to {cf['log_file']}")
            exit(1)


# check here for more use cases
# https://github.com/fgimian/paramiko-expect/blob/master/examples/paramiko_expect-demo.py
#
def send_cli(interact, cli_idx):
    output = []

    cli_list = cli[cli_idx]
    cli_tuple = (cli_list, 1) if type(cli_list) is list else cli_list  # wrap the CLI list in a tuple, repeat it once
    cli_, iterations = cli_tuple

    prompt = cf['prompt']
    time_interval = cf['time_interval']

    log(f"\tsend_cli: {len(cli_)} entries from set #{cli_idx} for {iterations} (max) iterations..", echo=ctx['verbose'])

    for i in range(iterations):
        t0 = datetime.now()
        for j, c_ in enumerate(cli_):
            log(f"[{ctx['step']}:{i}.{j}/{iterations}] c = {c_}")

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
                    ctx['timestamps'].append(datetime.now())

                o = interact.current_output_clean
                o = o.replace('\x00', '')
                o = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', o)
                output.append(o)
                # output.append(interact.current_output_clean)

        log(f"-- [{ctx['step']}] CLI set executed in {datetime.now() - t0}", echo=ctx['verbose'])

        # stop at command set level if time elapsed has exceeded ctx['duration_seconds']
        #
        t = (datetime.now() - ctx['start_time']).total_seconds()
        if t >= ctx['duration']:
            log(f"\trun time exceeded t = {t} >= {ctx['duration']} s (ctx['duration'])", echo=ctx['debug'])
            break

        if i < iterations - 1:
            log(f"\tsend_cli: sleep for {time_interval} seconds..", echo=ctx['verbose'])
            time.sleep(time_interval)

    return output


def collect_data():
    ctx['step'] += 1

    output = []

    client = None

    try:
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=ctx['hostname'],
            username=ctx['username'],
            password=ctx['password']
        )
    except Exception as e:
        print("collect_data:", e)
        client.close()
        ctx['close_time'] = datetime.now()
        exit(1)

    ctx['connect_time'] = datetime.now()
    log(f"-- [{ctx['step']}] connected to host {ctx['hostname']} as {ctx['username']}..", echo=True)

    time_delay = cf['time_delay']

    try:
        # with SSHClientInteraction(client, timeout=10, display=False) as interact:
        with SSHClientInteraction(
                client, timeout=10, display=False,
                tty_width=cf['tty_size'][0], tty_height=cf['tty_size'][1]
        ) as interact:
            log(f"\tcollect_data: sleep for {time_delay} seconds..", echo=ctx['verbose'])
            time.sleep(max(3, time_delay))  # wait for at least 3 seconds
            interact.send("")
            for i in range(len(cli)):
                ctx['step'] += 1
                log(f"-- [{ctx['step']}] submitting CLI set #{i}..", echo=True)
                t = datetime.now()
                output += send_cli(interact, i)
                log(f"-- [{ctx['step']}] total execution time for CLI set #{i}: {datetime.now() - t}", echo=ctx['verbose'])
        if ctx['debug']:
            log("\n".join(output), echo=ctx['debug'])
    except Exception as e:
        print(e)
    finally:
        client.close()
        ctx['close_time'] = datetime.now()

    return output


def write_files(data, stats=None):
    ctx['step'] += 1

    log(f"-- [{ctx['step']}] generating output at {ctx['job_dir']}/..", echo=True)

    file = ctx['cnf_file']  # .format(ddhhmm)
    with open(file, 'a') as f:
        password = cf['password']
        del cf['password']
        f.write(json.dumps({'cf': cf, 'cli': cli, 'metrics': metrics, 'metrics2': metrics2, 'dp': dp}, indent=2))
        # json.dump({'cf': cf, 'cli': cli, 'metrics': metrics}, f)
        cf['password'] = password
        log(f"\tfile {file} saved", echo=ctx['verbose'])

    file = ctx['cli_file']  # .format(ddhhmm)
    with open(file, 'a') as f:
        f.write("\n".join(data))
        log(f"\tfile {file} saved", echo=ctx['verbose'])

    if stats is not None:
        file = ctx['sta_file']  # .format(ddhhmm)
        with open(file, 'a') as f:
            f.write(json.dumps(stats, indent=2, default=str))
            log(f"\tfile {file} saved", echo=ctx['verbose'])


def get_joke():
    try:
        import pyjokes
        print(f"\n{pyjokes.get_joke()}")
    except Exception:
        pass


def cleanup():
    ctx['step'] += 1

    log(f"-- [{ctx['step']}] cleaning up..", echo=True)

    del ctx['password']  # no longer needed from now on, so to not be saved

    if ctx['verbose']:
        for key in ctx:
            if key not in ('log_buf', 'dp_output'):
                log(f"\tctx['{key}']: {ctx[key]}", echo=ctx['verbose'])
        for key, val in ctx['dp_output'].items():
            if isinstance(val, dict):
                for k, v in ctx['dp_output'][key].items():
                    ctx['dp_output'][key][k] = None
                log(f"\tctx['dp_output']['{key}'].keys(): {ctx['dp_output'][key].keys()}", echo=ctx['verbose'])

    duration = timedelta(seconds=ctx['duration'])
    log(f"\ttime connected: {ctx['close_time'] - ctx['connect_time']} / {duration}", echo=True)
    ctx['end_time'] = datetime.now()
    log(f"\ttime elapsed: {ctx['end_time'] - ctx['start_time']} / {duration}", echo=True)
    log(f"-- [{ctx['step']}] job {ctx['job_dir']} completed, exiting..", echo=True, flush=True)

    get_joke()

    file = ctx['ctx_file']
    for key, val in ctx.items():
        if isinstance(val, dict):
            for k, v in val.items():
                if isinstance(v, set):
                    val[k] = list(v)
        elif isinstance(val, list):
            ctx[key] = [v.isoformat() if isinstance(v, datetime) else v for v in val]
        # elif isinstance(val, set): ctx[key] = list(val)
        elif isinstance(val, datetime):
            ctx[key] = val.isoformat()
    with open(file, "w", encoding="utf-8") as f:
        json.dump(ctx, f, indent=2,
            skipkeys=True,
            default=lambda o: '<not serializable>',
        )


def analyze(data):
    ctx['step'] += 1

    log(f"-- [{ctx['step']}] analyzing data..", echo=True)

    output = {}   # stats
    results = {}  # results extracted from data

    for metric, pat_list in metrics.items():
        results[metric] = []
        if isinstance(pat_list, tuple):
            pattern = pat_list[0]
        else:
            pattern = pat_list
        for i, text in enumerate(data):
            match = re.search(pattern, text)
            if match:
                values = list(match.groups())
                results[metric].append(values)
                if ctx['debug']:
                    log(f"analyze: match {metric} values {values}", echo=ctx['debug'])
            if ctx['debug']:
                log(f"{i} - text = {text}", echo=ctx['debug'])
                log("-" * 80, echo=ctx['debug'])
        if len(results[metric]) == 0:  # delete empty matches from the results
            del results[metric]

    np_dict = {}
    for key, val_list in results.items():
        val_np = np.array(val_list, dtype=float)
        if ctx['debug']:
            print(val_np)
        np_dict[key] = val_np

    for key, expr in metrics2.items():
        metric = key + '2' if key in metrics else key
        try:
            with np.errstate(divide='raise', invalid='raise', over='raise'):
                val_np = eval(expr, {"__builtins__": None}, np_dict)
                val_np = np.asarray(val_np).reshape(-1, 1)  # shape always (T, 1)
        except Exception as e:
            print(f"[WARN] analyze: {key} failed: '{expr}': {e}")
            continue
        np_dict[metric] = val_np

    for key, val_np in np_dict.items():
        s = {
            'min': np.min(val_np, axis=0).tolist(),
            'max': np.max(val_np, axis=0).tolist(),
            'ave': np.mean(val_np, axis=0).tolist(),
            'cnt': int(val_np.shape[0]),
            'val': [(ctx['timestamps'][i], val_np[i].tolist()) for i in range(len(ctx['timestamps']))]
        }
        output[key] = s

    ctx['metrics'] = list(np_dict.keys())

    if ctx['verbose']:
        for key, value in output.items():
            log(f"\tmetrics: {key}: {value}", echo=ctx['verbose'])

    return output


def analyze_dp(data):
    ctx['step'] += 1

    log(f"-- [{ctx['step']}] analyzing DP data..", echo=True)

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
                    timestamp = ctx['timestamps'][t]
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
        if ctx['verbose']:
            _, values_0 = next(iter(output[dp_name]['_'].items()))
            log(f"\tanalyze_dp: DP {dp_name}: {len(values_0)} cores", echo=ctx['verbose'])
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

    ctx['dp_output'] = output

    return output


def plot_dp(data):
    ctx['step'] += 1

    log(f"-- [{ctx['step']}] plotting DP..", echo=True)

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

        log(f"\tplot_dp: DP {dp_name}: core_groups: {core_groups}", echo=ctx['verbose'])

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
            plt.grid(which='both', linestyle='--', linewidth=0.4, alpha=0.4)
            plt.legend()
            plt.tight_layout()
            plt.savefig(plot_file)
            plt.close()

            log(f"\tplot {plot_file} saved", echo=ctx['verbose'])

    pd.concat(df_list).to_csv(dp['csv_file'], index=False)
    log(f"\tfile {dp['csv_file']} saved", echo=ctx['verbose'])

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
    ctx['step'] += 1

    log(f"-- [{ctx['step']}] plotting stats..", echo=True)

    plt.style.use('seaborn-v0_8')  # 'ggplot')
    colors = plt.rcParams['axes.prop_cycle'].by_key()['color']

    plot_files = []

    for i, metric in enumerate(ctx['metrics']):
        if metric not in stats:  # i also skipped
            continue

        plot_file = cf['plot_file'].format(i, metric)
        data = stats[metric]['val']

        timestamps, values = zip(*data)  # Split into two lists

        x = np.array([mdates.date2num(ts) for ts in timestamps])
        y = np.array(values, dtype=float)

        x_smooth = np.linspace(x.min(), x.max(), 300)

        color = colors[i % len(colors)]

        plt.figure(figsize=(10, 5))

        legends, k = [metric], 0
        if metric in metrics and isinstance(metrics[metric], tuple) and y.shape[1] > 1:
            legends = metrics[metric][1]
            if len(metrics[metric]) > 2:
                k = metrics[metric][2]
        log(f"\tplot_stats: metric {metric} legends {legends} k {k}", echo=True)

        for j in range(y.shape[1]):
            pchip = PchipInterpolator(x, y[:, j])
            y_smooth = pchip(x_smooth)

            highlight = (j == k)
            linestyle = '-'  # if highlight else '--'
            alpha = 0.95 if highlight else 0.65
            linewidth = 2.2 if highlight else 1.6
            zorder = 4 if highlight else 3

            plt.plot(
                x_smooth, y_smooth,
                linestyle=linestyle,
                label=legends[j],
                alpha=alpha,
                linewidth=linewidth,
                zorder=zorder
            )

            if highlight:
                plt.fill_between(
                    x_smooth, y_smooth,
                    color=color,
                    alpha=0.45,
                    zorder=1,
                )

        ax = plt.gca()

        ax.set_facecolor('#f8fafc')
        ax.set_axisbelow(True)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        plt.gcf().autofmt_xdate()

        plt.xlabel("time")
        plt.ylabel(metric)
        plt.title(f"Plot {i} - {metric}")
        if y.shape[1] > 1:
            plt.legend()

        ax.grid(which='both', color='#000000', linestyle='-', linewidth=0.5, alpha=0.06)

        plt.tight_layout()
        plt.savefig(plot_file)
        plt.close()

        log(f"\tplot {plot_file} saved", echo=ctx['verbose'])

        plot_files.append(plot_file)

    merge_plots(plot_files, cf['plot_file_merged'], grid_size=cf['plot_grid_size'])


def merge_plots(source, target, grid_size=(1,1)):
    n_plots = len(source)
    n_rows, n_cols = grid_size  # (n_plots + 1) // 2, 2

    if n_rows * n_cols <= 1 or n_plots <= 1:
        return

    log(f"\tmerging {n_plots} plots", echo=ctx['verbose'])

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
    ctx['start_time'] = datetime.now()

    parser = argparse.ArgumentParser(prog='pan-cli.py', description='Script to repeat CLI over SSH.', add_help=False)
    parser.add_argument('-c', '--conf', nargs='?', type=str, default="conf/cli.py", help="config")
    parser.add_argument('-h', '--host', type=str, help="host")
    parser.add_argument('-u', '--user', type=str, help="user")
    parser.add_argument('-v', '--verbose', action='store_true', help="verbose")
    parser.add_argument('-?', '--help', action='help', help='show this help message and exit')
    parser.print_help()
    print()

    ctx['args'] = parser.parse_args()

    read_conf(ctx['args'].conf)
    from conf import cf, cli, metrics, metrics2, dp

    init()
    data_ = collect_data()
    stats_ = analyze(data_)
    plot_stats(stats_)
    write_files(data_, stats_)
    data_dp_ = analyze_dp(data_)
    plot_dp(data_dp_)
    cleanup()
