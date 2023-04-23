# pan-os_cli
Scripts to repeat CLI commands on PAN-OS over SSH

```
usage: pan-cli.py [-h] [-c [CONF]] [-v] [target]

Script to repeat PAN-OS CLI over SSH.

positional arguments:
  target                IP of the target device

options:
  -h, --help            show this help message and exit
  -c [CONF], --conf [CONF]
                        config file
  -v, --verbose         verbose mode

```

The following configuration parameters can be overriden in some ways.

cf['hostname']: specified as target on the command line
cf['username']: if empty, 'admin' is assumed
cf['password']: if empty, specified through the environment variable from cf['passenv']


Apr 23, 2023
