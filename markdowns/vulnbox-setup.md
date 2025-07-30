This page describes the technical details for participation in Academy CTF. If you're looking for a guide on how to get the Vulnbox running, have a look at Basic Vulnbox Hosting.

---
# Vulnbox

The Vulnbox image will be available as an x86-64 image in OVA format. This means it should run on your own hardware in VirtualBox, QEMU/KVM and other hypervisors. The image will be directly bootable without decryption. We recommend giving your VM at least 4 CPUs and 8 GB of RAM. Support for hardware virtualization (VT-x) is highly recommended.

A test image to check your virtualization setup (even before the Vulnbox image is released) will be available. To also check your networking setup, the VPN will be online as soon as the test image is available.

# Network

A WireGuard VPN config will be released which should be used in your Vulnbox (not your host) to connect it to the Gameserver. This VPN allows your vulnbox to be connected to the gameserver and other teams. so, it is very important to run the VPN during the competition otherwise you may loose SLA points.

You will find VPN configs containing the required secrets in the Downloads page of your team. 

## Vulnbox VPN

Connecting to this VPN is required. It provides access to the competition network for your Vulnbox, and optionally also your team.

We have no firewall in place to filter access to the Vulnbox network, so other teams can access the whole network unrestrictedly. This means that when also using it for team members' machines, you probably want to apply your own filtering.

The Vulnbox VPN uses WireGuard with a single peer per team. This means that it's only suitable for connecting two hosts with each other and cannot be used to connect additional machines to the competition network, such as physically distanced players. Use the player VPN config for that.

You can check the VPN connection on your personal VPN Status History page.

## Player VPN

The player VPN allows individual team members to connect to the team's own Vulnbox and the rest of the competition network.

It can be used in both on-site and remote setups, however, each player will have to use OpenVPN on their individual machine. Multiple connections can be made using the same player VPN config file.

The Vulnbox network and the player network have full access to each other, even before the start of the competition. But unlike on the Vulnbox network, hosts on the player VPN can not be accessed by other teams.
IP Ranges Overview

Graphic of network setup and IP ranges

Academy CTF will use only IPv4 within the competition network (Faust ctf uses ipv6 💀):

    Vulnbox VPN network
        10.32.<team-number>.1%wg-ctf: Competition gateway
        10.32.<team-number>.2%wg-ctf: Team vulnbox
        10.33.<team-number>.x%tun0: Player
    Team networks: 10.32.<team-number>.0/24
        Vulnbox network (VPN): 10.32.<team-number>.0/24
            Gateway (separate router machine): 10.32.<team-number>.1
            Vulnbox: 10.32.<team-number>.2
            Testing Vulnbox: 10.32.<team-number>.3
    Competition infrastructure: 10.32.<team-number>.0/32
        Gateways (each team assigned to one)
            10.32.1.1
            10.32.2.1
            10.32.3.1
            10.32.4.1
            10.32.5.1
        submission.x3ero0.dev

Note: <team-number> refers to the team number in decimal format, i.e. IP addresses are constructed using string interpolation and without hex encoding of the number. For example, the Vulnbox of team 123 will have the address 10.32.123.2.

# Teams JSON

We provide a list of all active teams under https://x3ero0.dev/competition/teams.json. The JSON contains assigned team numbers and flag ids, more information about both can be found below. The format is the following:

    {
        "teams": [123, 456, 789],
        "flag_ids": {
            "service1": {
                "123": ["abc123", "def456"],
                "789": ["xxx", "yyy"]
            }
        }
    }

## Team Numbers

Since team numbers (and therefore IP ranges) are assigned randomly, it is not obvious which team networks are actually assigned. All assigned team numbers can be found in the Teams JSON (see above).

# Flag IDs

Some (but not all) services come with flag IDs. Flag IDs are identifiers that help you access the flags that are still valid (like usernames or database IDs), without having to search through all of them. The current set of IDs will be provided in the Teams JSON (see above). Note that flag ids are only stored if the service is up and running. This might lead to active team numbers without flag ids.

# NOP Team

A mostly unaltered Vulnbox to check your exploits against will be available with team number 1 (i.e. IP 10.32.1.2). No vulnerabilities will be patched on this machine, but it will receive new flags (which of course won't be valid for submission) and be checked by the Gameserver.

# Exploitation

You run attacks against other teams from your infrastructure, using your own tools.

Flag submission is possible using a plaintext protocol on submission.x3ero0.dev:666 from within the competition network. The protocol is specified in the CTF Gameserver documentation.

# Flag Format

Flags match this regular expression: FLAG_[A-Za-z0-9/+]{32}

# Service Status

The Gameserver's checks for the functioning of a service have one of these results:

- up: Everything is working fine
- flag not found: The service seems to be working, but flags from past ticks cannot be retrieved
- recovering: Flags from more recent ticks can be retrieved, but (still valid) flags from previous ticks are missing
- faulty: The service is reachable, but not working correctly
- down: The service is not reachable at all, e.g. because the port is closed or a timeout occurred

