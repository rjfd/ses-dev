import fcntl
import os
import subprocess


class CmdException(Exception):
    def __init__(self, command, retcode, stderr):
        super(CmdException, self).__init__("Command '{}' failed: ret={} stderr:\n{}"
                                           .format(command, retcode, stderr))
        self.command = command
        self.retcode = retcode
        self.stderr = stderr


def run_sync(command):
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
        stdout, stderr = proc.communicate()
        if proc.returncode != 0:
            raise CmdException(command, proc.returncode, stderr)
    return stdout

def _non_block_read(fout):
    fd = fout.fileno()
    fl = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
    try:
        return fout.read()
    except:
        return ''

def run_async(command, callback):
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
        while True:
            output = _non_block_read(proc.stdout)
            if output is not None:
                output = output.strip()
            if output:
                # got new output
                callback(output)
            retcode = proc.poll()
            if retcode is not None:
                if retcode != 0:
                    raise CmdException(command, retcode, proc.stderr.read())
                break
