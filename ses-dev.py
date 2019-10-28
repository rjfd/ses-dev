import logging
import sys

import click
import seslib


logger = logging.getLogger(__name__)


@click.group()
@click.option('-w', '--work-path', required=True,
              type=click.Path(exists=True, dir_okay=True, file_okay=False),
              help='Filesystem path to store deployments')
@click.option('--debug/--no-debug', default=False)
@click.option('--log-file', type=str, default='ses-dev.log')
def cli(work_path=None, debug=False, log_file=None):
    logging.basicConfig(format='%(asctime)s [%(levelname)s] [%(name)s] %(message)s',
                        filename=log_file, filemode='w',
                        level=logging.INFO if not debug else logging.DEBUG)

    logger.info("Working path: %s", work_path)
    seslib.GlobalSettings.WORKING_DIR = work_path


@cli.command()
def list():
    deps = seslib.list_deployments()
    for dep in deps:
        click.echo(dep.status())
        click.echo()


def _print_log(output):
    sys.stdout.write(output)
    sys.stdout.flush()


@cli.command()
@click.argument('deployment_id')
@click.option('--roles', type=str, default=None,
              help='List of roles for each node. Example for two nodes: '
                   '[admin, prometheus],[osd, mon, mgr]')
@click.option('--os', type=str, default=None,
              help='openSUSE OS version (leap-15.1, tumbleweed, sles-12-sp3, or sles-15-sp1)')
@click.option('--deploy/--no-deploy', default=True,
              help="Don't run the deployment phase. Just generated the Vagrantfile")
def create(deployment_id, roles, os, deploy):
    settings_dict = {}
    if roles:
        roles = [r.strip() for r in roles.split(",")]
        _roles = []
        _node = None
        for r in roles:
            r = r.strip()
            if r.startswith('['):
                _node = []
                if r.endswith(']'):
                    r = r[:-1]
                    _node.append(r[1:])
                    _roles.append(_node)
                else:
                    _node.append(r[1:])
            elif r.endswith(']'):
                _node.append(r[:-1])
                _roles.append(_node)
            else:
                _node.append(r)
        settings_dict['roles'] = _roles

    if os:
        settings_dict['os'] = os

    settings = seslib.Settings(**settings_dict)

    dep = seslib.Deployment.create(deployment_id, settings)
    if deploy:
        dep.start(_print_log)


@cli.command()
@click.argument('deployment_id')
def destroy(deployment_id):
    dep = seslib.Deployment.load(deployment_id)
    dep.destroy(_print_log)


@cli.command()
@click.argument('deployment_id')
@click.argument('node_name')
def ssh(deployment_id, node_name):
    dep = seslib.Deployment.load(deployment_id)
    dep.ssh(node_name)


@cli.command()
@click.argument('deployment_id')
@click.argument('node', required=False)
def stop(deployment_id, node=None):
    dep = seslib.Deployment.load(deployment_id)
    dep.stop(node, _print_log)


@cli.command()
@click.argument('deployment_id')
@click.argument('node', required=False)
def start(deployment_id, node=None):
    dep = seslib.Deployment.load(deployment_id)
    dep.start(node, _print_log)


@cli.command()
@click.argument('deployment_id')
def info(deployment_id):
    dep = seslib.Deployment.load(deployment_id)
    click.echo(dep.status())


if __name__ == '__main__':
    cli()