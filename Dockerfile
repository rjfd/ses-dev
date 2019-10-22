FROM opensuse/leap:15.1

ARG user_name
ARG user_id=1000
ARG group_id=100

RUN zypper ar https://download.opensuse.org/repositories/Virtualization:/vagrant/openSUSE_Leap_15.1/Virtualization:vagrant.repo \
    && zypper --gpg-auto-import-keys ref

RUN zypper -n in vagrant vagrant-libvirt sudo

RUN useradd -u $user_id -g $group_id $user_name

RUN zypper -n in sudo
RUN echo "$user_name ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

ENTRYPOINT ["/bin/bash"]

