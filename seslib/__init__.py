import json
import os
import uuid
import logging


METADATA_FILENAME = ".metadata"


logger = logging.getLogger(__name__)


class GlobalSettings(object):
    WORKING_DIR = None

    @classmethod
    def init(cls, working_dir):
        cls.WORKING_DIR = working_dir


SETTINGS = {
    'libvirt_host': {
        'type': str,
        'help': 'Hostname/IP address of the libvirt host',
        'default': 'localhost'
    },
    'libvirt_user': {
        'type': str,
        'help': 'Username to use to login into the libvirt host',
        'default': 'root'
    },
    'libvirt_use_ssl': {
        'type': bool,
        'help': 'Flag to control the use of SSL when connecting to the libvirt host',
        'default': False
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
        'default': '[[admin, prometheus, grafana], '
                   ' [osd, mon, mgr, rgw, igw], '
                   ' [osd, mon, mgr, mds, igw, ganesha], '
                   ' [osd, mon, mds, rgw, ganesha]]'
    },
    'public_network': {
        'type': str,
        'help': 'The network address/mask for the public network',
        'default': '192.168.100.0/24'
    },
    'cluster_network': {
        'type': str,
        'help': 'The network address/mask for the cluster network',
        'default': '192.168.170.0/24'
    }
}


class Deployment(object):
    def __init__(self, dep_id, owner, name, settings):
        self.dep_id = dep_id
        self.owner = owner
        self.name = name
        self.settings = settings

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
            }, file)

    def __str__(self):
        return "Deployment({}, {}, {})".format(self.dep_id, self.owner, self.name)        

    @classmethod
    def create(cls, owner, name, settings):
        dep = cls(str(uuid.uuid4()), owner, name, settings)
        logger.info("creating new deployment: %s", dep)
        dep.save()

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
    Deployment.create(owner, name, settings)
