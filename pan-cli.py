"""

pan-os-cli v2.3 [20260617]
pan-os-cli v2.2 [20260607]
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
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import paramiko
from paramiko_expect import SSHClientInteraction
from scipy.interpolate import make_interp_spline, PchipInterpolator

from pan_api import pan_api
from pan_log import pan_get_traffic_logs


cf, cli, metrics, dp = {}, [], {}, {}

ctx = {  # context to store runtime data
    'start_time': datetime.now(),
}


def get_logger(name, log_file):
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        '[%(asctime)s] %(funcName)s %(levelname)s %(message)s'
    )

    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.propagate = False

    return logger


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
    print(ctx['args'], "\n")

    ctx['verbose'] = cf['verbose'] or ctx['args'].verbose
    ctx['debug'] = cf['debug']

    msg_buf = []

    h, u, p, e = 'hostname', 'username', 'password', 'passenv'
    x = (h, u, p)
    y = (None, 'admin', None)  # default
    z = (ctx['args'].host, ctx['args'].user, os.getenv(cf[e]))  # specified through CLI

    for i, attr in enumerate(x):
        ctx[attr] = z[i] or cf[attr] or y[i]
        val = ctx[attr]
        if not val:
            print("access undefined or empty", file=sys.stderr)
            print(f"check {ctx['args'].conf} for details ('{attr}')", file=sys.stderr)
            sys.exit(1)
        if ctx['verbose']:
            msg_buf.append(f"\tattr = {attr}, value = {val}")

    ctx['api_key'] = pan_api((ctx['hostname'], ctx['username'], ctx['password']))

    start_time = ctx['start_time']
    ddhhmm = start_time.strftime('%d%H%M')

    for f in ('job_dir', 'log_file', 'cnf_file', 'cli_file', 'sta_file', 'tra_file', 'ctx_file'):
        ctx[f] = cf[f].format(ddhhmm, ctx['hostname']) if f in cf else f"{f}-{ddhhmm}"

    job_dir = ctx['job_dir']
    os.makedirs(job_dir, exist_ok=True)

    ctx['log'] = get_logger(__name__, os.path.join(job_dir, ctx['log_file']))
    ctx['log'].setLevel(logging.DEBUG if ctx['debug'] else logging.INFO if ctx['verbose'] else logging.WARNING)

    ctx['log'].info(f"initializing the environment..")
    print("\n".join(msg_buf))  # no log

    if 'duration' in cf and len(cf['duration']) > 0:
        ctx['duration'] = duration_to_seconds(cf['duration'])  # convert duration string into seconds
        ctx['log'].info(f"(max) duration {cf['duration']} = {ctx['duration']}s")

    ctx['log'].info(f"(max) iterations {cf['iterations']}")
    ctx['log'].info(f"verbose = {ctx['verbose']}, debug = {ctx['debug']}")

    ctx['timestamps'] = []
    ctx['metrics'] = {}

    if 'dp_name_default' in dp and dp['dp_name_default'] == 'dp':
        dp['dp_name_default'] = 'dp0'
        ctx['log'].info("dp['dp_name_default'] set to 'dp0' as 'dp' is reserved")

    os.chdir(job_dir)


def send_cli(interact, cli_idx):
    output = []

    cli_list = cli[cli_idx]
    cli_tuple = (cli_list, 1) if type(cli_list) is list else cli_list  # wrap the CLI list in a tuple, repeat it once
    cli_, iterations = cli_tuple

    prompt = cf['prompt']
    time_interval = cf['time_interval']

    ctx['log'].info(f"{len(cli_)} entries from set {cli_idx} for {iterations} (max) iterations..")

    for i in range(iterations):
        t0 = datetime.now()
        for j, c in enumerate(cli_):
            ctx['log'].info(f"[{j}_{i}/{iterations}] c = {c}")

            c_ = (c,) if isinstance(c, str) else c  # convert it back to a tuple in case of a string
            c_len = len(c_)

            command, count, timeout = c_[0], 1, cf['cli_timeout']

            if c_len > 1:
                count = max(count, int(c_[1]))  # at least once
                if c_len > 2:
                    timeout = c_[2]

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
                output.append(o)  # output.append(interact.current_output_clean)

        now = datetime.now()
        elapsed = int((now - ctx['start_time']).total_seconds())
        remaining = max(0, ctx['duration'] - elapsed)

        ctx['log'].info(f"cli set executed in {now - t0}")
        ctx['log'].info(f"elapsed | remaining [{timedelta(seconds=elapsed)} | {timedelta(seconds=remaining)}]")
        if elapsed >= ctx['duration']:  # time elapsed has exceeded ctx['duration']
            ctx['log'].warning(f"elapsed={elapsed} has exceeded target duration={ctx['duration']} seconds")
            break

        if i < iterations - 1:
            ctx['log'].info(f"sleep for {time_interval} seconds..")
            time.sleep(time_interval)

    return output


def collect_data():
    output = []

    client = None

    try:
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=ctx['hostname'],
            username=ctx['username'], password=ctx['password'],
            timeout=cf['conn_timeout']
        )
    except Exception as e:
        ctx['log'].error(f"{ctx['hostname']}: {str(e)}")
        client.close()
        ctx['close_time'] = datetime.now()
        sys.exit(1)

    ctx['connect_time'] = datetime.now()
    ctx['log'].info(f"connected to host {ctx['hostname']} as {ctx['username']}..")

    time_delay = max(2, cf['time_delay'])

    try:
        with SSHClientInteraction(
                client, timeout=10, display=ctx['debug'],
                tty_width=cf['tty_size'][0], tty_height=cf['tty_size'][1]
        ) as interact:
            ctx['log'].info(f"sleep for {time_delay} seconds..")
            time.sleep(time_delay)  # wait for at least 3 seconds
            interact.send("")
            for i in range(len(cli)):
                ctx['log'].info(f"submitting cli set {i}..")
                t = datetime.now()
                output += send_cli(interact, i)
                ctx['log'].info(f"execution time for cli set {i}: {datetime.now() - t}")
        ctx['log'].debug("\n".join(output))
    except Exception as e:
        ctx['log'].warning(f"{ctx['hostname']}: {str(e)}")
    finally:
        client.close()
        ctx['close_time'] = datetime.now()

    return output


def write_files(data, stats=None):
    ctx['log'].info(f"generating output at {ctx['job_dir']}/..")

    file = ctx['cnf_file']
    with open(file, 'a') as f:
        password = cf['password']
        del cf['password']
        f.write(json.dumps({'cf': cf, 'cli': cli, 'metrics': metrics, 'metrics2': metrics2, 'dp': dp}, indent=2))
        cf['password'] = password
        ctx['log'].info(f"file {file} saved")

    file = ctx['cli_file']
    with open(file, 'a') as f:
        f.write("\n".join(data))
        ctx['log'].info(f"file {file} saved")

    if stats is not None:
        file = ctx['sta_file']
        with open(file, 'a') as f:
            f.write(json.dumps(stats, indent=2, default=str))
            ctx['log'].info(f"file {file} saved")


def get_joke():
    try:
        import pyjokes
        print(f"\n{pyjokes.get_joke()}")
    except Exception:
        pass


def cleanup():
    ctx['log'].info(f"cleaning up..")

    del ctx['password']  # no longer needed from now on, and not saved

    if ctx['verbose']:
        for key, val in ctx.items():
            if key not in ('log_buf', 'dp_output'):
                ctx['log'].info(f"ctx['{key}']: {val}")
        for key, val in ctx['dp_output'].items():
            if isinstance(val, dict):
                for k, v in ctx['dp_output'][key].items():
                    ctx['dp_output'][key][k] = None
                ctx['log'].info(f"ctx['dp_output']['{key}'].keys(): {ctx['dp_output'][key].keys()}")

    duration = timedelta(seconds=ctx['duration'])
    ctx['log'].info(f"time connected: {ctx['close_time'] - ctx['connect_time']} / {duration}")
    ctx['end_time'] = datetime.now()
    ctx['log'].info(f"time elapsed: {ctx['end_time'] - ctx['start_time']} / {duration}")
    ctx['log'].info(f"job {ctx['job_dir']} completed, exiting..")

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
    ctx['log'].info(f"analyzing data..")

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
                ctx['log'].debug(f"match {metric} values {values}")
            ctx['log'].debug(f"{i} - text = {text}")
            ctx['log'].debug("-" * 80)
        if len(results[metric]) == 0:  # delete empty matches from the results
            del results[metric]

    np_dict = {}
    for metric, val_list in results.items():
        val_np = np.array(val_list, dtype=float)
        if ctx['debug']:
            print(val_np)
        np_dict[metric] = val_np
        ctx['metrics'][metric] = metrics[metric]

    for metric2, metric_cf in metrics2.items():
        metric = metric2 if metric2 not in metrics else f"{metric2}_2"
        expr = metric_cf if not isinstance(metric_cf, tuple) else metric_cf[0]
        try:
            with np.errstate(divide='raise', invalid='raise', over='raise'):
                val_np = eval(expr, {"__builtins__": None}, {**np_dict, 'np': np})
                if val_np.ndim == 1:
                    val_np = np.asarray(val_np).reshape(-1, 1)  # (T,) reshaped to (T, 1)
        except Exception as e:
            ctx['log'].warning(f"{metric} failed: '{expr}': {str(e)}")
            continue
        np_dict[metric] = val_np
        ctx['metrics'][metric] = metrics2[metric2]

    for key, val_np in np_dict.items():
        s = {
            'min': np.min(val_np, axis=0).tolist(),
            'max': np.max(val_np, axis=0).tolist(),
            'ave': np.mean(val_np, axis=0).tolist(),
            'cnt': int(val_np.shape[0]),
            'val': [(ctx['timestamps'][i], val_np[i].tolist()) for i in range(len(ctx['timestamps']))]
        }
        output[key] = s

    if ctx['debug']:
        for key, value in output.items():
            ctx['log'].debug(f"metrics: {key}: {value}")

    return output


def analyze_dp(data):
    ctx['log'].info(f"analyzing DP data..")

    output = {}
    dp_name = dp['dp_name_default']
    t, timestamp, s, seconds = 0, None, 0, None

    for text in data:
        found = False
        lines = text.split('\n')
        i, n = 0, len(lines)
        while i < n:
            line = lines[i]
            i += 1
            match = re.search(dp['dp_name'], line)
            if match:
                dp_name = match.group(1)
                continue
            match = re.search(dp['cpu_load'], line)
            if not match:
                continue
            found = True
            seconds = min(cf['time_interval'], int(match.group(1)))  # seconds = number of data rows
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
                    if not values:
                        break  # empty line indicates end of section
                    if s <= 0:
                        continue  # value lines outside time window ignored until next core header line with s reset
                    is_first_row = (s == seconds)
                    timestamp -= timedelta(seconds=1)
                    s -= 1
                    if is_first_row and dp['skip_first_row']:
                        continue  # first value line ignored (usually with some zeros)
                    for j, core in enumerate(cores[1:]):
                        value = values[j]
                        if value.isdigit():  # '*' ignored
                            value = int(value)
                            output[dp_name][core].append((timestamp, value))
                            if '_' not in output[dp_name]:  # values by timestamp
                                output[dp_name]['_'] = {}
                            if timestamp not in output[dp_name]['_']:
                                output[dp_name]['_'][timestamp] = []
                            output[dp_name]['_'][timestamp].append(value)
        if found:
            t += 1  # next timestamp when the DP command was issued

    for dp_name in output.keys():
        values = next(iter(output[dp_name]['_'].values()))
        n = len(values)
        ctx['log'].info(f"DP {dp_name}: {n} cores")
        for timestamp, values in output[dp_name]['_'].items():
            output[dp_name]['min'].append((timestamp, min(values)))
            output[dp_name]['max'].append((timestamp, max(values)))
            output[dp_name]['ave'].append((timestamp, sum(values) / n))

    ctx['dp_output'] = output

    return output


def plot_dp(data):
    ctx['log'].info(f"plotting DP..")

    df_list = []
    plot_groups = {'0': []}
    watermark = []

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

        ctx['log'].info(f"DP {dp_name}: core_groups: {core_groups}")

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
                    plt.fill_between(x_smooth_datetime, y_smooth, step='mid', alpha=0.4)  # , color='skyblue')

            plot_file = dp['plot_file'].format(dp_name, i)
            plot_groups[dp_name].append(plot_file)

            if i == 0:
                plot_groups['0'].append(plot_file)
                plt.title(f"DP Utilization ({dp_name})")
                watermark.append(dp_name)
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

            ctx['log'].info(f"plot {plot_file} saved")

    pd.concat(df_list).to_csv(dp['csv_file'], index=False)
    ctx['log'].info(f"file {dp['csv_file']} saved")

    combine_plots(plot_groups['0'], dp['plot_file_combined'], grid_size=dp['plot_grid_size'], watermark=watermark)


def read_conf(cf_path):
    if not os.path.exists(cf_path):
        ctx['log'].info(f"{cf_path}: file not found")
        sys.exit(1)
    name = "conf"
    spec = importlib.util.spec_from_file_location(name, cf_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)


def plot_stats(stats):
    ctx['log'].info(f"plotting stats..")

    plt.style.use('seaborn-v0_8')  # 'ggplot')
    colors = plt.rcParams['axes.prop_cycle'].by_key()['color']

    plot_files, watermark = [], []

    for i, (metric, metric_cf) in enumerate(ctx['metrics'].items()):
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
        if isinstance(metric_cf, tuple) and y.shape[1] > 1:
            legends = metric_cf[1]
            if len(metric_cf) > 2:
                k = metric_cf[2]
        ctx['log'].info(f"metric = {metric}, legends = {legends}, k = {k}")

        for j in range(y.shape[1]):
            pchip = PchipInterpolator(x, y[:, j])
            y_smooth = pchip(x_smooth)

            highlight = (j == k)
            linestyle = '-'  # if highlight else '--'
            alpha = 0.95 if highlight else 0.65
            linewidth = 1.1 if highlight else 0.9  # (2.2, 1.6)
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

        ctx['log'].info(f"plot {plot_file} saved")

        plot_files.append(plot_file)
        watermark.append(metric)

    combine_plots(plot_files, cf['plot_file_combined'], grid_size=cf['plot_grid_size'], watermark=watermark)


def combine_plots(
        source, target, grid_size=(1,1), watermark=None,
        start=0, shift=0.0
):
    n_plots = len(source)
    n_rows, n_cols = grid_size

    if n_rows * n_cols <= 1 or n_plots <= 1:
        return

    ctx['log'].info(f"creating plot grid from {n_plots} plots")

    for i in range(0, n_plots, n_rows * n_cols):
        plot_file_combined = target.format(start + i)
        fig, axs = plt.subplots(n_rows, n_cols, figsize=(n_cols * 6, n_rows * 4))
        axs = axs.flatten()
        n = min(i + n_rows * n_cols, n_plots)
        for j in range(i, n):
            plot_file = source[j]
            image = plt.imread(plot_file)
            ax = axs[j-i]
            ax.imshow(image)
            ax.axis('off')
            if watermark:
                label = watermark[j]
                ax.text(
                    0.5 + shift, 0.5, label,
                    transform=ax.transAxes,
                    fontsize=25,
                    color='black', alpha=0.1,
                    # color='white', alpha=0.5, bbox=dict(facecolor='black', alpha=0.1, edgecolor='none'),
                    ha='center', va='center',
                    weight='bold',
                    rotation=10
                )
        for j in range(n, i + n_rows * n_cols):
            axs[j-i].axis('off')
        plt.tight_layout()
        plt.savefig(plot_file_combined)
        plt.close()

        ctx['log'].info(f"combined plot {plot_file_combined} saved")


def analyze_logs_traffic():
    if 'traffic_analysis' not in cf or not cf['traffic_analysis']:
        return None

    n_logs = cf['tra_cnt']

    ctx['log'].info(f"analyzing most recent {n_logs:,} traffic logs entries")

    logs = pan_get_traffic_logs(
        ctx['hostname'],
        ctx['api_key'],
        columns=cf['tra_cols'],
        nlogs=n_logs,
    )
    file = ctx['tra_file']
    with open(file, "w") as f:
        json.dump(logs, f, indent=2)

    ctx['log'].info(f"traffic logs {file} saved")

    df = pd.DataFrame(logs)
    columns = ['bytes', 'elapsed']
    df[columns] = df[columns].apply(pd.to_numeric, errors="coerce")
    file = cf['tra_csv_file']
    df.to_csv(file, index=False)

    ctx['log'].info(f"traffic logs {file} saved")

    return df


def plot_logs_traffic(df):
    if 'traffic_analysis' not in cf or not cf['traffic_analysis']:
        return

    ctx['log'].info(f"plotting traffic stats..")

    colors = plt.rcParams['axes.prop_cycle'].by_key()['color']
    n_colors = len(colors)

    plot_files, watermark = [], []
    plot_file_combined = cf['tra_plot_file_combined']
    grid_size = cf['tra_plot_grid_size']

    stats = df.groupby("app").agg(
        bytes_sum=("bytes", "sum"),
        elapsed_sum=("elapsed", "sum"),
        sess_count=("app", "count")
    )
    stats["bytes_avg"] = (stats["bytes_sum"] / stats["sess_count"])
    stats["elapsed_avg"] = (stats["elapsed_sum"] / stats["sess_count"])

    data = {
        'sess_count': ('topAppsByLogCount', 'Count'),
        'bytes_sum': ('topAppsByBytesSum', 'Bytes'),
        'elapsed_sum': ('topAppsByElapsedSum', 'Seconds'),
        'bytes_avg': ('topAppsByBytesAvg', 'Bytes'),
        'elapsed_avg': ('topAppsByElapsedAvg', 'Seconds'),
    }

    top_k = cf['tra_apps_top_k']

    for i, column in enumerate(data.keys()):
        title, xlabel = data[column]

        plot_file = cf['tra_plot_file'].format(i, title)

        apps = stats[column].sort_values(ascending=False).head(top_k).sort_values()

        fig, ax = plt.subplots(figsize=(10, 5))

        y_pos = range(len(apps))

        color = colors[i % n_colors]

        ax.barh(
            y_pos,
            apps.values,
            color=color,  # "#4C72B0",  # simple seaborn-like blue
            edgecolor="grey",  # "dimgray",
            linewidth=0.8,
            alpha=0.9
        )

        ax.set_yticks(y_pos)
        ax.set_yticklabels(apps.index)

        max_v = apps.max()

        for j, (val) in enumerate(apps.values):
            ax.text(
                val + max_v * 0.01,  # right of bar
                j,
                f"{val:,.0f}",
                va="center", ha="left",
                fontsize=9,
                fontweight="bold"
            )

        ax.set_xlim(0, max_v * 1.2)

        ax.grid(axis="x", linestyle="--", alpha=0.4)

        ax.set_title(f"{title} (k={top_k}) ")
        ax.set_xlabel(xlabel)

        plt.tight_layout()
        plt.savefig(plot_file)
        plt.close()

        ctx['log'].info(f"plot {plot_file} saved")

        plot_files.append(plot_file)
        watermark.append(title)

    combine_plots(plot_files, plot_file_combined, grid_size=grid_size, watermark=watermark, shift=0.2)
    plot_files, watermark = [], []

    # distribution of column values like bytes and elapsed
    #
    for i, column in enumerate(cf['tra_bins'].keys(), start=len(data)):
        title = column.title()
        xlabel = title

        plot_file = cf['tra_plot_file'].format(i, title)

        bins, labels = cf['tra_bins'][column]

        plt.figure(figsize=(10, 5))

        color = colors[i % n_colors]

        ax = sns.histplot(
            df[column],
            bins=bins,
            color=color,
            edgecolor="grey",  # "dimgray",  # "black",
            linewidth=1.0,
            alpha=0.4
        )

        ax.set_title(f"Traffic Log Distribution - {title}")
        ax.set_xlabel(xlabel)
        ymax = ax.get_ylim()[1]
        ax.set_ylim(0, ymax * 1.25)

        plt.xscale("log")

        for j, p in enumerate(ax.patches):
            h = p.get_height()

            if h <= 0:
                continue

            left = labels[j]
            if j < len(labels) - 1:
                right = labels[j + 1]
                label = f"{left}-{right}"
            else:
                label = f"> {left}"

            x = p.get_x() + p.get_width()

            if h > 0:
                ax.text(
                    x,
                    h * 1.05,
                    f"{int(h):,}\n{label}",
                    ha="right", va="bottom",
                    fontsize=8
                )

        plt.grid(True, which="both", axis="both", linestyle="--", alpha=0.3)

        plt.tight_layout()
        plt.savefig(plot_file)
        plt.close()

        ctx['log'].info(f"plot {plot_file} saved")

        plot_files.append(plot_file)
        watermark.append(title)

    combine_plots(plot_files, plot_file_combined, grid_size=grid_size, watermark=watermark, start=len(data))


if __name__ == '__main__':
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
    data_logs_ = analyze_logs_traffic()
    plot_logs_traffic(data_logs_)
    cleanup()
