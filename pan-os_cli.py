"""

pan-os_cli v1.0 [20230421]

Script to repeat CLI commands on PAN-OS over SSH

by Terence LEE <telee.hk@gmail.com>

https://github.com/telee0/pan_scripts
https://pexpect.readthedocs.io/en/stable/index.html

"""

import json
import os
import re
import time
from datetime import datetime
from os import makedirs

import paramiko
from paramiko_expect import SSHClientInteraction

from cli import cf, cli, metrics

verbose, debug = True, False


# check here for more use cases
#
# https://github.com/fgimian/paramiko-expect/blob/master/examples/paramiko_expect-demo.py

def send_cli(interact, cli_idx):
    cli_list = cli[cli_idx]
    cli_tuple = (cli_list, 1) if type(cli_list) is list else cli_list  # convert list to tuple in case
    cli_, iterations = cli_tuple

    prompt = cf['prompt']
    time_interval = cf['time_interval']

    output = []

    for i in range(iterations):
        for c_ in cli_:
            if verbose:
                t = datetime.now().strftime('%H:%M:%S')
                print(f"[{cli_idx}.{i:02d} {t}] c =", c_)  # original form

            c = (c_,) if isinstance(c_, str) else c_  # convert it back to a tuple in case of a string

            command, count, timeout = c[0], 1, cf['cli_timeout']

            c_len = len(c)
            if c_len >= 2:
                count = max(count, int(c[1]))  # make sure at least once
                if c_len >= 3:
                    timeout = c[2]

            for j in range(count):  # repeat_count of each command line
                if timeout > 0:
                    interact.expect([prompt], timeout=timeout)
                interact.send(command)
                output.append(interact.current_output_clean)

        if i < iterations - 1:
            print(f"-- sleep for {time_interval} seconds..")
            time.sleep(time_interval)

    return output


def collect_data():
    hostname = cf['hostname']
    username = cf['username']
    password = cf['password']

    time_delay = cf['time_delay']

    client = None

    # SSH to login
    #
    try:
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=hostname, username=username, password=password)
    except Exception as e:
        print("go:", e)
        client.close()
        return

    output = []

    try:
        with SSHClientInteraction(client, timeout=10, display=False) as interact:
            print(f"-- sleep for {time_delay} seconds..")
            time.sleep(max(3, time_delay))  # wait for at least 3 seconds
            interact.send("")
            for i in range(len(cli)):
                print(f"-- submit CLI set #{i}..")
                output += send_cli(interact, i)
        if debug:
            print("\n".join(output))
    except Exception as e:
        print(e)
    finally:
        client.close()

    return output


def write_data(data, stats=None):
    t = datetime.now().strftime('%Y%m%d%H%M')
    ddhhmm = t[6:12]

    # prepare the directory structure for job files
    #
    job_dir = cf['job_dir'].format(ddhhmm)
    makedirs(job_dir, exist_ok=True)
    os.chdir(job_dir)

    if verbose:
        print(f"-- generate output at {job_dir}/..")

    step = '0.00'

    file = cf['cnf_file'].format(ddhhmm)
    with open(file, 'a') as f:
        username, cf['username'] = cf['username'], ''
        password, cf['password'] = cf['password'], ''
        f.write(json.dumps({'cf': cf, 'cli': cli, 'metrics': metrics}, indent=4))
        # json.dump({'cf': cf, 'cli': cli, 'metrics': metrics}, f)
        cf['username'], cf['password'] = username, password
        if verbose:
            t = datetime.now().strftime('%H:%M:%S')
            print(f"[{step} {t}] file = {file}")

    file = cf['cli_file'].format(ddhhmm)
    with open(file, 'a') as f:
        f.write("\n".join(data))
        if verbose:
            t = datetime.now().strftime('%H:%M:%S')
            print(f"[{step} {t}] file = {file}")

    if stats is None:
        return

    file = cf['sta_file'].format(ddhhmm)
    with open(file, 'a') as f:
        f.write(json.dumps(stats, indent=4))
        if verbose:
            t = datetime.now().strftime('%H:%M:%S')
            print(f"[{step} {t}] file = {file}")


def analyze(data):
    if verbose:
        print(f"-- analyze data..")

    step = '0.00'

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

    for key in results.keys():
        v_0 = float(results[key][0])
        s = {
            'min': v_0, 'max': v_0,
            'ave': 0,
            'cnt': len(results[key])
        }
        for v_i in results[key]:
            value = float(v_i)
            s['min'] = min(s['min'], value)
            s['max'] = max(s['max'], value)
            s['ave'] += value
        s['ave'] /= s['cnt']
        if verbose:
            t = datetime.now().strftime('%H:%M:%S')
            print(f"[{step} {t}] {key}:", results[key])
            print(f"[{step} {t}] stats:", s)
        output[key] = s

    return output


if __name__ == '__main__':
    data_ = collect_data()
    stats_ = analyze(data_)
    write_data(data_, stats_)
