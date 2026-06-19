"""

pan-os-cli v2.3 [20260617]

Script to repeat CLI commands on PAN-OS over SSH

by Terence LEE <telee.hk@gmail.com>

https://github.com/telee0/pan-os_cli

"""

import requests
import xml.etree.ElementTree as ET
import time

# https://192.168.1.1/api/?
# type=log&
# log_type=traffic&
# query=(elapsed geq 0)&
# nlogs=100&
# key=LUFRPT1Lb2Z4VDlGWFlJVm4yUE1rKzJtdzA2T3cvMTg8Nkk4RzVsVlpkbGVUU3ZZWVVmOENwaGlHNWR6bFZVSTJQWG5tNlBIKzE5UDlKNG1CcXMvOVJmVWFGc2tZVlhJSA==

def pan_get_traffic_logs(
    firewall, api_key,
    columns=[],
    query="(action eq allow) and (elapsed geq 0)",  # "(session_end_reason neq incomplete)",
    nlogs=5000,
    verify_ssl=False
):
    base_url = f"https://{firewall}/api/"

    params = {
        "type": "log",
        "log-type": "traffic",
        "query": query,
        "nlogs": nlogs,
        "key": api_key
    }

    r = requests.get(base_url, params=params, verify=verify_ssl)
    r.raise_for_status()

    root = ET.fromstring(r.text)
    job_id = root.findtext(".//job")

    if not job_id:
        raise Exception(f"No job ID returned: {r.text}")

    results = []
    skip = 0

    while True:
        params = {
            "type": "log",
            "action": "get",
            "job-id": job_id,
            "key": api_key,
            "nlogs": nlogs,
            "skip": skip
        }

        r = requests.get(base_url, params=params, verify=verify_ssl)
        r.raise_for_status()

        root = ET.fromstring(r.text)

        log_entries = root.findall(".//entry")
        if not log_entries:
            break

        for e in log_entries:
            log = {}
            for col in columns:
                log[col] = e.findtext(col)
            if log:
                results.append(log)

        skip += nlogs

        if len(log_entries) < nlogs:
            break

        time.sleep(0.5)

    return results


if __name__ == '__main__':
    pass
