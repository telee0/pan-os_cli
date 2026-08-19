"""

report v1.1 [20260802]
report v1.0 [20260722]

Script to generate a report in pptx with data collected by pan-os_cli

by Terence LEE <telee.hk@gmail.com>

https://github.com/telee0/pan-os_cli
https://pexpect.readthedocs.io/en/stable/index.html

"""

cf = {
    'poc_number': 'POC18888',
    'poc_date': 'Aug 2026',
    'cust_name': 'Terence Investment',
    'subject': 'PA-5540 QoS Performance Testing',
    'author': 'Terence Lee <telee.hk@gmail.com>',

    'poc_dir': 'data/POC18888 (Terence Investment PA-5540 QoS)',
    'report_dir': 'report-{}',
    'report_file': 'poc18888.pptx',
    'log_file': 'report-{}.log',

    'template': 'data/pov_template.pptx',
    'sldId': {  # slide indexes
        'cover': 0,
        'agenda': 1,
        'summary': 2,        # executive summary
        'setup': 5,          # setup details
        'results': 7,        # table of results
        'section': 8,        # section cover
        'case': 9,           # table of case
        'last': 10,          # last slide
        'new': 1,            # blank slide for content
        # 'removal': (7, 9),  # (7, 27),  # slides to be removed [7, 27)
    },

    'case_prefixes': ['AP', 'AE', 'AVAM', 'URL', 'HA', 'TP', 'TC'],
    'other_prefixes': ['PA'],
    'bp_reports': 'POC*.pdf',
    # 'screenshot_files': '[^.]*Screenshot*.png',
    'other_files': '[!.]*.png',
    'other_files_exclude': ['throughput.png', 'traffic.png'],  # files to be excluded
    'image_files': '[!.]*.png',

    'job_dir': 'job-*',
    'cli_file': 'cli-[0-9]*.log',
    'ctx_file': 'ctx.json',
    'sta_file': 'sta-[0-9]*.json',
    # 'dp_files_list': ['dp0-0.png', 's[0-9]*dp[0-9]*-0.png'],
    'dp_files_list': ['dp-*.png'],
    # 'p_files_list': ['p-[0-9].png', 'p-[0-9][0-9].png'],    # grid of plots
    # 'p_files_list': ['p[0-9]-*.png', 'p[0-9][0-9]-*.png'],  # plots individually
    'p_files_list': [
        #'p*-activeTCPSessions.png',
        #'p*-activeUDPSessions.png',
        #'p*-allocatedSessions.png',
        'p*-allSessions.png',                  # tcp + udp
        #'p*-chassisPower.png',
        #
        'p*-connectionRate.png',
        #'p*-ethBytesReceived.png',
        #'p*-ethPacketsReceived.png',
        #'p*-ethPacketSizesAverage.png',       # bytes / packets
        #'p*-flow_ctrl.png',                   # dp usage
        #
        #'p*-logReceiverLogRate.png',
        'p*-packetRate.png',
        #'p*-sessionFilterCount.png'           # number of sessions that match filter `show session all filter count yes`
        #'p*-sessionTableUtil.png',
        #'p*-systemResourcesCpu.png',          # mp usage
        #
        'p*-systemResourcesCpuBusy.png',       # mp usage busy vs idle
        #'p*-systemResourcesCpuUsSy.png',      # mp usage us and sy only
        'p*-systemResourcesMemMiB.png',
        #'p*-throughputKbps.png',
        #'p*-vpnIPSecTunnels.png',
    ],

    'bp_sections': {
        'test_parameters': 'Test parameters',                                       # section 3.2
        'test_device': 'Test Device',                                               # section 5.7 for tester details
        # 'super_flow_data': 'Super Flow Data',                                     # section 7.9
        'super_flow_data_throughput': 'Super Flow Data Throughput',                 # section 7.29.5
        'super_flow_iterations': 'Super Flow Iterations',                           # section 7.11
        'transactions': 'Transactions',                                             # section 6.4.19
        'tcp_average_time_response_packet': 'TCP Average Time to Response Packet',  # section 7.29.27
        # 'tcp_average_time_to_open': 'TCP Average Time to Open',                     # section 7.26.21
        # 'tcp_average_time_to_close': 'TCP Average Time to Close',                   # section 7.26.23
    },
    'bp_section_re': r'^\d+(\.\d+)+\.',
    'bp_table_values_trim': (0.05, 0.05),  # remove the first 5% and the last 5%

    'pa_attrs': [
        'model',
        'sw-version',
        'app-version',
        'app-release-date',
        'sessions supported',
    ],

    'sta_metrics': {
        'allocatedSessions': 'Max sess captured',
        'connectionRate': 'Max CPS captured',
        'flow_ctrl': 'DP %',
        'flow_rate': 'CPS',
        'packetRate': 'Max PPS captured',
    },

    'result_columns': {
        'case': 'Test Case',
        'job': 'Dataset',
        'flow_ctrl': 'DP %',
        'throughput': 'Gbps',
        'flow_rate': 'CPS',
        'connectionRate': 'Max CPS\nCaptured',
        'allocatedSessions': 'Max Sessions\nCaptured',
        'packetRate': 'Max PPS\nCaptured',
        'supportedSessions': 'Sessions\nSupported',
    },

    'text': {
        'agenda': 'Agenda',
        'case': 'Test Case',
        'dp': 'DP Utilization',
        'others': 'References',
        'results': 'Test Result Summary',
        'util': 'Resources',
    },

    'agenda_items': [  # agenda slide from scratch not yet looking good
        'Overview',
        'Lab Setup', [
            'Hardware Requirements',
            'Topology',
            'Test Case Summary',
            'Test Environment',
            'Traffic Details',
        ],
        'Test Result Summary',
        'Test Cases',
    ],

    'version': '1.1',

    'verbose': True,
    'debug': False,
}
