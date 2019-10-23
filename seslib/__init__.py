import json
from json import JSONEncoder
import os
import uuid
import logging

from jinja2 import Environment, PackageLoader, select_autoescape


METADATA_FILENAME = ".metadata"


logger = logging.getLogger(__name__)

jinja_env = Environment(loader=PackageLoader('seslib', 'templates'), trim_blocks=True)


class GlobalSettings(object):
    WORKING_DIR = None

    @classmethod
    def init(cls, working_dir):
        cls.WORKING_DIR = working_dir


SETTINGS = {
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
    'num_nodes': {
        'type': int,
        'help': 'Number of nodes to use in the deployment',
        'default': 4
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
        'type': str,
        'help': 'List of roles for each node. Example for two nodes: '
                '[[admin, prometheus], [osd, mon, mgr]]',
        'default': '[admin, prometheus, grafana], '
                   '[osd, mon, mgr, rgw, igw], '
                   '[osd, mon, mgr, mds, igw, ganesha], '
                   '[osd, mon, mds, rgw, ganesha]'
    },
    'public_network': {
        'type': str,
        'help': 'The network address prefix for the public network',
        'default': '192.168.100.'
    },
    'cluster_network': {
        'type': str,
        'help': 'The network address prefix for the cluster network',
        'default': '192.168.170.'
    },
    'domain': {
        'type': str,
        'help': 'The domain name for nodes',
        'default': 'sesdev.com'
    }
}

class Settings(object):
    # pylint: disable=no-member
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            if k not in SETTINGS:
                logger.error("Setting '%s' is not known", k)
                raise Exception("Unknown setting: {}".format(k))
            if not isinstance(v, SETTINGS[k]['type']):
                logger.error("Setting '%s' value has wrong type: expected %s but got %s", k,
                             SETTINGS[k]['type'], type(v))
                raise Exception("Wrong value type for setting: {}".format(k))
            setattr(self, k, v)
        for k, v in SETTINGS.items():
            if k not in kwargs:
                setattr(self, k, v['default'])

        self._post_process_settings()

    def _post_process_settings(self):
        # roles
        roles = [n.strip() for n in self.roles.split(",")]
        self.nodes = []
        node = None
        for role in roles:
            if role.startswith('['):
                node = []
                node.append(role[1:])
            elif role.endswith(']'):
                node.append(role[:-1])
                self.nodes.append(node)
            else:
                node.append(role)


class SettingsEncoder(JSONEncoder):
    # pylint: disable=method-hidden
    def default(self, settings):
        return {
            'nodes': settings.nodes
        }


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
    def __init__(self, dep_id, owner, name, settings):
        self.dep_id = dep_id
        self.owner = owner
        self.name = name
        self.settings = settings
        self.nodes = []
        self.admin = None

    def _generate_nodes(self):
        node_id = 1
        for node_roles in self.settings.nodes:
            if 'admin' in node_roles:
                # admin node
                node = Node('admin', 'admin.{}'.format(self.settings.domain),
                            '{}{}'.format(self.settings.public_network, 200))
                self.admin = node
            else:
                node = Node('node{}'.format(node_id),
                            'node{}.{}'.format(node_id, self.settings.domain),
                            '{}{}'.format(self.settings.public_network, 200 + node_id))
                node_id += 1
            self.nodes.append(node)

    def generate_vagrantfile(self):
        self._generate_nodes()

        template = jinja_env.get_template('Vagrantfile.jinja')
        return template.render(**{
            'libvirt_host': '192.168.1.103',
            'libvirt_user': 'rdias',
            'libvirt_use_ssl': 'true',
            'ram': '4096',
            'cpus': '2',
            'vagrant_box': 'opensuse-leap-15.1',
            'nodes': self.nodes,
            'admin': self.admin
        })

    def save(self):
        dep_dir = os.path.join(GlobalSettings.WORKING_DIR, self.dep_id)
        os.makedirs(dep_dir, exist_ok=True)
        metadata_file = os.path.join(dep_dir, METADATA_FILENAME)
        with open(metadata_file, 'w') as file:
            json.dump({
                'id': self.dep_id,
                'name': self.name,
                'owner': self.owner,
                'settings': self.settings
            }, file, cls=SettingsEncoder)

    def __str__(self):
        return "Deployment({}, {}, {})".format(self.dep_id, self.owner, self.name)

    @classmethod
    def create(cls, owner, name, settings):
        dep = cls(str(uuid.uuid4()), owner, name, settings)
        logger.info("creating new deployment: %s", dep)
        dep.save()
        return dep

    @classmethod
    def load(cls, dep_dir):
        if not os.path.exists(dep_dir) or not os.path.isdir(dep_dir):
            logger.debug("%s does not exist or is not a directory", dep_dir)
            return None
        metadata_file = os.path.join(dep_dir, METADATA_FILENAME)
        if not os.path.exists(metadata_file) or not os.path.isfile(metadata_file):
            logger.debug("metadata file %s does not exist or is not a file", metadata_file)
            return None

        with open(metadata_file, 'r') as file:
            metadata = json.load(file)

        return cls(metadata['id'], metadata['owner'], metadata['name'], metadata['settings'])


def list_deployments():
    """
    List the available deployments
    """
    deps = []
    if not os.path.exists(GlobalSettings.WORKING_DIR):
        return deps
    for dep_dir in os.listdir(GlobalSettings.WORKING_DIR):
        dep = Deployment.load(os.path.join(GlobalSettings.WORKING_DIR, dep_dir))
        if dep:
            deps.append(dep)
    return deps


def create_deployment(owner, name, settings):
    """
    Create a new SES deployment
    """
    return Deployment.create(owner, name, settings)
