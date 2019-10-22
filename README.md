# SES-DEV Project

Docker container that bundles vagrant and vagran-libvirt to help with the
deployment of SES clusters using vagrant-based deployment scripts

# Container build

```
docker build --build-arg user_name=$(whoami) \
             --build-arg user_id=$(id -u) \
             --build-arg group_id=$(id -g) \
             -t ses-dev .
```

The `user_id` and `group_id` have the default values `1000` and `100`
respectively.

# Running the container

```
docker run --rm -ti --net=host \
        --user $(id -u):$(id -g) \
        -v <HOST_VAGRANT_FILE_DIR>:/vagrant-prj \
        -v $HOME:$HOME ses-dev
```

`HOST_VAGRANT_FILE_DIR` is the directory that contains the `Vagrantfile` file
that you use to deploy your cluster.

We suggest to export `$HOME` into the container to make it easy for vagrant to
use the `~/.vagrant.d` directory and the ssh keys that exist in your home.

