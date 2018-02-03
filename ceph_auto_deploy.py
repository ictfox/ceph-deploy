#!/usr/bin/env python
# coding=utf-8

import sys
import getopt
import os
import re
import io
import threading
from ConfigParser import ConfigParser
config = ConfigParser()

class threading_do_parallel_cmd(threading.Thread):
    def __init__(self, cmd):
        threading.Thread.__init__(self)
        self._cmd = cmd

    def run(self):
        thread_name = threading.currentThread().getName()
        #print thread_name, self._cmd
        do_local_cmd(self._cmd)

def do_osds_parallel_cmd(sub_cmd, osds_list):
    threads = []
    for osds in osds_list:
        #print "osds: %s" % osds

        # Create ceph osd
        threads.append(threading_do_parallel_cmd(sub_cmd + osds))

    # Start all the threads
    for t in threads:
        t.start()

    # Waiting for all the threads to terminate
    for t in threads:
        t.join()

    return

def do_local_cmd(cmd):
    print "[CMD] %s" % cmd
    if conf_debug: return

    out = os.system(cmd)
    if out:
        print "Error code: %d" % out
        sys.exit(1)
    return

def do_local_cmd_with_return(cmd):
    print "Do command: %s" % cmd
    if conf_debug: return

    output_list = os.popen(cmd).readlines()
    return output_list

def do_remote_cmd(host, cmd):
    print "Do command: (%s) %s" % (host, cmd)
    if conf_debug: return

    out = os.system("ssh " + host + " " + cmd)
    if out:
        print "Error code: %d" % out
        sys.exit(1)
    return

def do_remote_cmd_with_return(host, cmd):
    print "Do command: (%s) %s" % (host, cmd)
    if conf_debug: return

    output_list = os.popen("ssh " + host + " " + cmd).readlines()
    return output_list

class Host:
    def __init__(self, hostname):
        self.hostname = hostname
        self.public_network = ""
        self.cluster_network = ""

    def set_network(self, public_network, cluster_network):
        self.public_network = public_network
        self.cluster_network = cluster_network

    def update_network_conf(self):
        if conf_debug: return

        conf = ConfigParser()
        conf.read('ceph.conf')
        if self.public_network:
            conf.set("global", "public network", self.public_network)
        if self.cluster_network:
            conf.set("global", "cluster network", self.cluster_network)
        with open('ceph.conf', 'wb') as cfgfile:
            conf.write(cfgfile)

class MON(Host):
    def __init__(self, hostname):
        Host.__init__(self, hostname)

    def __str__(self):
        return 'MON: {\n  hostname: %s,\n  public_network: %s,\n  cluster_network: %s\n}' % \
            (self.hostname, self.public_network, self.cluster_network)

    def add_mon(self):
        print "Adding MON: %s" % self.hostname
        self.update_network_conf()
        do_local_cmd("ceph-deploy mon add " + self.hostname)

class OSD(Host):
    def __init__(self, hostname):
        Host.__init__(self, hostname)
        self.dev_list = []
        self.path_list = []
        self.part_list = []
        self.journals = []
        self.num_osds = 0

    def __str__(self):
        return 'OSD: {\n  hostname: %s,\n' % self.hostname + \
            '  public_network: %s,\n' % self.public_network + \
            '  cluster_network: %s,\n' % self.cluster_network + \
            '  devices: %s,\n' % self.dev_list + \
            '  paths: %s,\n' % self.path_list + \
            '  partitions: %s\n}' % self.part_list

    def deploy(self):
        print "Deploying OSD: %s" % self.hostname
        self.update_network_conf()

        if self.journals:
            journals_str = ' '.join(self.journals)
            do_local_cmd("ceph-deploy disk zap " + journals_str)
        if self.dev_list:
            devs_str = ' '.join(self.dev_list)
            do_local_cmd("ceph-deploy --overwrite-conf osd prepare --zap-disk " + devs_str)
        if self.path_list:
            paths_str = ' '.join(self.path_list)
            do_local_cmd("ceph-deploy --overwrite-conf osd prepare " + paths_str)
            do_local_cmd("ceph-deploy osd activate " + paths_str)
        if self.part_list:
            print "partition deployment not supported now."


    # Set device list, should only be called once
    def set_dev_list(self, dev_list):
        self.dev_list = dev_list
        self.num_osds = self.num_osds + len(dev_list)
        # Parse the journal devices
        for dev in dev_list:
            # dev format: hostname:disk:journal
            tmp = dev.split(':')
            if len(tmp) == 3:
                journal = self.hostname+":"+tmp[2]
                self.journals.append(journal)
                # Deduplicate and sort
                self.journals = list(set(self.journals))
                self.journals.sort()

    # Set path list, should only be called once
    def set_path_list(self, path_list):
        self.path_list = path_list
        self.num_osds = self.num_osds + len(path_list)

    # Set partition list
    def set_part_list(self, part_list):
        self.part_list = part_list
        self.num_osds = self.num_osds + len(part_list)

class RGW(Host):
    def __init__(self, hostname):
        Host.__init__(self, hostname)

    def __str__(self):
        return 'RGW: {\n  hostname: %s,\n  public_network: %s,\n  cluster_network: %s\n}' % \
            (self.hostname, self.public_network, self.cluster_network)

    def deploy(self):
        print "Deploying RGW: %s" % self.hostname
        self.update_network_conf()
        do_local_cmd("ceph-deploy rgw create " + self.hostname)

def create_initial_monitors(mons_str):
    print "Creating initial MON(s): %s" % mons_str
    do_local_cmd("rm -rf ceph.*")
    do_local_cmd("ceph-deploy new " + mons_str)
    # Add user configuration to ceph.conf
    user_configure_ceph()
    do_local_cmd("ceph-deploy mon create-initial")

def parse_deploy_conf(cfile):
    # global mons, osds, rgws
    conf_data = {"mon":[], "osd":[], "rgw":[]}

    fhandle = open(cfile, 'r')
    raw_data = fhandle.read()
    fhandle.close()

    # Remove whitespaces in cfile so ConfigParser can parse it
    fdata = raw_data.replace("    ", "")
    config.readfp(io.BytesIO(fdata))

    section = "host-specific"

    # 1.Parse monitor hosts
    hosts = config.get(section, "mon_hosts")
    mon_hosts = [x.strip() for x in hosts.split(',')]
    mons = [MON(x) for x in mon_hosts]

    # 2.Parse OSD hosts
    hosts = config.get(section, "osd_hosts")
    osd_hosts = [x.strip() for x in hosts.split(',')]
    osds = []
    # Parse OSD devices/partitions/paths
    for host in osd_hosts:
        osd_dev_list = []
        osd_path_list = []
        osd_part_list = []
        osd = OSD(host)
        # Parse devices
        if config.has_option(section, 'osd.'+host+'.devs'):
            devs = config.get(section, 'osd.'+host+'.devs')
            dev_list = [x.strip() for x in devs.split(',')]
            for dev in dev_list:
                osd_dev = host+":"+dev
                osd_dev_list.append(osd_dev)
            osd.set_dev_list(osd_dev_list)
        # Parse paths
        if config.has_option(section, 'osd.'+host+'.paths'):
            paths = config.get(section, 'osd.'+host+'.paths')
            path_list = [x.strip() for x in paths.split(',')]
            for path in path_list:
                osd_path = host+":"+path
                osd_path_list.append(osd_path)
            osd.set_path_list(osd_path_list)
        # Parse partitions
        if config.has_option(section, 'osd.'+host+'.parts'):
            parts = config.get(section, 'osd.'+host+'.parts')
            part_list = [x.strip() for x in parts.split(',')]
            for part in part_list:
                osd_part = host+":"+part
                osd_part_list.append(osd_part)
            osd.set_part_list(osd_part_list)
        osds.append(osd)

    # 3.Parse RGW hosts
    if config.has_option(section, 'rgw_hosts'):
        hosts = config.get(section, "rgw_hosts")
        if hosts:
            rgw_hosts = [x.strip() for x in hosts.split(',')]
            rgws = [RGW(x) for x in rgw_hosts]
        else:
            rgws = []
    else:
        rgws = []

    # 4.Parse network settings
    # "public-network;cluster-network" : [host1, host2, host3],
    # "public-network;cluster-network" : [host4, host5]
    net_conf = re.compile(r"(1?\d\d?|2[0-4]\d|25[0-5])\.(1?\d\d?|2[0-4]\d|25[0-5])\."+
                          "(1?\d\d?|2[0-4]\d|25[0-5])\.(1?\d\d?|2[0-4]\d|25[0-5])/\d\d?;"+
                          "(1?\d\d?|2[0-4]\d|25[0-5])\.(1?\d\d?|2[0-4]\d|25[0-5])\."+
                          "(1?\d\d?|2[0-4]\d|25[0-5])\.(1?\d\d?|2[0-4]\d|25[0-5])/\d\d?$")
    options = config.options(section)
    for option in options:
        if re.match(net_conf, option) == None:
            continue
        tmp = [x.strip() for x in option.split(';')]
        public_network = tmp[0]
        cluster_network = tmp[1]
        hosts = config.get(section, option)
        host_set = set([x.strip() for x in hosts.split(',')])
        for mon in mons:
            if mon.hostname in host_set:
                mon.set_network(public_network, cluster_network)
        for osd in osds:
            if osd.hostname in host_set:
                osd.set_network(public_network, cluster_network)
        for rgw in rgws:
            if rgw.hostname in host_set:
                rgw.set_network(public_network, cluster_network)

    conf_data["mon"] = mons
    conf_data["osd"] = osds
    conf_data["rgw"] = rgws

    return conf_data


def get_osds_num():
    num = 0
    for osd in osds:
        num = num + osd.num_osds
    return nums

def usage(name):
    print "%s usage:" % name
    print "    python %s     run this script with default configuration" % name
    print "    -h, --help                          print help message"
    print "    -v, --version                       print script version"
    print "    -c [configure file]                 specify the configure file"
    print "    -p                                  just purge older ceph and ceph data"
    print "    -r                                  do ceph purge and ceph reinstall"
    print "    --just-deploy-osds                  just do deploy ceph osds"
    print "    --debug                             just print out the commands"

def version():
    print "version 2.0"

def get_suitable_pgnum(osds, pools, replicas):
    pgnum = get_osds_num() * 100 / (replicas * pools)
    loops = 0
    while (pgnum != 0):
        pgnum = pgnum >> 1
        loops = loops + 1
    #print "loops = %d" % loops
    pgnum = 2 ** loops
    return pgnum

def install_ceph_with_cmd(ceph_hosts):
    # Reinstall ceph on hosts with multiple threading
    threads = []
    for host in ceph_hosts:
        threads.append(threading_do_parallel_cmd("ssh " + host + " '" + install_ceph_cmd + "'"))

    # Start all the threads
    for t in threads:
        t.start()

    # Waiting for all the threads to terminate
    for t in threads:
        t.join()

def purge_older_ceph(ceph_hosts, need_confirm):
    if need_confirm:
        print "CAUTION: we are about to purge ceph on these hosts:"
        for host in ceph_hosts:
            print host
        confirm = raw_input("\nConfirm? y/n: ")
    else:
        confirm = "y"

    if confirm != "y":
        print "Not confirmed, exit!"
        sys.exit(1)

    hosts_str = ' '.join(ceph_hosts)
    do_local_cmd("ceph-deploy purge " + hosts_str)
    do_local_cmd("ceph-deploy purgedata " + hosts_str)

    return

def user_configure_ceph():
    do_local_cmd("sed -i 's/cephx/none/g' ceph.conf")
    do_local_cmd("sed -e '1d' " + conf_ceph_file + " >> ceph.conf")
    conf = ConfigParser()
    conf.read('ceph.conf')
    # Remove our customer sections
    conf.remove_section("host-specific")
    # Get RGW host list from deploy.conf and add rgw_host to client section in ceph.conf
    if config.has_option("host-specific", "rgw_hosts"):
        hosts = config.get("host-specific", "rgw_hosts")
        if hosts:
            conf.set("client", "rgw_host", hosts)

    with open('ceph.conf', 'wb') as cfgfile:
        conf.write(cfgfile)
    return

def ceph_deploy(mons, osds, rgws, need_confirm):
    if need_confirm:
        print "CAUTION: we are about to deploy ceph on these hosts:"
        print "\nMONs:"
        for mon in mons:
            print mon.hostname
        print "\nOSDs:"
        for osd in osds:
            print osd.hostname
        print "\nRGWs:"
        for rgw in rgws:
            print rgw.hostname
        confirm = raw_input("\nConfirm? y/n: ")
    else:
        confirm = "y"

    if confirm != "y":
        print "Not confirmed, exit!"
        sys.exit(1)

    # Do not deploy monitor if option --just-deploy-osds set
    if not conf_jdo:
        # Deploy MONs
        mons_str = ""
        for mon in mons:
            mons_str = mons_str + ' ' + mon.hostname
        create_initial_monitors(mons_str)
    # Deploy OSDs
    for osd in osds:
        osd.deploy()
    # Deploy RGWs
    if not conf_jdo:
        for rgw in rgws:
            rgw.deploy()

    return

def do_ceph_deploy_main(purge_reinstall):
    print "conf_ceph_file = %s" % conf_ceph_file
    if not os.path.exists(conf_ceph_file):
        print "Error could NOT find configure file: %s" % conf_ceph_file
        sys.exit(1)

    # Parse deploy configuration
    conf_data = parse_deploy_conf(conf_ceph_file)

    # Do Ceph purge or reinstall requests
    hosts = []
    if not conf_jdo:
        for host in conf_data["mon"]:
            if host.hostname not in hosts:
                hosts.append(host.hostname)
        for host in conf_data["rgw"]:
            if host.hostname not in hosts:
                hosts.append(host.hostname)

    for host in conf_data["osd"]:
        if host.hostname not in hosts:
            hosts.append(host.hostname)

    if purge_reinstall == "purge":
        purge_older_ceph(hosts, need_confirm)
    elif purge_reinstall == "reinstall":
        purge_older_ceph(hosts, need_confirm)
        install_ceph_with_cmd(hosts)
    else:
        ceph_deploy(conf_data["mon"], conf_data["osd"],
                    conf_data["rgw"], need_confirm)
    return


def main(argv):
    global conf_debug, conf_ceph_file, conf_jdo, need_confirm

    try:
        opts, args = getopt.getopt(argv[1:], 'hvprc:y', ['help', 'version', 'debug', 'just-deploy-osds'])
    except getopt.GetoptError, err:
        print str(err)
        usage(argv[0])
        sys.exit(2)

    purge_reinstall = ""
    for op, value in opts:
        if op in ('-h', '--help'):
            usage(argv[0])
            sys.exit(1)
        elif op in ('-v', '--version'):
            version()
            sys.exit(0)
        elif op == '-c':
            conf_ceph_file = value
        elif op == '-p':
            purge_reinstall = "purge"
        elif op == '-r':
            purge_reinstall = "reinstall"
        elif op == '-y':
            need_confirm = False
        elif op in ('--debug'):
            conf_debug = True
            need_confirm = False
        elif op in ('--just-deploy-osds'):
            conf_jdo = True
        else:
            usage(argv[0])
            sys.exit(1)

    # Main entrance of ceph deploy
    do_ceph_deploy_main(purge_reinstall)

# Configuration of this script
conf_debug = False
conf_jdo = False
conf_ceph_file = "deploy.conf"
need_confirm = True
install_ceph_cmd = "apt-get install -y ceph radosgw ceph-mds"

if __name__ == '__main__':
    main(sys.argv)

