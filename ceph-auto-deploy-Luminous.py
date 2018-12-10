#!/usr/bin/env python
# coding=utf-8

import sys
import getopt
import json
import os, re, io, time
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
    print "[CMD] %s" % cmd
    if conf_debug: return

    output_list = os.popen(cmd).readlines()
    return output_list

def do_remote_cmd(host, cmd):
    print "[CMD] ssh %s %s" % (host, cmd)
    if conf_debug: return

    out = os.system("ssh " + host + " " + cmd)
    if out:
        print "Error code: %d" % out
        sys.exit(1)
    return

def do_remote_cmd_with_return(host, cmd):
    print "[CMD] ssh %s %s" % (host, cmd)
    if conf_debug: return [""]

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
        print "\nAdding %s" % self
        self.update_network_conf()
        do_local_cmd("ceph-deploy mon add " + self.hostname)

class OSD(Host):
    def __init__(self, hostname):
        Host.__init__(self, hostname)
        self.osd_type = "bluestore"
        self.data_dev = ""
        self.wal_dev = ""
        self.db_dev = ""
        self.jnl_dev = ""

    def __str__(self):
        return 'OSD: {\n  hostname: %s,\n' % self.hostname + \
            '  public_network: %s,\n' % self.public_network + \
            '  cluster_network: %s,\n' % self.cluster_network + \
            '  data: %s,\n' % self.data_dev + \
            '  wal_dev: %s,\n' % self.wal_dev + \
            '  db_dev: %s,\n' % self.db_dev + \
            '  journal: %s}\n' % self.jnl_dev

    def is_filestore(self):
        return self.osd_type == "filestore"

    def is_bluestore(self):
        return self.osd_type == "bluestore"

    def deploy(self):
        print "\nDeploying %s" % self
        self.update_network_conf()

        if self.data_dev == "":
            print "osd data device is null!"
            return

        disk_zap_cmd = "ceph-deploy disk zap " + self.hostname + " " + self.data_dev
        osd_create_cmd = "ceph-deploy --overwrite-conf osd create " + self.hostname + " --data " + self.data_dev
        if self.wal_dev != "":
            osd_create_cmd += " --block-wal "
            osd_create_cmd += self.wal_dev
        if self.db_dev != "":
            osd_create_cmd += " --block-db "
            osd_create_cmd += self.db_dev

        do_local_cmd(disk_zap_cmd)
        do_local_cmd(osd_create_cmd)

    # Set devices, should only be called once
    def set_devs(self, devs):
        # devs format: data_dev:jnl_dev:db_dev:wal_dev
        dev_list = devs.split(':')
        self.data_dev = dev_list[0]
        if len(dev_list) >= 2:
            if self.is_filestore():
                self.jnl_dev = dev_list[1]
            else:
                self.wal_dev = dev_list[1]
        if len(dev_list) >= 3:
            if self.is_bluestore():
                self.db_dev = dev_list[2]

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
        print "\nDeploying %s" % self
        self.update_network_conf()
        do_local_cmd("ceph-deploy rgw create " + self.hostname)

class MDS(Host):
    def __init__(self, hostname):
        Host.__init__(self, hostname)

    def __str__(self):
        return 'MDS: {\n  hostname: %s,\n  public_network: %s,\n  cluster_network: %s\n}' % \
            (self.hostname, self.public_network, self.cluster_network)

    def deploy(self):
        print "\nDeploying %s" % self
        self.update_network_conf()
        do_local_cmd("ceph-deploy mds create " + self.hostname + ":" + self.hostname)

# One Host which could communication with Ceph Cluster
class CephHost:
    def __init__(self, name):
        self.host_name = name   # host name

    def __str__(self):
        return 'CephHost: {\n  Name: %s\n}' % (self.name)

    def ceph_cmd(self, cmd):
        do_remote_cmd(self.host_name, cmd)

    def ceph_cmd_with_return(self, cmd):
        return do_remote_cmd_with_return(self.host_name, cmd)

# Only support type=replicated crush rule now
class CrushRule(CephHost):
    def __init__(self, host, type, rclass):
        CephHost.__init__(self, host)
        self.type = type            # rule type
        self.rule_class = rclass    # rule class
        self.osd_count = 0          # osd count related to the class
        self.name = type + "_rule_" + rclass    # name

    def __str__(self):
        return 'CrushRule: {\n  Name: %s,\n  class: %s\n}' % \
            (self.name, self.rule_class)

    def related_osds(self):
        return self.osd_count

    def set_related_osds(self):
        output_list = self.ceph_cmd_with_return("ceph osd crush class ls-osd "\
                                                + self.rule_class + " | wc -l")
        if conf_debug: return
        if output_list:
            self.osd_count = int(output_list[0])
        else:
            print "\033[1;41mGet ceph class %s related osds error!\033[0m" % self.rule_class
        return

    def cluster_has_rule_class(self):
        output_list = self.ceph_cmd_with_return("ceph osd crush class ls | grep "
                                                            + self.rule_class)
        if output_list:
            return True
        else:
            return False

    def match_rule_class(self, request):
        if self.rule_class == request:
            return True
        else:
            return False

    def deploy(self):
        print "\nCreating %s" % self
        self.set_related_osds()
        self.ceph_cmd("ceph osd crush rule create-" + self.type\
                + " " + self.name + " default host " + self.rule_class)

class Pool(CephHost):
    def __init__(self, host, name, crule):
        CephHost.__init__(self, host)
        self.name = name            # name
        self.pg_num = 64            # default pg number
        self.application = ""       # pool application
        self.crush_rule = crule     # crush rule

    def __str__(self):
        return 'Pool: {\n  Name: %s,\n  pg number: %s,\n  crush rule: %s\n}' % \
            (self.name, str(self.pg_num), self.crush_rule)

    def set_suitable_pg_num(self):
        if self.crush_rule:
            replicas = 2
            crush_rule_pools = 2
            osd_count = self.crush_rule.related_osds()
            pgnum = osd_count * 100 / (replicas * crush_rule_pools)
            loops = 0
            while (pgnum != 0):
                pgnum = pgnum >> 1
                loops += 1
            pgnum = 2 ** (loops - 1)
            if pgnum > self.pg_num:
                self.pg_num = pgnum
        return

    def get_application(self):
        return self.application

    def enable_application(self, app):
        self.application = app
        self.ceph_cmd("ceph osd pool application enable " + self.name + " " + self.application)

    def deploy(self):
        print "\nCreating %s" % self
        self.set_suitable_pg_num()
        cmd = "ceph osd pool create " + self.name + " " + str(self.pg_num) + " " + str(self.pg_num)
        if self.crush_rule:
            cmd = cmd + " " + self.crush_rule.name
        self.ceph_cmd(cmd)

class CephFS(CephHost):
    def __init__(self, host, name, mdpool, dpools, mmds):
        CephHost.__init__(self, host)
        self.name = name            # name
        self.mdata_pool = mdpool    # metadata pool
        self.data_pools = dpools    # data pools list
        self.max_mds = mmds         # max MDSs

    def __str__(self):
        dpool_str = ""
        for p in self.data_pools:
            dpool_str = dpool_str + p.name + ","
        return 'CephFS: {\n  Name: %s,\n  metadata pool: %s,\n  data pools: %s - %s\n  max mds: %s\n}' % \
            (self.name, self.mdata_pool.name, len(self.data_pools), dpool_str, self.max_mds)

    def deploy(self):
        print "\nCreating %s" % self
        self.ceph_cmd("ceph fs new " + self.name + " " + self.mdata_pool.name + " " + self.data_pools[0].name)
        if len(self.data_pools) > 1:
            for p in self.data_pools[1:]:
                self.ceph_cmd("ceph fs add_data_pool " + self.name + " " + p.name)
        if self.max_mds > 1:
            self.ceph_cmd("ceph fs set " + self.name + " max_mds " + str(self.max_mds))


def create_initial_monitors(mons):
    mons_str = ""
    for mon in mons:
        mons_str = mons_str + ' ' + mon.hostname

    print "Creating initial MON(s): %s" % mons_str
    do_local_cmd("rm -rf ceph.*")
    do_local_cmd("ceph-deploy new" + mons_str)
    # Add user configuration to ceph.conf
    user_configure_ceph()
    do_local_cmd("ceph-deploy --overwrite-conf mon create" + mons_str)

    # Retry and waiting for all monitors in quorum
    cmd = "ceph --connect-timeout 10 --admin-daemon /var/run/ceph/ceph-mon.*.asok mon_status --format json"
    mons_ok = False
    counter = 0
    while counter < 10:
        counter += 1
        do_local_cmd("sleep 5")
        output_list = do_remote_cmd_with_return(mons[0].hostname, cmd)
        if conf_debug:
            mons_ok = True
            break
        if output_list:
            mon_status = json.loads(output_list[0])
            if len(mon_status["quorum"]) != len(mons):
                print "Not all montiors in quorum now %s" % mon_status["quorum"]
                continue
            else:
                print "All montiors in quorum now %s" % mon_status["quorum"]
                mons_ok = True
                break
        else:
            print "Failed to get monitor status from %s" % mons[0].hostname
            continue
    if mons_ok == False:
        print "Failed to wait all monitors in quorum!"
        sys.exit(1)

def gatherkeys_then_push_config(ceph_hosts):
    hosts_str = ' '.join(ceph_hosts)
    do_local_cmd("ceph-deploy gatherkeys " + hosts_str)
    do_local_cmd("ceph-deploy admin " + hosts_str)

def create_managers(mons):
    mons_str = ""
    for mon in mons:
        mons_str = mons_str + ' ' + mon.hostname
    do_local_cmd("ceph-deploy mgr create" + mons_str)

def tuple_to_dictionary(t):
    d = {}
    for k, v in t:
        d[k] = v
    return d

def parse_deploy_conf(cfile):
    # global mons, osds, rgws
    conf_data = {"mon":[], "osd":[], "rgw":[], "mds":[]}

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
        osd_part_list = []
        # Parse devices
        if config.has_option(section, 'osd.'+host+'.devs'):
            host_devs = config.get(section, 'osd.'+host+'.devs')
            devs_list = [x.strip() for x in host_devs.split(',')]
            for devs in devs_list:
                osd = OSD(host)
                osd.set_devs(devs)
                osds.append(osd)

        # Parse partitions
        if config.has_option(section, 'osd.'+host+'.parts'):
            host_parts = config.get(section, 'osd.'+host+'.parts')
            parts_list = [x.strip() for x in host_parts.split(',')]
            for parts in parts_list:
                osd = OSD(host)
                osd.set_part_list(parts)
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

    # 4.Parse MDS hosts
    if config.has_option(section, 'mds_hosts'):
        hosts = config.get(section, "mds_hosts")
        if hosts:
            mds_hosts = [x.strip() for x in hosts.split(',')]
            mdss = [MDS(x) for x in mds_hosts]
        else:
            mdss = []
    else:
        mdss = []


    # 5.Parse network settings
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
    conf_data["mds"] = mdss

    # Collect configurations to dictionary
    conf_data["crush"] = tuple_to_dictionary(config.items("crush"))
    conf_data["pools"] = tuple_to_dictionary(config.items("pools"))
    conf_data["cephfs"] = tuple_to_dictionary(config.items("cephfs"))

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
    # Get ceph install command
    output_list = do_local_cmd_with_return('cat /etc/os-release | grep -w ID')
    if output_list:
        os_info = output_list[0]
        if 'ubuntu' in os_info:
            install_ceph_cmd = "apt-get install -y ceph radosgw ceph-mds"
        elif 'centos' in os_info:
            #install_ceph_cmd = "yum install -y ceph ceph-radosgw"
            install_ceph_cmd = "yum install -y ceph"
        else:
            print "Unkown OS: %s" % os_info
            sys.exit(1)
    else:
        print "Get ceph install command error!"
        sys.exit(1)

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

    # Cleanup vgs created by ceph when use bluestore
    cmd = "vgs | grep ceph | awk '{print $1}'"
    for host in ceph_hosts:
        output_list = do_remote_cmd_with_return(host, cmd)
        if conf_debug: continue
        if output_list:
            for vg in output_list:
                do_remote_cmd(host, "vgremove -f " + vg)
        else:
            print "Failed to get vgs from %s" % host
    return

def user_configure_ceph():
    do_local_cmd("sed -e '1d' " + conf_ceph_file + " >> ceph.conf")
    do_local_cmd("sed -ie '/#/d' ceph.conf")
    do_local_cmd("sed -i '/host-specific/,$d' ceph.conf")
    conf = ConfigParser()
    conf.read('ceph.conf')
    # Remove our customer sections
    conf.remove_section("host-specific")
    # Get RGW host list from deploy.conf and add rgw_host to client section in ceph.conf
    if config.has_option("host-specific", "rgw_hosts"):
        hosts = config.get("host-specific", "rgw_hosts")
        if hosts:
            if not conf_debug:
                conf.set("client", "rgw_host", hosts)

    with open('ceph.conf', 'wb') as cfgfile:
        conf.write(cfgfile)
    return

# Retry and waiting Ceph Cluster to be ready
def wait_ceph_cluster_ready(host):
    cmd = "ceph --connect-timeout 10 status --format json | grep status"
    ceph_health = "HEALTH_OK"
    counter = 0
    while counter < 10:
        counter += 1
        do_local_cmd("sleep 5")
        output_list = do_remote_cmd_with_return(host, cmd)
        if conf_debug: break
        if output_list:
            ceph_status = json.loads(output_list[0])
            ceph_health = ceph_status["health"]["status"]
            if ceph_health != "HEALTH_OK":
                print "Ceph health: %s" % ceph_health
                continue
            else:
                break
        else:
            print "Failed to get Ceph status from %s" % host
            ceph_health = "HEALTH_ERR"
            continue

    if ceph_health == "HEALTH_ERR":
        print "Ceph health still be HEALTH_ERR!"
        sys.exit(1)
    return

def create_crush_rules(host, classes):
    crules = [CrushRule(host, "replicated", c) for c in classes]
    for cr in crules[:]:
        if cr.cluster_has_rule_class():
            cr.deploy()
        else:
            print "\033[1;33mCluster DOESN'T have class '%s'\033[0m" % cr.rule_class
            crules.remove(cr)
    return crules

# Create pools
def create_pools(host, pools, crules):
    npools = []
    for poolstr in pools:
        pool_cr = None
        pool = poolstr.split(':')
        for cr in crules:
            if cr.match_rule_class(pool[1]):
                pool_cr = cr
        if pool_cr == None:
            print "\033[1;35mPool '%s' will use default crush rule "\
                    "as we DOESN't have class %s\033[0m" % (pool[0], pool[1])
        npool = Pool(host, pool[0], pool_cr)
        npool.deploy()
        npools.append(npool)

    return npools

def ceph_deploy(conf_data, need_confirm):
    mons = conf_data["mon"]
    osds = conf_data["osd"]
    rgws = conf_data["rgw"]
    mdss = conf_data["mds"]
    ceph_hosts = get_all_ceph_hosts(conf_data)

    if need_confirm:
        print "CAUTION: we are about to deploy ceph on these hosts:"
        print "\nMONs:"
        for mon in mons:
            print mon.hostname
        print "\nOSDs:"
        for osd in osds:
            print osd.hostname, osd.data_dev, osd.wal_dev, osd.db_dev
        print "\nRGWs:"
        for rgw in rgws:
            print rgw.hostname
        print "\nMDSs:"
        for mds in mdss:
            print mds.hostname
        if conf_data.has_key("crush"):
            print "\ncrush:\n%s" % conf_data["crush"]
        if conf_data.has_key("pools"):
            print "\npools:\n%s" % conf_data["pools"]
        if conf_data.has_key("cephfs"):
            print "\ncephfs:\n%s" % conf_data["cephfs"]
        confirm = raw_input("\nConfirm? y/n: ")
    else:
        confirm = "y"

    if confirm != "y":
        print "Not confirmed, exit!"
        sys.exit(1)

    # Do not deploy monitor if option --just-deploy-osds set
    if not conf_jdo:
        # Deploy Mons and Mgrs
        create_initial_monitors(mons)
        gatherkeys_then_push_config(ceph_hosts)
        create_managers(mons)

    # Deploy OSDs
    for osd in osds:
        osd.deploy()

    if conf_jdo:
        return

    # Disable cephx after all done
    do_local_cmd("sed -i 's/cephx/none/g' ceph.conf")
    hosts_str = ' '.join(ceph_hosts)
    do_local_cmd("ceph-deploy --overwrite-conf admin " + hosts_str)
    for host in ceph_hosts:
        do_remote_cmd(host, "'systemctl restart ceph.target'")
    wait_ceph_cluster_ready(ceph_hosts[0])

    # Deploy RGWs, MDSs
    for rgw in rgws:
        rgw.deploy()
    for mds in mdss:
        mds.deploy()

    # Init one ceph host and wait ceph cluster ready
    host = ceph_hosts[0]
    wait_ceph_cluster_ready(host)

    # Create crush rules according to specified class
    # Only support hdd/ssd class NOW!
    crule_class = [x.strip() for x in conf_data["crush"]["rules"].split(',')]
    crush_rules = create_crush_rules(host, crule_class)

    # Deploy rbd pools ["name:class", ...]
    # Now we only need one RBD pool
    rpools = [x.strip() for x in conf_data["pools"]["rbd"].split(',')]
    rbd_pools = create_pools(host, rpools, crush_rules)
    for pool in rbd_pools:
        pool.enable_application("rbd")

    # Deploy one cephfs
    fs_name = conf_data["cephfs"]["name"]
    max_mds = int(conf_data["cephfs"]["max_mds"])
    if max_mds >= len(mdss):
        max_mds = len(mdss) - 1
    fspools = [x.strip() for x in conf_data["cephfs"]["mdata_pool"].split(',')]
    fspools.extend([x.strip() for x in conf_data["cephfs"]["data_pools"].split(',')])
    cephfs_pools = create_pools(host, fspools, crush_rules)
    cephfs = CephFS(host, fs_name, cephfs_pools[0], cephfs_pools[1:], max_mds)
    cephfs.deploy()

    # Adjust crush tunables to hammer as we now use 4.4.x kernel
    CephHost(host).ceph_cmd("ceph osd crush tunables hammer")

    return

def get_all_ceph_hosts(conf_data):
    hosts = []
    if not conf_jdo:
        for host in conf_data["mon"]:
            if host.hostname not in hosts:
                hosts.append(host.hostname)
        for host in conf_data["rgw"]:
            if host.hostname not in hosts:
                hosts.append(host.hostname)
        for host in conf_data["mds"]:
            if host.hostname not in hosts:
                hosts.append(host.hostname)

    for host in conf_data["osd"]:
        if host.hostname not in hosts:
            hosts.append(host.hostname)

    return hosts

def do_ceph_deploy_main(purge_reinstall):
    print "conf_ceph_file = %s" % conf_ceph_file
    if not os.path.exists(conf_ceph_file):
        print "Error could NOT find configure file: %s" % conf_ceph_file
        sys.exit(1)

    # Parse deploy configuration
    conf_data = parse_deploy_conf(conf_ceph_file)

    # Do Ceph purge or reinstall requests
    ceph_hosts = get_all_ceph_hosts(conf_data)
    if purge_reinstall == "purge":
        purge_older_ceph(ceph_hosts, need_confirm)
    elif purge_reinstall == "reinstall":
        purge_older_ceph(ceph_hosts, need_confirm)
        install_ceph_with_cmd(ceph_hosts)
    else:
        ceph_deploy(conf_data, need_confirm)
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
conf_ceph_file = "deploy-Luminous.conf"
need_confirm = True

if __name__ == '__main__':
    main(sys.argv)

