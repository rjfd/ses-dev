from datetime import datetime
import json
from json import JSONEncoder
import logging
import os
import random
import shutil

from Crypto.PublicKey import RSA

from jinja2 import Environment, PackageLoader, select_autoescape

from . import tools


METADATA_FILENAME = ".metadata"


logger = logging.getLogger(__name__)

jinja_env = Environment(loader=PackageLoader('seslib', 'templates'), trim_blocks=True)


class GlobalSettings(object):
    WORKING_DIR = None

    @classmethod
    def init(cls, working_dir):
        cls.WORKING_DIR = working_dir


OS_BOX_MAPPING = {
    'leap-15.1': 'https://download.opensuse.org/repositories/Virtualization:/Appliances:/Images:/openSUSE-Leap-15.1/images/Leap-15.1.x86_64-libvirt.box',
    'tumbleweed': 'https://download.opensuse.org/repositories/Virtualization:/Appliances:/Images:/openSUSE-Tumbleweed/openSUSE_Tumbleweed/Tumbleweed.x86_64-libvirt.box',
    'sles-15-sp1': 'http://download.suse.de/ibs/Virtualization:/Vagrant:/SLE-15-SP1/images/boxes/SLES15-SP1-Vagrant.x86_64.json',
    'sles-12-sp3': 'http://download.suse.de/ibs/Devel:/Storage:/5.0/vagrant/sle12sp3.x86_64.box',
}


SETTINGS = {
    'version': {
        'type': str,
        'help': 'SES version to install (ses5, ses6, luminous, nautilus, octopus)',
        'default': 'nautilus'
    },
    'os': {
        'type': str,
        'help': 'openSUSE OS version (leap-15.1, tumbleweed, sles-12-sp3, or sles-15-sp1)',
        'default': 'leap-15.1'
    },
    'libvirt_host': {
        'type': str,
        'help': 'Hostname/IP address of the libvirt host',
        'default': None
    },
    'libvirt_user': {
        'type': str,
        'help': 'Username to use to login into the libvirt host',
        'default': None
    },
    'libvirt_use_ssl': {
        'type': bool,
        'help': 'Flag to control the use of SSL when connecting to the libvirt host',
        'default': None
    },
    'ram': {
        'type': int,
        'help': 'RAM size in gigabytes for each node',
        'default': 4
    },
    'cpus': {
        'type': int,
        'help': 'Number of virtual CPUs in each node',
        'default': 2
    },
    'num_disks': {
        'type': int,
        'help': 'Number of additional disks in storage nodes',
        'default': 2
    },
    'disk_size': {
        'type': int,
        'help': 'Storage disk size in gigabytes',
        'default': 8
    },
    'roles': {
        'type': list,
        'help': 'List of roles for each node. Example for two nodes: '
                '[["admin", "prometheus"], ["osd", "mon", "mgr"]]',
        'default': [["admin", "prometheus", "grafana"],
                    ["osd", "mon", "mgr", "rgw", "igw"],
                    ["osd", "mon", "mgr", "mds", "igw", "ganesha"],
                    ["osd", "mon", "mds", "rgw", "ganesha"]]
    },
    'public_network': {
        'type': str,
        'help': 'The network address prefix for the public network',
        'default': None
    },
    'cluster_network': {
        'type': str,
        'help': 'The network address prefix for the cluster network',
        'default': None
    },
    'domain': {
        'type': str,
        'help': 'The domain name for nodes',
        'default': '{}.com'
    }
}

class Settings(object):
    # pylint: disable=no-member
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            if k not in SETTINGS:
                logger.error("Setting '%s' is not known", k)
                raise Exception("Unknown setting: {}".format(k))
            if v is not None and not isinstance(v, SETTINGS[k]['type']):
                logger.error("Setting '%s' value has wrong type: expected %s but got %s", k,
                             SETTINGS[k]['type'], type(v))
                raise Exception("Wrong value type for setting: {}".format(k))
            setattr(self, k, v)
        for k, v in SETTINGS.items():
            if k not in kwargs:
                setattr(self, k, v['default'])


class SettingsEncoder(JSONEncoder):
    # pylint: disable=method-hidden
    def default(self, settings):
        return {k: getattr(settings, k) for k in SETTINGS}


class Disk(object):
    def __init__(self, size):
        self.size = size


class Node(object):
    def __init__(self, name, fqdn, public_address, cluster_address=None, storage_disks=None):
        self.name = name
        self.fqdn = fqdn
        self.public_address = public_address
        self.cluster_address = cluster_address
        if storage_disks is None:
            storage_disks = []
        self.storage_disks = storage_disks


class Deployment(object):
    def __init__(self, dep_id, settings):
        self.dep_id = dep_id
        self.settings = settings
        self.nodes = {}
        self.admin = None

        self._generate_networks()
        self._generate_nodes()

    @property
    def dep_dir(self):
        return os.path.join(GlobalSettings.WORKING_DIR, self.dep_id)

    def _generate_networks(self):
        if self.settings.public_network is not None and self.settings.cluster_network is not None:
            return

        deps = list_deployments()
        existing_networks = [dep.settings.public_network for dep in deps
                             if dep.settings.public_network]
        existing_networks.extend([dep.settings.cluster_network for dep in deps
                                  if dep.settings.cluster_network])
        public_network = self.settings.public_network
        cluster_network = self.settings.cluster_network

        while True:
            if public_network is None or public_network in existing_networks:
                public_network = "10.20.{}.".format(random.randint(2, 200))
            else:
                break

        while True:
            if cluster_network is None or cluster_network in existing_networks:
                cluster_network = "10.20.{}.".format(random.randint(2, 200))
            else:
                break

        self.settings.public_network = public_network
        self.settings.cluster_network = cluster_network

    def _generate_nodes(self):
        node_id = 1
        for node_roles in self.settings.roles:
            if 'admin' in node_roles:
                # admin node
                node = Node('admin', 'admin.{}'.format(self.settings.domain.format(self.dep_id)),
                            '{}{}'.format(self.settings.public_network, 200))
                self.admin = node
            else:
                node = Node('node{}'.format(node_id),
                            'node{}.{}'.format(node_id,
                                               self.settings.domain.format(self.dep_id)),
                            '{}{}'.format(self.settings.public_network, 200 + node_id))
                if 'osd' in node_roles:
                    node.cluster_address = '{}{}'.format(self.settings.cluster_network,
                                                         200 + node_id)
                    for _ in range(self.settings.num_disks):
                        node.storage_disks.append(Disk(self.settings.disk_size))
                node_id += 1
            self.nodes[node.name] = node

    def generate_vagrantfile(self):
        template = jinja_env.get_template('Vagrantfile.jinja')
        return template.render(**{
            'libvirt_host': '192.168.1.103',
            'libvirt_user': 'rdias',
            'libvirt_use_ssl': 'true',
            'libvirt_storage_pool': 'vagrant',
            'ram': self.settings.ram * 2**10,
            'cpus': self.settings.cpus,
            'vagrant_box': self.settings.os,
            'nodes': [n for _, n in self.nodes.items()],
            'admin': self.admin
        })

    def save(self):
        os.makedirs(self.dep_dir, exist_ok=False)
        metadata_file = os.path.join(self.dep_dir, METADATA_FILENAME)
        with open(metadata_file, 'w') as file:
            json.dump({
                'id': self.dep_id,
                'settings': self.settings
            }, file, cls=SettingsEncoder)

        vagrantfile = os.path.join(self.dep_dir, 'Vagrantfile')
        with open(vagrantfile, 'w') as file:
            file.write(self.generate_vagrantfile())

        # generate ssh key pair
        keys_dir = os.path.join(self.dep_dir, 'keys')
        os.makedirs(keys_dir)
        key = RSA.generate(2048)
        private_key = key.export_key('PEM')
        public_key = key.publickey().export_key('OpenSSH')

        with open(os.path.join(keys_dir, 'id_rsa'), 'w') as file:
            file.write(private_key.decode('utf-8'))
        os.chmod(os.path.join(keys_dir, 'id_rsa'), 0o600)

        with open(os.path.join(keys_dir, 'id_rsa.pub'), 'w') as file:
            file.write(public_key.decode('utf-8'))
        os.chmod(os.path.join(keys_dir, 'id_rsa.pub'), 0o600)

        # bin dir with helper scripts
        bin_dir = os.path.join(self.dep_dir, 'bin')
        os.makedirs(bin_dir)

    def get_vagrant_box(self, log_handler):
        logger.info("Checking if vagrant box is already here: %s", self.settings.os)
        found_box = False
        output = tools.run_sync(["vagrant", "box", "list"])
        lines = output.split('\n')
        for line in lines:
            if line:
                box_name = line.split()[0]
                if box_name == self.settings.os:
                    logger.info("Found vagrant box")
                    found_box = True
                    break

        if not found_box:
            logger.info("Vagrant box for '%s' is not installed, we need to add it",
                        self.settings.os)

            log_handler("Downloading vagrant box: {}\n".format(self.settings.os))

            tools.run_async(["vagrant", "box", "add", "--provider", "libvirt", "--name",
                             self.settings.os, OS_BOX_MAPPING[self.settings.os]], log_handler)

    def vagrant_up(self, node, log_handler):
        if node is None:
            node = ""
        tools.run_async(["vagrant", "up", node], log_handler, self.dep_dir)

    def destroy(self, log_handler):
        tools.run_async(["vagrant", "destroy", "--force"], log_handler, self.dep_dir)
        shutil.rmtree(self.dep_dir)

    def _stop(self, node, log_handler):
        ssh_cmd = self._ssh_cmd(node)
        ssh_cmd.extend(['echo "sleep 2 && shutdown -h now" > /root/shutdown.sh && chmod +x /root/shutdown.sh'])
        tools.run_sync(ssh_cmd)
        ssh_cmd = self._ssh_cmd(node)
        ssh_cmd.extend(['nohup /root/shutdown.sh > /dev/null 2>&1 &'])
        tools.run_sync(ssh_cmd)

    def stop(self, node=None, log_handler=None):
        if node and node not in self.nodes:
            raise Exception("Node '{}' does not exist in this deployment".format(name))
        elif node:
            self._stop(node, log_handler)
        else:
            for node in self.nodes:
                self._stop(node, log_handler)

    def start(self, node=None, log_handler=None):
        if node and node not in self.nodes:
            raise Exception("Node '{}' does not exist in this deployment".format(name))

        self.get_vagrant_box(log_handler)
        self.vagrant_up(node, log_handler)

    def __str__(self):
        return self.dep_id

    def status(self):
        nodes_info = {}
        out = tools.run_sync(["vagrant", "status"], cwd=self.dep_dir)
        for line in [line.strip() for line in out.split('\n')]:
            if line:
                line_arr = line.split(' ', 1)
                if line_arr[0] in self.nodes:
                    if line_arr[1].strip().startswith("running"):
                        nodes_info[line_arr[0]] = "running"
                    elif line_arr[1].strip().startswith("not created"):
                        nodes_info[line_arr[0]] = "not deployed"
                    elif line_arr[1].strip().startswith("shutoff"):
                        nodes_info[line_arr[0]] = "stopped"
                    elif line_arr[1].strip().startswith("paused"):
                        nodes_info[line_arr[0]] = "suspended"
        result = "{}:\n".format(self.dep_id)
        for k, v in nodes_info.items():
            result += "  - {}: {}\n".format(k, v)
        return result

    def _ssh_cmd(self, name):
        if name not in self.nodes:
            raise Exception("Node '{}' does not exist in this deployment".format(name))

        out = tools.run_sync(["vagrant", "ssh-config", name], cwd=self.dep_dir)
        address = None
        proxycmd = None
        for line in out.split('\n'):
            line = line.strip()
            if line.startswith('HostName'):
                address = line[len('HostName')+1:]
            elif line.startswith('ProxyCommand'):
                proxycmd = line[len('ProxyCommand')+1:]

        if address is None:
            raise Exception("Could not get HostName info from 'vagrant ssh-config {}' command"
                            .format(name))
        if proxycmd is None:
            raise Exception("Could not get ProxyCommand info from 'vagrant ssh-config {}' command"
                            .format(name))

        dep_private_key = os.path.join(self.dep_dir, "keys/id_rsa")
        return ["ssh", "root@{}".format(address), "-i", dep_private_key,
                "-o", "IdentitiesOnly yes", "-o", "StrictHostKeyChecking no",
                "-o", "UserKnownHostsFile /dev/null", "-o", "PasswordAuthentication no",
                "-o", "ProxyCommand={}".format(proxycmd)]

    def ssh(self, name):
        tools.run_interactive(self._ssh_cmd(name))

    @classmethod
    def create(cls, dep_id, settings):
        dep = cls(dep_id, settings)
        logger.info("creating new deployment: %s", dep)
        dep.save()
        return dep

    @classmethod
    def load(cls, dep_id):
        dep_dir = os.path.join(GlobalSettings.WORKING_DIR, dep_id)
        if not os.path.exists(dep_dir) or not os.path.isdir(dep_dir):
            logger.debug("%s does not exist or is not a directory", dep_dir)
            return None
        metadata_file = os.path.join(dep_dir, METADATA_FILENAME)
        if not os.path.exists(metadata_file) or not os.path.isfile(metadata_file):
            logger.debug("metadata file %s does not exist or is not a file", metadata_file)
            return None

        with open(metadata_file, 'r') as file:
            metadata = json.load(file)

        return cls(metadata['id'], Settings(**metadata['settings']))


def list_deployments():
    """
    List the available deployments
    """
    deps = []
    if not os.path.exists(GlobalSettings.WORKING_DIR):
        return deps
    for dep_id in os.listdir(GlobalSettings.WORKING_DIR):
        dep = Deployment.load(dep_id)
        if dep:
            deps.append(dep)
    return deps


def destroy_deployment(deployment_id, log_handler):
    """
    Destroy an existing SES deployment
    """
    return Deployment.destroy(deployment_id, log_handler)
