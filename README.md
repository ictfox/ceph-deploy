## ceph-deploy

This python script used to auto deply Ceph Cluster with ceph-deploy.
Please configure the deploy.conf before do Ceph Cluster auto deploy.

For more usage description, see my homepage: [ictfox](www.yangguanjun.com)

## Getting Started
Most parameters in deploy.conf are same with ceph parameters, the deploy python
script will create the ceph.conf file according to this file.

For special configurations, like below, are the Ceph Cluster info, just be used
by the python script.

## deploy.conf
Before do ceph cluster auto deploy, make sure you know everything plan to used
for Ceph Cluster, like monitor/osd/radosgw nodes, osd/journal devices,
public/cluster network and so on.

Please configure them in deploy.conf as descripted.

```sh
##################
## host-specific
## Put your settings for each node here, these settings will be removed
## from the ultimate ceph.conf
[host-specific]
mon_hosts = ceph0, ceph1, ceph2
osd_hosts = ceph0, ceph1, ceph2
rgw_hosts = ceph0, ceph1, ceph2

# Example configuration use file system path
#osd.ceph0.paths = /var/lib/ceph/osd/ceph-0, /var/lib/ceph/osd/ceph-1
#osd.ceph1.paths = /var/lib/ceph/osd/ceph-2, /var/lib/ceph/osd/ceph-3
osd.ceph0.devs = sdb:sde, sdc:sde, sdd:sde
osd.ceph1.devs = sdb, sdc, sdd
osd.ceph2.devs = sdb, sdc, sdd:sde

## for multi network settings
## public network 1;cluster network1 = Host1, Host2, Host3
## public network 2;cluster network2 = Host4, Host5
192.10.1.0/24;192.10.1.0/24 = ceph0, ceph1, ceph2
```

- mon_hosts: The hosts which deploy Monitor
- osd_hosts: The hosts which deploy OSDs
- rgw_hosts: The hosts which deploy RadosGW
- osd.[host].devs: The host devices to deploy ceph osd
    * 'sdb:sde' mean use whole 'sdb' as osd disk, use one partion of 'sde' as osd journal
    * 'sdb' mean use whole 'sdb' as osd disk, use file as its journal
- public network;cluster network1: The hosts which use THIS 'public/cluster network' configuration

## Usage

```
ceph_auto_deploy.py usage:
    python ceph_auto_deploy.py     run this script with default configuration
    -h, --help                          print help message
    -v, --version                       print script version
    -c [configure file]                 specify the configure file
    -d [ceph deb packages dir]          specify the ceph deb packages directory
    -j [osd journal path]               specify the osd journal file path
    -o [osd_host:osd_host:...]          just deploy the osds on this hosts
    -p                                  just purge older ceph and ceph data
    -r                                  do ceph purge and ceph reinstall
    --just-deploy-osds                  just do deploy ceph osds
    --debug                             just print out the commands
```

Some usually command as below.

### Deploy Ceph Cluster
`python ceph_auto_deploy.py`
> Deploy Ceph Cluster according to deploy.conf

### Purge Ceph Cluster
`python ceph_auto_deploy.py -p`
> Purge older Ceph Cluster and its data

### Puerge Ceph Cluster and Reinstall Ceph packages
`python ceph_auto_deploy.py -r`
> Will NOT deploy Ceph Cluster
