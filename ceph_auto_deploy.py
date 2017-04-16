#!/usr/bin/env python
# coding=utf-8

import sys
import getopt
import os
import re
import json
import platform
import pdb

import threading
import time

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
    print "Do command: %s" % cmd
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

def get_conf_json_data(cfile):
    fhandle = open(cfile, 'r')
    fdata = fhandle.readlines()
    fhandle.close()

    json_data = {"mon": {}, "osd": {}, "mds": {}, "client": {}, "rgw": {}}
    index = 0
    for line in fdata:
        index = index + 1
        #print line.strip()
        if re.search(r'\[mon\]', line, re.M|re.I):
            hosts = re.split('=', fdata[index])
            json_hosts = {hosts[0].strip() : hosts[1].strip()}
            json_data["mon"] = json_hosts
        if re.search(r'\[osd\]', line, re.M|re.I):
            hosts = re.split('=', fdata[index])
            json_hosts = {hosts[0].strip() : hosts[1].strip()}
            json_data["osd"] = json_hosts
        elif re.search(r'osd\.', line, re.M|re.I):
            tmp = re.split('[.]', line.strip())
            osd_host = tmp[1]
            #print "osd host: %s" % osd_host
            try:
                json_osd = json_data["osd"]
            except Exception, err:
                json_data["osd"] = {}
                json_osd = json_data["osd"]
            devs = re.split('=', tmp[2])
            #print "devs: %s" % devs
            json_devs = {devs[0].strip() : devs[1].strip()}
            json_osd[osd_host] = json_devs
        elif re.search(r'client\.(images|volumes|cinder)', line, re.M|re.I):
            tmp = re.split('[\[\]]', line.strip())
            client = tmp[1]
            try:
                json_client = json_data["client"]
            except Exception, err:
                json_data["client"] = {}
                json_client = json_data["client"]
            keyring = re.split('=', fdata[index])
            json_keyring = {keyring[0].strip() : keyring[1].strip()}
            json_client[client] = json_keyring
        elif re.search(r'\[rgw\]', line, re.M|re.I):
            hosts = re.split('=', fdata[index])
            json_hosts = {hosts[0].strip() : hosts[1].strip()}
            json_data["rgw"] = json_hosts

    #print "json_data: %s" % json_data
    return json_data

def get_conf_monitors(jd):
    tmp = ''.join(jd["hosts"].split())
    hosts = re.split(',', tmp)
    return hosts

def get_conf_host_osds(jd):
    host_osds = {"devs": {}, "parts": {}, "paths": {}}
    host_osds_devs = []
    host_osds_parts = []
    host_osds_paths = []

    tmp = ''.join(jd["hosts"].split())
    hosts = re.split(',', tmp)
    for host in hosts:
        osds_devs = ""
        osds_parts = ""
        osds_paths = ""
        if host == "": continue
        if jd[host].has_key("devs"):
            tmp = ''.join(jd[host]["devs"].split())
            devs = re.split(',', tmp)
            #print "%s: %s" %(host, devs)
            # Parse disks and partitions
            for dev in devs:
                tmp = re.split('[:/]', dev)
                if re.match('^[a-z]+[0-9]+$', tmp[2]):
                    osds_parts = osds_parts + host + ":" + dev + " "
                else:
                    osds_devs = osds_devs + host + ":" + dev + " "
        if jd[host].has_key("paths"):
            # Parse paths
            tmp = ''.join(jd[host]["paths"].split())
            paths = re.split(',', tmp)
            #print "%s: %s" %(host, paths)
            for path in paths:
                tmp = re.split('[:/]', path)
                osds_paths = osds_paths + host + ":" + path + " "

        #print "osds_devs: %s" % osds_devs
        #print "osds_parts: %s" % osds_parts
        #print "osds_paths: %s" % osds_paths
        if osds_devs != "":
            host_osds_devs.append(osds_devs.strip())
        if osds_parts != "":
            host_osds_parts.append(osds_parts.strip())
        if osds_paths != "":
            host_osds_paths.append(osds_paths.strip())

    host_osds["devs"] = host_osds_devs
    host_osds["parts"] = host_osds_parts
    host_osds["paths"] = host_osds_paths
    return host_osds

def get_conf_mdss(jd):
    if not jd:
        print "no mds configured in configure file"
        return

    return

def get_conf_rgws(jd):
    if not jd:
        print "no rgw configured in configure file"
        return
    if jd.has_key("hosts"):
        tmp = ''.join(jd["hosts"].split())
        hosts = re.split(',', tmp)
        return hosts
    return

def get_osds_num(osds_list):
    nums = 0
    for osds in osds_list["devs"]:
        nums = nums + len(re.split('\s', osds))
    for osds in osds_list["parts"]:
        nums = nums + len(re.split('\s', osds))
    print "nums: %d" % nums
    return nums

def init_conf_keyrings(jd, ceph_hosts):
    if not jd:
        print "no keyring configured in configure file"
        return

    conf_ceph_hosts = just_get_conf_hosts(ceph_hosts)
    #print "jd: %s" % jd
    for keyring in jd:
        kr_file = jd[keyring]["keyring"]

        do_local_cmd("ceph-authtool --create-keyring " + kr_file)
        do_local_cmd("ceph-authtool " + kr_file + " -n " + keyring + " --gen-key")
        do_local_cmd("ceph-authtool " + kr_file + " -n " + keyring + " --cap osd 'allow *' --cap mon 'allow rw' --cap mds 'allow r'")
        do_local_cmd("ceph auth add " + keyring + " -i " + kr_file)

        # Copy keyring files to all hosts
        for host in conf_ceph_hosts:
            do_local_cmd("scp " + kr_file + " " + host + ":" + kr_file)

    return

def usage(name):
    print "%s usage:" % name
    print "    python %s     run this script with default configuration" % name
    print "    -h, --help                          print help message"
    print "    -v, --version                       print script version"
    print "    -c [configure file]                 specify the configure file"
    print "    -d [ceph deb packages dir]          specify the ceph deb packages directory"
    print "    -j [osd journal path]               specify the osd journal file path"
    print "    -o [osd_host:osd_host:...]          just deploy the osds on this hosts"
    print "    -p                                  just purge older ceph and ceph data"
    print "    -r                                  do ceph purge and ceph reinstall"
    print "    --just-deploy-osds                  just do deploy ceph osds"
    print "    --debug                             just print out the commands"

def version():
    print "version 1.0"

def get_suitable_pgnum(osds, pools, replicas):
    pgnum = get_osds_num(osds) * 100 / (replicas * pools)
    loops = 0
    while (pgnum != 0):
        pgnum = pgnum >> 1
        loops = loops + 1
    #print "loops = %d" % loops
    pgnum = 2 ** loops
    return pgnum

def clear_conf_jnl_data(hosts):
    for host in hosts:
        do_remote_cmd(host, "mkdir -p " + conf_jnl_path)
        do_remote_cmd(host, "rm -rf " + conf_jnl_path + "/osd*")
        do_remote_cmd(host, "rm -rf " + conf_jnl_path + "/*journal")
    return

def purge_older_ceph(hosts):
    conf_hosts_list = just_get_conf_hosts(hosts)

    # Check which host need purge ceph
    print "purge hosts: %s" % conf_hosts_list
    hosts_str = ' '.join(conf_hosts_list)
    do_local_cmd("ceph-deploy purge " + hosts_str)
    do_local_cmd("ceph-deploy purgedata " + hosts_str)

    if conf_jnl_path != "":
        clear_conf_jnl_data(conf_hosts_list)

    return

def install_ceph_with_pkgs(hosts):
    conf_hosts_list = just_get_conf_hosts(hosts)

    # Check ceph package directory and do prepare.sh if needed
    for host in conf_hosts_list:
        output_list = do_remote_cmd_with_return(host, "'ls " + conf_ceph_pkg_dir + "* | grep prepare.sh'")
        if output_list:
            continue

        ceph_pkg_tar_file = os.path.basename(conf_ceph_pkg_dir) + ".tar.gz"
        output_list = do_remote_cmd_with_return(host, "'ls " + conf_ceph_pkg_dir + ".tar.gz'")
        if conf_debug or output_list:
            do_remote_cmd(host, "'cd " + os.path.dirname(conf_ceph_pkg_dir) + "; tar -zxf " + ceph_pkg_tar_file + "'")
            do_remote_cmd(host, "'cd " + conf_ceph_pkg_dir + "; bash prepare.sh'")
        else:
            print "Could not find ceph deb packages in %s" % conf_ceph_pkg_dir
            sys.exit(1)

    # Reinstall ceph on hosts with multiple threading
    threads = []
    for host in conf_hosts_list:
        threads.append(threading_do_parallel_cmd("ssh " + host + " 'cd " + conf_ceph_pkg_dir + "; bash install.sh'"))

    # Start all the threads
    for t in threads:
        t.start()

    # Waiting for all the threads to terminate
    for t in threads:
        t.join()

    return

def install_ceph_with_cmd(hosts):
    # Reinstall ceph on hosts with multiple threading
    threads = []
    for host in just_get_conf_hosts(hosts):
        threads.append(threading_do_parallel_cmd("ssh " + host + " '" + install_ceph_cmd + "'"))

    # Start all the threads
    for t in threads:
        t.start()

    # Waiting for all the threads to terminate
    for t in threads:
        t.join()

    return

def user_configure_ceph():
    do_local_cmd("sed -i 's/cephx/none/g' ceph.conf")
    do_local_cmd("sed -i '2,$s/^/    /g' ceph.conf")
    do_local_cmd("sed -e '1d' " + conf_ceph_file + " >> ceph.conf")
    do_local_cmd("sed -i 's/\/osd-journal-path/" + conf_jnl_path.replace('/', '\/') + "/g' ceph.conf")
    return

osd_num = 0
def append_jnl_path_with_osdid(osd_devs_path):
    global osd_num
    jnl_path = conf_jnl_path + "/osd" + str(osd_num)
    osd_num = osd_num + 1

    osd_host = re.split(':', osd_devs_path)[0]
    do_remote_cmd(osd_host, "mkdir -p " + jnl_path)

    return osd_devs_path + ":" + jnl_path + "/journal"

def append_jnl_path_with_devs(osd_devs_path):
    dev_basename = os.path.basename(re.split(':', osd_devs_path)[1])
    return osd_devs_path + ":" + conf_jnl_path + "/" + dev_basename + "-journal"

def ceph_deploy_osd_with_journal(cmd, osds_list):
    print "Deploy osd with journal path: %s" % conf_jnl_path
    osds_list_with_jnl = []
    for osds in osds_list:
        if conf_journal_with_osdid:
            osdlist = map(append_jnl_path_with_osdid, re.split(' ', osds))
            # Create ceph osd
            do_local_cmd(cmd + ' '.join(osdlist))
        else:
            osdlist = map(append_jnl_path_with_devs, re.split(' ', osds))
            osds_list_with_jnl.append(' '.join(osdlist))
            if not conf_do_osd_deploy_parallel:
                do_local_cmd(cmd + ' '.join(osdlist))

    # Do parallel deploy ceph osd if not configure journal with osdid
    if conf_do_osd_deploy_parallel and (not conf_journal_with_osdid):
        do_osds_parallel_cmd(cmd, osds_list_with_jnl)

    return

def ceph_deploy_osd(cmd, osds_list):
    if conf_jnl_path != "":
        ceph_deploy_osd_with_journal(cmd, osds_list)
        return

    # Without journal path configured
    if conf_do_osd_deploy_parallel:
        do_osds_parallel_cmd(cmd, osds_list)
    else:
        for osds in osds_list:
            do_local_cmd(cmd + osds)

    return

def just_get_conf_hosts(osds_list):
    conf_hosts_list = []
    if conf_osd_hosts != "":
        for osds in osds_list:
            osd_host = re.split(':', osds)[0]
            if osd_host in conf_osd_hosts:
                conf_hosts_list.append(osds)
    else:
        for osds in osds_list:
            conf_hosts_list.append(osds)

    return conf_hosts_list

def ceph_deploy(mons_list, mdss_list, osds_list, rgws_list, ceph_hosts):
    # Do not deploy monitor if option --just-deploy-osds set
    if not conf_jdo:
        do_local_cmd("rm -rf ceph.*")
        ### Deploy monitors
        mons_str = ' '.join(mons_list)
        #print "mons_str: %s" % mons_str
        do_local_cmd("ceph-deploy new " + mons_str)

        # Add user configure to ceph.conf
        user_configure_ceph()

        do_local_cmd("ceph-deploy mon create-initial")
        create_dir_for_rbd(ceph_hosts)

    ### Add osds to ceph cluster
    deploy_osd_cmd = "ceph-deploy --overwrite-conf osd create "
    output_list = do_local_cmd_with_return("ceph-deploy osd create -h | grep '\--zap-disk'")
    if output_list:
        deploy_osd_cmd_with_zapdisk = "ceph-deploy --overwrite-conf osd create --zap-disk "
    else:
        deploy_osd_cmd_with_zapdisk = "ceph-deploy --overwrite-conf osd create "

    # Just keep the osds which owner in the conf_osd_hosts
    conf_osds_list_devs = just_get_conf_hosts(osds_list["devs"])
    conf_osds_list_parts = just_get_conf_hosts(osds_list["parts"])
    conf_osds_list_paths = just_get_conf_hosts(osds_list["paths"])

    if conf_osds_list_devs:
        ceph_deploy_osd(deploy_osd_cmd_with_zapdisk, conf_osds_list_devs)

    if conf_osds_list_parts:
        ceph_deploy_osd(deploy_osd_cmd, conf_osds_list_parts)
        # Activate osds which device just one partion of disk
        do_osds_parallel_cmd("ceph-deploy osd activate ", conf_osds_list_parts)

    if conf_osds_list_paths:
        ceph_deploy_osd("ceph-deploy --overwrite-conf osd prepare ", conf_osds_list_paths)
        do_osds_parallel_cmd("ceph-deploy osd activate ", conf_osds_list_paths)

    ### Add mdss to the cluster

    ### Add rgws to the cluster
    if rgws_list:
        rgws_str = ' '.join(rgws_list)
        do_local_cmd("ceph-deploy rgw create " + rgws_str)

    # Copy ceph related files to hosts
    do_local_cmd("ceph-deploy --overwrite-conf admin " + ' '.join(ceph_hosts))

    # Copy ceph.conf to remote host(s)
    do_local_cmd("ceph-deploy --overwrite-conf config push " + ' '.join(ceph_hosts))

    return

def create_app_pools(pools, pgnum):
    for pool in pools:
        do_local_cmd("ceph osd pool create " + pool + " " + str(pgnum))
    return

def create_dir_for_rbd(ceph_hosts):
    for host in ceph_hosts:
        do_remote_cmd(host, "mkdir -p /var/run/ceph/ceph-client")
        do_remote_cmd(host, "chmod 777 /var/run/ceph/ceph-client")
    return

def do_ceph_deploy_main(purge_reinstall):
    print "conf_ceph_file = %s" % conf_ceph_file
    if not os.path.exists(conf_ceph_file):
        print "Could NOT find configure file: %s" % conf_ceph_file
        sys.exit(1)

    # Get ceph configuration
    json_data = get_conf_json_data(conf_ceph_file)
    mons_list = get_conf_monitors(json_data["mon"])
    osds_list = get_conf_host_osds(json_data["osd"])
    mdss_list = get_conf_mdss(json_data["mds"])
    rgws_list = get_conf_rgws(json_data["rgw"])
    #print "mons_list: %s" % mons_list
    #print "osds_list: %s" % osds_list
    #print "mdss_list: %s" % mdss_list
    #print "rgws_list: %s" % rgws_list

    # Purge older ceph and reinstall
    tmp = ''.join(json_data["osd"]["hosts"].split())
    osd_hosts = re.split(',', tmp)
    ceph_hosts = mons_list[:]
    ceph_hosts.extend(osd_hosts)
    if rgws_list:
        ceph_hosts.extend(rgws_list)
    # Remove duplicated hosts
    ceph_hosts = list(set(ceph_hosts))
    ceph_hosts.sort()

    # Do Ceph purge or reinstall requests
    if purge_reinstall == "purge":
        purge_older_ceph(ceph_hosts)
        return
    if purge_reinstall == "reinstall":
        purge_older_ceph(ceph_hosts)
        #install_ceph_with_pkgs(ceph_hosts)
        install_ceph_with_cmd(ceph_hosts)
        return

    # Deploy ceph with the configuration
    ceph_deploy(mons_list, mdss_list, osds_list, rgws_list, ceph_hosts)

    # Create keyrings and pools used by apps
    #if not conf_jdo:
    #    init_conf_keyrings(json_data["client"], ceph_hosts)
    #    pgnum = get_suitable_pgnum(osds_list, len(app_pools), ceph_replicas)
    #    create_app_pools(app_pools, pgnum)

def main(argv):
    global conf_debug, conf_ceph_file, conf_ceph_pkg_dir, conf_jnl_path, conf_osd_hosts, conf_jdo

    try:
        opts, args = getopt.getopt(argv[1:], 'hvprc:d:j:o:', ['help', 'version', 'debug', 'just-deploy-osds'])
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
        elif op == '-d':
            conf_ceph_pkg_dir = value
        elif op == '-j':
            conf_jnl_path = value
        elif op == '-o':
            conf_osd_hosts = re.split(':', value)
        elif op == '-p':
            purge_reinstall = "purge"
        elif op == '-r':
            purge_reinstall = "reinstall"
        elif op in ('--debug'):
            conf_debug = True
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
conf_journal_with_osdid = False
conf_do_osd_deploy_parallel = False
conf_ceph_file = "deploy.conf"
conf_ceph_pkg_dir = "/opt/osdeploy/deploy/src/ceph/ceph-debpkgs"
conf_jnl_path = ""
conf_osd_hosts = ""

install_ceph_cmd = "yum install -y ceph ceph-common ceph-radosgw"
app_pools = ["images", "volumes", "backups", "vms"]
ceph_replicas = 3

if __name__ == '__main__':
    main(sys.argv)

