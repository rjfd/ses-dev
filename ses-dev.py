import logging

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
        click.echo(dep)


@cli.command()
@click.argument('owner')
@click.argument('name')
def create(owner, name):
    dep = seslib.create_deployment(owner, name, seslib.Settings())
    click.echo(dep.generate_vagrantfile())


if __name__ == '__main__':
    cli()