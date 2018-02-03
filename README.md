# ceph-deploy

This python script used to deply ceph auto with ceph-deploy
Please configure the deploy.conf before do ceph auto deploy

## Getting Started
Most parameters in deploy.conf are same with ceph parameters, the deploy python
script will create the ceph.conf file according to the deploy.conf.

For special configurations, like below, are the ceph cluster info, which parsed 
by the python script.

# monitor

```
[mon]
    hosts = cloud01, cloud02, cloud03
```

hosts: The hosts would deploy monitor on them.

# osd

```
[osd]
    hosts = cloud01, cloud02, cloud03, cloud04

    # Example configuration use file system path
    #osd.cloud01.paths = /var/lib/ceph/osd/ceph-0, /var/lib/ceph/osd/ceph-1
    #osd.cloud02.paths = /var/lib/ceph/osd/ceph-2, /var/lib/ceph/osd/ceph-3
    # Configuration with host devices
    osd.cloud01.devs = sdb:sdl, sdc:sdl, sdd:sdl, sde:sdl, sdf:sdl, sdg:sdm, sdh:sdm, sdi:sdm, sdj:sdm, sdk:sdm
    osd.cloud02.devs = sdb:sdl, sdc:sdl, sdd:sdl, sde:sdl, sdf:sdl, sdg:sdm, sdh:sdm, sdi:sdm, sdj:sdm, sdk:sdm
    osd.cloud03.devs = sdb:sdl, sdc:sdl, sdd:sdl, sde:sdl, sdf:sdl, sdg:sdm, sdh:sdm, sdi:sdm, sdj:sdm, sdk:sdm
    osd.cloud04.devs = sdb:sdl, sdc:sdl, sdd:sdl, sde:sdl, sdf:sdl, sdg:sdm, sdh:sdm, sdi:sdm, sdj:sdm, sdk:sdm
```

- hosts: The hosts would deploy osds on them.
- osd.[host].devs: The host devices to deploy ceph osd
    For example: 'sdb:sdl' mean use 'sdb' as osd disk, 'sdl' as osd journal

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

## Deploy Ceph Cluster

Run python script ceph_auto_deploy.py: `python ceph_auto_deploy.py`
