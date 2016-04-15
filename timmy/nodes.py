#!/usr/bin/env python2
# -*- coding: utf-8 -*-

#    Copyright 2015 Mirantis, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
main module
"""

import flock
import json
import os
import logging
import sys
import threading
import re
from tools import *

ckey = 'cmds'
fkey = 'files'
lkey = 'logs'
varlogdir = '/var/log'


class Node(object):

    def __init__(self, node_id, mac, cluster, roles, os_platform,
                 online, status, ip):
        self.node_id = node_id
        self.mac = mac
        self.cluster = cluster
        self.roles = roles
        self.os_platform = os_platform
        self.online = online
        self.status = status
        self.ip = ip
        self.files = {}
        self.data = {}
        self.logsize = 0
        self.flogs = {}
        self.mapcmds = {}

    def set_files(self, dirname, key, ds, version):
        files = []
        for role in self.roles:
            if 'by-role' in ds[key] and role in ds[key]['by-role'].keys():
                for f in ds[key]['by-role'][role]:
                    files += [os.path.join(dirname, key, 'by-role', role, f)]
            if (('release-'+version in ds[key].keys()) and
                    (role in ds[key]['release-'+version].keys())):
                for f in ds[key]['release-'+version][role]:
                        files += [os.path.join(dirname, key,
                                               'release-'+version, role, f)]
            if 'by-os' in ds[key]:
                for f in ds[key]['by-os'][self.os_platform].keys():
                    files += [os.path.join(dirname, key, 'by-os',
                                           self.os_platform, f)]
            if 'default' in ds[key] and 'default' in ds[key]['default']:
                for f in ds[key]['default']['default'].keys():
                    files += [os.path.join(dirname, key, 'default', 'default', f)]
        self.files[key] = sorted(set(files))
        logging.debug('set_files:\nkey: %s, node: %s, file_list: %s' %
                      (key, self.node_id, self.files[key]))

    def checkos(self, filename):
        bname = str(os.path.basename(filename))
        logging.debug('check os: node: %s, filename %s' %
                      (self.node_id, filename))
        if bname[0] == '.':
            if self.os_platform in bname:
                logging.debug('os %s in filename %s' %
                              (self.os_platform, filename))
                return True
            else:
                return False
        return True

    def exclude_non_os(self):
        for key in self.files.keys():
            self.files[key] = [f for f in self.files[key] if self.checkos(f)]

    def add_files(self, dirname, key, ds):
        for role in self.roles:
            if 'once-by-role' in ds[key] and role in ds[key]['once-by-role'].keys():
                for f in ds[key]['once-by-role'][role]:
                    self.files[key] += [os.path.join(dirname, key,
                                                     'once-by-role', role, f)]
        self.files[key] = sorted(set(self.files[key]))
        logging.debug('add files:\nnode: %s, key: %s, files:\n%s' %
                      (self.node_id, key, self.files[key]))

    def exec_cmd(self, label, sshvars, sshopts, odir='info', timeout=15, fake=False):
        sn = 'node-%s' % self.node_id
        cl = 'cluster-%s' % self.cluster
        logging.debug('%s/%s/%s/%s' % (odir, label, cl, sn))
        ddir = os.path.join(odir, label, cl, sn)
        mdir(ddir)
        for f in self.files[label]:
            logging.info('node:%s(%s), exec: %s' % (self.node_id, self.ip, f))
            if not fake:
                outs, errs, code = ssh_node(ip=self.ip,
                                            filename=f,
                                            sshvars=sshvars,
                                            sshopts=sshopts,
                                            timeout=timeout,
                                            command=''
                                            )
                if code != 0:
                    logging.error("node: %s, ip: %s, cmdfile: %s,"
                                  " code: %s, error message: %s" %
                                  (self.node_id, self.ip, f, code, errs))
            dfile = os.path.join(ddir, 'node-%s-%s-%s' %
                                 (self.node_id, self.ip, os.path.basename(f)))
            logging.info('outfile: %s' % dfile)
            self.mapcmds[os.path.basename(f)] = dfile
            if not fake:
                try:
                    with open(dfile, 'w') as df:
                        df.write(outs)
                except:
                    logging.error("exec_cmd: can't write to file %s" % dfile)

    def exec_simple_cmd(self, cmd, infile, outfile, sshvars, sshopts, timeout=15, fake=False):
        logging.info('node:%s(%s), exec: %s' % (self.node_id, self.ip, cmd))
        if not fake:
            outs, errs, code = ssh_node(ip=self.ip,
                                        command=cmd,
                                        sshvars=sshvars,
                                        sshopts=sshopts,
                                        timeout=timeout,
                                        outputfile=outfile,
                                        inputfile=infile)
            if code != 0:
                logging.warning("node: %s, ip: %s, cmdfile: %s,"
                                " code: %s, error message: %s" %
                                (self.node_id, self.ip, cmd, code, errs))

    def du_logs(self, label, sshopts, odir='info', timeout=15):
        logging.info('node:%s(%s), filelist: %s' %
                     (self.node_id, self.ip, label))
        cmd = 'du -b %s' % self.data[label].replace('\n', ' ')
        logging.info('node: %s, logs du-cmd: %s' % (self.node_id, cmd))
        outs, errs, code = ssh_node(ip=self.ip,
                                    command=cmd,
                                    sshopts=sshopts,
                                    sshvars='',
                                    timeout=timeout)
        if code != 0:
            logging.warning("node: %s, ip: %s, cmdfile: %s, "
                            "code: %s, error message: %s" %
                            (self.node_id, self.ip, label, code, errs))
        if code == 124:
            logging.error("node: %s, ip: %s, command: %s, "
                          "timeout code: %s, error message: %s" %
                          (self.node_id, self.ip, label, code, errs))
            # mark node as offline
            self.online = False
        if self.online:
            size = 0
            for s in outs.splitlines():
                size += int(s.split()[0])
            self.logsize = size
            logging.info("node: %s, ip: %s, size: %s" %
                         (self.node_id, self.ip, self.logsize))

    def get_files(self, label, sshopts, odir='info', timeout=15):
        logging.info('node:%s(%s), filelist: %s' %
                     (self.node_id, self.ip, label))
        sn = 'node-%s' % self.node_id
        cl = 'cluster-%s' % self.cluster
        ddir = os.path.join(odir, label, cl, sn)
        mdir(ddir)
        outs, errs, code = get_files_rsync(ip=self.ip,
                                           data=self.data[label],
                                           sshopts=sshopts,
                                           dpath=ddir,
                                           timeout=timeout)
        if code != 0:
            logging.warning("get_files: node: %s, ip: %s, label: %s, "
                            "code: %s, error message: %s" %
                            (self.node_id, self.ip, label, code, errs))

    def get_data_from_files(self, key):
        self.data[key] = ''
        for fname in self.files[key]:
            try:
                with open(fname, 'r') as dfile:
                    self.data[key] += '\n'+"".join(line for line in dfile
                                                   if (not line.isspace() and
                                                       line[0] != '#'))
            except:
                logging.error('could not read file: %s' % fname)
            logging.debug('node: %s, key: %s, data:\n%s' %
                          (self.node_id, key, self.data[key]))

    def apply_include_filter(self, lfilter):
        logging.info('apply_include_filter: node: %s, filter: %s' % (self.node_id, lfilter))
        flogs = {}
        if 'include' in lfilter and lfilter['include'] is not None:
            for f in self.dulogs.splitlines():
                try:
                    if ('include' in lfilter and re.search(lfilter['include'], f)):
                        flogs[f.split("\t")[1]] = int(f.split("\t")[0])
                    else:
                        logging.debug("filter %s by %s" % (f, lfilter))
                except re.error as e:
                    logging.error('logs_include_filter: filter: %s, str: %s, re.error: %s' %
                                  (lfilter, f, str(e)))
                    sys.exit(5)

            self.flogs.update(flogs)
            return True
        else:
            return False

    def apply_exclude_filter(self, lfilter):
        logging.info('apply_exclude_filter: node: %s, filter: %s' % (self.node_id, lfilter))
        rflogs = []
        if 'exclude' in lfilter and lfilter['exclude'] is None:
            return True
        if 'exclude' in lfilter and lfilter['exclude'] is not None:
            for f in self.flogs:
                try:
                    if re.search(lfilter['exclude'], f):
                        rflogs.append(f)
                        logging.info('logs_exclude_filter: %s' % f)
                except re.error as e:
                    logging.error('logs_include_filter: filter: %s, str: %s, re.error: %s' %
                                  (lfilter, f, str(e)))
                    sys.exit(5)
        for f in rflogs:
            logging.info('apply_exclude_filter: node: %s remove file: %s from log list' % (self.node_id, f ))
            self.flogs.pop(f, None)
            return True
        else:
            return False

    def logs_filter(self, filterconf):
        brstr = 'by_role'
        flogs = {}
        logging.info('logs_filter: node: %s, filter: %s' % (self.node_id, filterconf))
        bynodeidinc = False
        bynodeidexc = False
        #  need to check the following logic:
        #if 'by_node_id' in filterconf and self.node_id in filterconf['by_node_id']:
        #    if self.apply_include_filter(filterconf['by_node_id'][self.node_id]):
        #        bynodeidinc = True
        #    if self.apply_exclude_filter(filterconf['by_node_id'][self.node_id]):
        #        bynodeidexc = True
        #if bynodeidinc:
        #    return
        #if bynodeidexc:
        #    return
        byrole = False
        if brstr in filterconf:
            for role in self.roles:
                if role in filterconf[brstr].keys():
                    logging.info('logs_filter: apply filter for role %s' % role)
                    byrole = True
                    if self.apply_include_filter(filterconf[brstr][role]):
                        byrole = True
        if not byrole:
            if 'default' in filterconf:
                self.apply_include_filter(filterconf['default'])
            else:
                #  unexpected
                logging.warning('default log filter is not defined')
                self.flogs = {}
        byrole = False
        if brstr in filterconf:
            for role in self.roles:
                if role in filterconf[brstr].keys():
                    logging.info('logs_filter: apply filter for role %s' % role)
                    if self.apply_exclude_filter(filterconf[brstr][role]):
                        byrole = True
        if not byrole:
            if 'default' in filterconf:
                logging.info('logs_filter: apply default exclude filter')
                self.apply_exclude_filter(filterconf[brstr])

    def log_size_from_find(self, path, sshopts, timeout=5):
        cmd = ("find '%s' -type f -exec du -b {} +" % (path))
        logging.info('log_size_from_find: node: %s, logs du-cmd: %s' % (self.node_id, cmd))
        outs, errs, code = ssh_node(ip=self.ip,
                                    command=cmd,
                                    sshopts=sshopts,
                                    sshvars='',
                                    timeout=timeout)
        if code == 124:
            logging.error("node: %s, ip: %s, command: %s, "
                          "timeout code: %s, error message: %s" %
                          (self.node_id, self.ip, cmd, code, errs))
            return False
        self.dulogs = outs
        logging.info('log_size_from_find: dulogs: %s' % (self.dulogs))
        return True

    def print_files(self):
        for k in self.files.keys():
            print('key: %s' % (k))
            for f in self.files[k]:
                print(f)
            print('\n')

    def __str__(self):
        if self.status in ['ready', 'discover'] and self.online:
            my_id = self.node_id
        else:
            my_id = '#' + str(self.node_id)

        templ = '{0} {1.cluster} {1.ip} {1.mac} {1.os_platform} '
        templ += '{2} {1.online} {1.status}'
        return templ.format(my_id, self, ','.join(self.roles))


class Nodes(object):
    """Class nodes """

    def __init__(self, cluster, extended, conf, destdir, filename=None):
        import_subprocess()
        self.dirname = conf.rqdir.rstrip('/')
        if (not os.path.exists(self.dirname)):
            logging.error("directory %s doesn't exist" % (self.dirname))
            sys.exit(1)
        self.files = get_dir_structure(conf.rqdir)[os.path.basename(self.dirname)]
        self.fuelip = conf.fuelip
        self.sshopts = conf.ssh['opts']
        self.sshvars = conf.ssh['vars']
        self.timeout = conf.timeout
        self.conf = conf
        self.destdir = destdir
        self.get_version()
        self.cluster = cluster
        self.extended = extended
        logging.info('extended: %s' % self.extended)
        if filename is not None:
            try:
                with open(filename, 'r') as json_data:
                    self.njdata = json.load(json_data)
            except:
                logging.error("Can't load data from file %s" % filename)
                sys.exit(6)
        else:
            self.njdata = json.loads(self.get_nodes())
        self.load_nodes()

    def get_nodes(self):
        fuel_node_cmd = 'fuel node list --json'
        nodes_json, err, code = ssh_node(ip=self.fuelip,
                                         command=fuel_node_cmd,
                                         sshopts=self.sshopts,
                                         sshvars='DUMMY=""',
                                         timeout=self.timeout,
                                         filename=None)
        if code != 0:
            logging.error("Can't get fuel node list %s" % err)
            sys.exit(4)
        return nodes_json

    def pass_hard_filter(self, node):
        if self.conf.hard_filter:
            if self.conf.hard_filter.status and (node.status not in self.conf.hard_filter.status):
                logging.info("hard filter by status: excluding node-%s" % node.node_id)
                return False
            if (isinstance(self.conf.hard_filter.online, bool) and
                    (bool(node.online) != bool(self.conf.hard_filter.online))):
                logging.info("hard filter by online: excluding node-%s" % node.node_id)
                return False
            if (self.conf.hard_filter.node_ids and
                    ((int(node.node_id) not in self.conf.hard_filter.node_ids) and
                     (str(node.node_id) not in self.conf.hard_filter.node_ids))):
                logging.info("hard filter by ids: excluding node-%s" % node.node_id)
                return False
            if self.conf.hard_filter.roles:
                ok_roles = []
                for role in node.roles:
                    if role in self.conf.hard_filter.roles:
                        ok_roles.append(role)
                if not ok_roles:
                    logging.info("hard filter by roles: excluding node-%s" % node.node_id)
                    return False
        return True

    def load_nodes(self):
        node = Node(node_id=0,
                    cluster=0,
                    mac='n/a',
                    os_platform='centos',
                    roles=['fuel'],
                    status='ready',
                    online=True,
                    ip=self.fuelip)
        self.nodes = {}
        if self.pass_hard_filter(node):
            self.nodes = {self.fuelip: node}
        for node in self.njdata:
            node_roles = node.get('roles')
            if not node_roles:
                roles = ['None']
            elif isinstance(node_roles, list):
                roles = node_roles
            else:
                roles = str(node_roles).split(', ')
            node_ip = str(node['ip'])
            keys = "cluster mac os_platform status online".split()
            params = {'node_id': node['id'],
                      'roles': roles,
                      'ip': node_ip}
            for key in keys:
                params[key] = node[key]
            nodeobj = Node(**params)

            if self.pass_hard_filter(nodeobj):
                self.nodes[node_ip] = nodeobj

    def get_version(self):
        cmd = "awk -F ':' '/release/ {print \$2}' /etc/nailgun/version.yaml"
        release, err, code = ssh_node(ip=self.fuelip,
                                      command=cmd,
                                      sshopts=self.sshopts,
                                      sshvars='',
                                      timeout=self.timeout,
                                      filename=None)
        if code != 0:
            logging.error("Can't get fuel version %s" % err)
            sys.exit(3)
        self.version = release.rstrip('\n').strip(' ').strip('"')
        logging.info('release:%s' % (self.version))

    def get_release(self):
        cmd = "awk -F ':' '/fuel_version/ {print \$2}' /etc/astute.yaml"
        for node in self.nodes.values():
            # skip master
            if node.node_id == 0:
                node.release = self.version
            if (node.node_id != 0) and (node.status == 'ready'):
                release, err, code = ssh_node(ip=node.ip,
                                              command=cmd,
                                              sshopts=self.sshopts,
                                              sshvars='',
                                              timeout=self.timeout,
                                              filename=None)
                if code != 0:
                    logging.warning("get_release: node: %s: Can't get node release" %
                                    (node.node_id))
                    node.release = self.version
                    continue
                node.release = release.strip('\n "\'')
                logging.info("get_release: node: %s, release: %s" % (node.node_id, node.release))

    def get_node_file_list(self):
        for key in self.files.keys():
            #  ###   case
            roles = []
            for node in self.nodes.values():
                node.set_files(self.dirname, key, self.files, self.version)
                # once-by-role functionality
                if self.extended and key == ckey and node.online:
                    for role in node.roles:
                        if role not in roles:
                            roles.append(role)
                            logging.debug('role: %s, node: %s' %
                                          (role, node.node_id))
                            node.add_files(self.dirname, key, self.files)
                node.exclude_non_os()
                if key == ckey:
                    logging.info('node: %s, os: %s, key: %s, files: %s' %
                                 (node.node_id,
                                  node.os_platform,
                                  key,
                                  node.files[key]))
        for key in [fkey, lkey]:
            if key in self.files.keys():
                for node in self.nodes.values():
                    node.get_data_from_files(key)
        for node in self.nodes.values():
            logging.debug('%s' % node.files[ckey])

    def launch_ssh(self, odir='info', timeout=15, fake=False):
        lock = flock.FLock('/tmp/timmy-cmds.lock')
        if not lock.lock():
            logging.warning('Unable to obtain lock, skipping "cmds"-part')
            return ''
        label = ckey
        threads = []
        for node in self.nodes.values():
            if (self.cluster and str(self.cluster) != str(node.cluster) and
                    node.cluster != 0):
                continue
            if node.status in self.conf.soft_filter.status and node.online:
                t = threading.Thread(target=node.exec_cmd,
                                     args=(label,
                                           self.sshvars,
                                           self.sshopts,
                                           odir,
                                           self.timeout,
                                           fake))
                threads.append(t)
                t.start()
        for t in threads:
            t.join()
        lock.unlock()

    def filter_logs(self):
        for node in self.nodes.values():
            if (self.cluster and str(self.cluster) != str(node.cluster) and
                    node.cluster != 0):
                continue
            if node.status in self.conf.soft_filter.status and node.online:
                node.logs_filter(self.conf.log_files['filter'])
                #for role in node.roles:
                #    if ('by_role' in self.conf.log_files['filter'] and
                #            role in self.conf.log_files['filter']['by_role'].keys()):
                #        logging.info('filter_logs: node:%s apply role: %s' %
                #                     (node.node_id, role))
                #        node.logs_filter(self.conf.log_files['filter']['by_role'][role])
                logging.debug('filter logs: node-%s: filtered logs: %s' %
                              (node.node_id, node.flogs))

    def calculate_log_size(self, timeout=15):
        lsize = 0
        for node in self.nodes.values():
            if (self.cluster and str(self.cluster) != str(node.cluster) and
                    node.cluster != 0):
                continue
            if node.status in self.conf.soft_filter.status and node.online:
                if not node.log_size_from_find(self.conf.log_files['path'],
                                               self.sshopts,
                                               5):
                    logging.warning("can't get log file list from node %s" % node.node_id)
        self.filter_logs()
        for node in self.nodes.values():
            for f in node.flogs:
                lsize += node.flogs[f]
        logging.info('Full log size on nodes(with fuel): %s bytes' % lsize)
        self.alogsize = lsize / 1024

    def is_enough_space(self, coefficient=1.2):
        outs, errs, code = free_space(self.destdir, timeout=1)
        if code != 0:
            logging.error("Can't get free space: %s" % errs)
            return False
        fs = int(outs.rstrip('\n'))
        logging.info('logsize: %s Kb, free space: %s Kb' % (self.alogsize, fs))
        if (self.alogsize*coefficient > fs):
            logging.error('Not enough space on device')
            return False
        else:
            return True

    def create_archive_general(self, directory, outfile, timeout):
        cmd = "tar jcf '%s' -C %s %s" % (outfile, directory, ".")
        mdir(self.conf.archives)
        logging.debug("create_archive_general: cmd: %s" % cmd)
        outs, errs, code = ssh_node(ip='localhost',
                                    command=cmd,
                                    sshopts=self.sshopts,
                                    sshvars='',
                                    timeout=timeout)
        if code != 0:
            logging.error("Can't create archive %s" % (errs))

    def create_log_archives(self, outdir, timeout):
        threads = []
        txtfl = []
        for node in self.nodes.values():
            if (self.cluster and str(self.cluster) != str(node.cluster) and
                    node.cluster != 0):
                continue

            if node.status in self.conf.soft_filter.status and node.online:
                node.archivelogsfile = os.path.join(outdir,
                                                    'logs-node-'+str(node.node_id) + '.tar.bz2')
                mdir(outdir)
                logslistfile = node.archivelogsfile + '.txt'
                txtfl.append(logslistfile)
                try:
                    with open(logslistfile, 'w') as llf:
                        for line in node.flogs:
                            llf.write(line+"\0")
                except:
                    logging.error("create_archive_logs: Can't write to file %s" % logslistfile)
                    continue
                cmd = "tar --bzip2 --create --file - --null --files-from -"
                t = threading.Thread(target=node.exec_simple_cmd,
                                     args=(cmd,
                                           logslistfile,
                                           node.archivelogsfile,
                                           self.sshvars,
                                           self.sshopts,
                                           timeout)
                                     )
                threads.append(t)
                t.start()
        for t in threads:
            t.join()
        for tfile in txtfl:
            os.remove(tfile)

    def add_logs_archive(self, directory, key, outfile, timeout):
        cmd = ("tar --append --file=%s --directory %s %s" %
               (outfile, directory, key))
        outs, errs, code = ssh_node(ip='localhost', command=cmd,
                                    sshopts=self.sshopts,
                                    sshvars='',
                                    timeout=timeout)
        if code != 2 and code != 0:
            logging.warning("stderr from tar: %s" % (errs))

    def compress_logs(self, timeout):
        for node in self.nodes.values():
            if (self.cluster and str(self.cluster) != str(node.cluster) and
                    node.cluster != 0):
                continue

            if node.status in self.conf.soft_filter.status and node.online:
                self.compress_archive(node.archivelogsfile, timeout)

    def compress_archive(self, filename, timeout):
        cmd = 'bzip2 -f %s' % filename
        outs, errs, code = launch_cmd(command=cmd,
                                      timeout=timeout)
        if code != 0:
            logging.warning("Can't compress archive %s" % (errs))

    def set_template_for_find(self):
        '''Obsolete'''
        for node in self.nodes.values():
            node.flpath = self.conf.log_files['path']
            node.fltemplate = self.conf.log_files['filter']['default']
            for role in node.roles:
                if role in self.conf.log_files['filter']['by_role'].keys():
                    node.fltemplate = self.conf.log_files['filter']['by_role'][role]
                    logging.debug('set_template_for_find: break on role %s' % role)
                    break
            if (self.conf.log_files['filter']['by_node_id'] and
                    node.node_id in self.conf.log_files['filter']['by_node_id'].keys()):
                node.fltemplate = self.conf.log_files['by_node_id'][node.node_id]
            logging.debug('set_template_for_find: node: %s, template: %s' %
                          (node.node_id, node.fltemplate))

    def get_conf_files(self, odir=fkey, timeout=15):
        if fkey not in self.files:
            logging.warning("get_conf_files: %s directory does not exist" % fkey)
            return
        lock = flock.FLock('/tmp/timmy-files.lock')
        if not lock.lock():
            logging.warning('Unable to obtain lock, skipping "files"-part')
            return ''
        label = fkey
        threads = []
        for node in self.nodes.values():
            if (self.cluster and str(self.cluster) != str(node.cluster) and
                    node.cluster != 0):
                continue
            if node.status in self.conf.soft_filter.status and node.online:
                t = threading.Thread(target=node.get_files,
                                     args=(label,
                                           self.sshopts,
                                           odir,
                                           self.timeout,))
                threads.append(t)
                t.start()
        for t in threads:
            t.join()
        lock.unlock()

    def get_log_files(self, odir=lkey, timeout=15):
        if lkey not in self.files:
            logging.warning("get_log_files: %s directory does not exist" % lkey)
            return
        label = lkey
        threads = []
        for node in self.nodes.values():
            if (self.cluster and str(self.cluster) != str(node.cluster) and
                    node.cluster != 0):
                continue
            if (node.status in self.conf.soft_filter.status and
                    node.online and str(node.node_id) != '0'):
                        t = threading.Thread(target=node.get_files,
                                             args=(label,
                                                   self.sshopts,
                                                   odir,
                                                   self.timeout,))
                        threads.append(t)
                        t.start()
        for t in threads:
            t.join()

    def print_nodes(self):
        """print nodes"""
        print('#node-id, cluster, admin-ip, mac, os, roles, online, status')
        for node in sorted(self.nodes.values(), key=lambda x: x.node_id):
            if (self.cluster and
                    (str(self.cluster) != str(node.cluster)) and
                    node.cluster != 0):
                print("#"+str(node))
            else:
                print(str(node))


def main(argv=None):
    return 0

if __name__ == '__main__':
    exit(main(sys.argv))