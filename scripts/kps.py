#!/usr/bin/env python3

"""
usage: kps.py [-h] [--search {contains,startswith,equals}] [-s {c,s,e}] [--show-commands] app_name
A small cli script to quickly and easily get a shell for any pod of any kubernetes container.
Written and tested for TrueNAS Scale Dragonfish 24.04
positional arguments:
  app_name              name of the kubernetes container
options:
  -h, --help            show this help message and exit
  --search {contains,startswith,equals}
                        container name search method (default contains)
  -s {c,s,e}            [short variant of --search]
  --show-commands       display the ran commands to get the shell
USE THIS SCRIPT AT YOUR OWN RISK! IT COMES WITHOUT WARRANTY AND IS NOT SUPPORTED BY IXSYSTEMS.


Example usage to get a shell for my Jellyfin app:
```
admin@truenas[/mnt/hdd_pool/scripts]$ sudo ./kps.py jelly
found multiple active namespaces:
 [0] ix-jellyfin
 [1] ix-jellyseerr
 [2] ix-jellyfin-tubesync
select namespace by index: 0
selected namespace: ix-jellyfin
found running pod: jellyfin-5dd75f4df6-ql5pq

shell:
I have no name!@truenas:/$ ls
bin  boot  cache  config  dev  etc  home  jellyfin  lib  lib64  media  mnt  opt  proc  root  run  sbin  srv  sys  tmp  usr  var
I have no name!@truenas:/$ exit
exit
admin@truenas[/mnt/hdd_pool/scripts]$
```
"""

__version__ = "2025.03.09"
__author__ = "Fabian Bartl"
__copyright__ = "Copyright (C) 2025, Fabian Bartl"
__license__ = "MIT License"
__disclaimer__ = "USE THIS SCRIPT AT YOUR OWN RISK! IT COMES WITHOUT WARRANTY AND IS NOT SUPPORTED BY IXSYSTEMS."

import re
import subprocess
import argparse
import itertools


def print_command_preview(command: list[str]) -> None:
    global _args
    if _args.show_commands:
        print("$", " ".join([ str(cmd) for cmd in command ]))


def get_active_namespaces() -> list[str]:
    cmd_get_namespaces = ["sudo", "k3s", "kubectl", "get", "namespaces"]
    print_command_preview(cmd_get_namespaces)
    process = subprocess.run(cmd_get_namespaces, stdout=subprocess.PIPE)
    output = process.stdout.decode()
    
    namespaces = []
    for line in output.split("\n")[1:]:
        line = re.sub(" +", " ", line).strip()
        if not line:
            continue
        coloumns = dict(itertools.zip_longest(["name", "status", "age"], line.split(" ")))

        if coloumns["status"].lower() == "active":
            namespaces.append(coloumns)
    
    return namespaces


def get_running_pods_of_namespace(namespace: str) -> list[str]:
    cmd_get_pods = ["sudo", "k3s", "kubectl", "get", "-n", namespace, "pods"]
    print_command_preview(cmd_get_pods)
    process = subprocess.run(cmd_get_pods, stdout=subprocess.PIPE)
    output = process.stdout.decode()
    
    pods = []
    for line in output.split("\n")[1:]:
        line = re.sub(" +", " ", line).strip()
        if not line:
            continue
        coloumns = dict(itertools.zip_longest(["name", "ready", "status", "restarts", "age"], line.split(" ")))
        
        if coloumns["status"].lower() == "running":
            pods.append(coloumns)
    
    return pods


def launch_pod_shell(namespace: str, pod: str) -> subprocess.CompletedProcess:
    cmd_launch_shell = ["sudo", "k3s", "kubectl", "exec", "-n", namespace, "--stdin", "--tty", pod, "--", "/bin/bash"]
    print_command_preview(cmd_launch_shell)
    return subprocess.run(cmd_launch_shell)


def select_one_of_many(options: list[str], input_message: str) -> tuple[int, str]:
    for ind, option in enumerate(options):
        print(f" [{ind}]", option)
    if not input_message.endswith(" "):
        input_message += " "

    selected_ind = -1
    while not (0 <= selected_ind < len(options)):
        user_input = input(input_message).strip()
        if user_input.isdigit():
            selected_ind = int(user_input)
        else:
            print("invalid index")

    selected = options[selected_ind]
    return (selected_ind, selected)



def main(app_name: str, *, search_variant: str = "contains") -> None:
    search_variant = search_variant.lower()
    found_namespaces = []
    for namespace in get_active_namespaces():
        append_namespace = \
            search_variant in ["contains", "c"] and app_name.lower() in namespace["name"].lower() or \
            search_variant in ["startswith", "s"] and namespace["name"].lower().startswith(app_name.lower()) or \
            search_variant in ["equals", "e"] and app_name.lower() == namespace["name"].lower()
        if append_namespace:
            found_namespaces.append(namespace["name"])
    
    if len(found_namespaces) == 0:
        print("E: no active namespace found")
        return

    elif len(found_namespaces) > 1:
        print("found multiple active namespaces:")
        _, namespace = select_one_of_many(found_namespaces, "select namespace by index:")
        print("selected namespace:", namespace)

    else:
        namespace = found_namespaces[0]
        print("found active namespace:", namespace)

    pods = get_running_pods_of_namespace(namespace)
    if len(pods) == 0:
        print("no runnign pods found")
        return

    elif len(pods) > 1:
        print("found multiple running pods:")
        _, pod = select_one_of_many([pod["name"] for pod in pods], "select pod by index:")
        print("selected pod:", pod)

    else:
        pod = pods[0]["name"]
        print("found running pod:", pod)

    print("\nshell:")
    launch_pod_shell(namespace, pod)


if __name__ == "__main__":
    _parser = argparse.ArgumentParser(description="A small cli script to quickly and easily get a shell for any pod of any kubernetes container. Written and tested for TrueNAS Scale Dragonfish 24.04", epilog=f"{__disclaimer__}")
    _parser.add_argument("app_name", type=str, help="name of the kubernetes container")
    _parser.add_argument("--search", choices=["contains", "startswith", "equals"], default="contains", required=False, help="container name search method (default: %(default)s)")
    _parser.add_argument("-s", choices=["c", "s", "e"], default=None, required=False, help="[short variant of --search]")
    _parser.add_argument("--show-commands", action="store_true", default=False, required=False, dest="show_commands", help="display the ran commands to get the shell")
    _args = _parser.parse_args()
    
    search_variant = _args.search
    if _args.s is not None:
        search_variant = _args.s
    main(_args.app_name, search_variant=search_variant)
