This page describes the technical details for participation in Academy CTF. If you're looking for a guide on how to get the Vulnbox running, have a look at Basic Vulnbox Hosting.

---
# Vulnbox

The Vulnbox image will be available as an x86-64 image in OVA format. This means it should run on your own hardware in VirtualBox, QEMU/KVM and other hypervisors. The image will be directly bootable without decryption. We recommend giving your VM at least 4 CPUs and 8 GB of RAM. Support for hardware virtualization (VT-x) is highly recommended.

A test image to check your virtualization setup (even before the Vulnbox image is released) will be available. To also check your networking setup, the VPN will be online as soon as the test image is available.

# Final Vulnbox

Final vulnbox, which will be used for the actual game is now available to download. There were a few bug fixes and QOL improvements.

Changelogs:

- changed from 20GB to 40GB cuz its hard to resize partition after its already being used
- fixed sshd_config
- added new setup-vulnbox.py that also sets up exploitfarm for you.

Download available here: [Final Vulnbox](https://x3ero0.dev/uploads/vulnbox.ova)

Default credentials for the vulnbox is `vulnbox:vulnbox123`. Reach out to `x3ero0` or `alchemy1729` if there are any issues.

This vulnbox should also clone and setup scripts to control Exploitfarm, You just have to setup Tulip and configure Exploitfarm.

**DO NOT FORGET TO SET PASSWORD AUTH ON YOUR EXPLOITFARM UI RUNNING ON PORT 5050**


## How to setup tulip (The easy way?)

I have made a fork of Tulip and added a bunch of install scripts, all you have to do is run ``python3 setup_tulip.py`` and put in your team id and team ip. Thats it.

When the actual game starts, I can add all the services and their port in the configuration script and you guys can do a ``git pull`` and rerun tulip, thats it.


    git clone https://github.com/X3eRo0/tulip
    cd tulip
    python3 setup_tulip.py
    sudo ./start_capture.sh # this starts tcpdump
    ./start_tulip.sh


# Test Vulnbox

The test vulnboxes are now available to download at [vulnbox.ova](https://x3ero0.dev/uploads/vulnbox-ubuntu24.04.ova)

We're created a tutorial/demo on how to setup the vulnbox at 00:08:00 mark. 
<iframe width="560" height="315" src="https://www.youtube.com/embed/_yGP5HxubWQ?si=fldlyWK_ljeoPD9P" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>

To start a test vulnbox, 

- Follow the tutorial to download and setup the VM. 
- Create a test account on x3ero0.dev (registration for testing purposes is open. The site will be reset later on)
- Ping `x3ero0` or `alchemy1729` and ask them to generate your VPN configs. Once they are generated, they should be available in your Team Downloads.
- Download [cowsay](https://x3ero0.dev/uploads/cowsay.tar.gz) service and setup the service and test if everything is working as intended.
- We are running out own test vulnbox at 10.32.1.2 and you can test your exploits and flag submissions using out test vulnbox.
- You can also test your traffic analyser tools such as [Tulip: Network analysis tool for Attack Defence CTF](https://github.com/OpenAttackDefenseTools/tulip) and exploit shooters such as [ExploitFarm](https://github.com/pwnzer0tt1/exploitfarm).

Default credentials for the vulnbox is `vulnbox:vulnbox123`. Reach out to `x3ero0` or `alchemy1729` if there are any issues.

Test Vulnbox: [vulnbox.ova](https://x3ero0.dev/uploads/vulnbox-ubuntu24.04.ova)

Cowsay service: [cowsay](https://x3ero0.dev/uploads/cowsay.tar.gz)

# Network

A WireGuard VPN config will be released which should be used in your Vulnbox (not your host) to connect it to the Gameserver. This VPN allows your vulnbox to be connected to the gameserver and other teams. so, it is very important to run the VPN during the competition otherwise you may loose SLA points.

You will find VPN configs containing the required secrets in the Downloads page of your team. 

## Vulnbox VPN

Connecting to this VPN is required. It provides access to the competition network for your Vulnbox, and optionally also your team.

We have no firewall in place to filter access to the Vulnbox network, so other teams can access the whole network unrestrictedly. This means that when also using it for team members' machines, you probably want to apply your own filtering.

The Vulnbox VPN uses WireGuard with a single peer per team. This means that it's only suitable for connecting two hosts with each other and cannot be used to connect additional machines to the competition network, such as physically distanced players. Use the player VPN config for that.

You can check the VPN connection on your personal VPN Status History page.

### Setup VPN on the vulnbox
1. Download `wg-ctf.conf` from [Team Downloads](/downloads/)
2. scp it to the vulnbox `scp <filename> vulnbox@192.168.56.10:<path on vulnbox>`
3. Enable a system ctl service to start the VPN on boot. This means no manual effort to start VPN everytime the vulnbox is restarted.
   
   - To enable VPN service: `systemctl enable wg-quick@wg-ctf`
   - To manually start VPN: `systemctl start wg-quick@wg-ctf`
   - To manually stop VPN: `systemctl stop wg-quick@wg-ctf`
   - To check VPN status: `systemctl status wg-quick@wg-ctf`
4. Your VPN is all done!!!

## Player VPN

The player VPN allows individual team members to connect to the team's own Vulnbox and the rest of the competition network.

It can be used in both on-site and remote setups, however, each player will have to use OpenVPN on their individual machine. Multiple connections can be made using the same player VPN config file.

All players should use openvpn to connect their HOST machines to the game network, and it's as easy as installing OpenVPN on your machine and using the provided `player.ovpn` from [Team Downloads](/downloads/) and connecting using this config.

### OpenVPN on Windows/Mac
1. Download and install the client from [https://openvpn.net/client/](https://openvpn.net/client/)
2. Download `player.ovpn` from [Team Downloads](/downloads/)
3. Import or Upload from file and choose player.ovpn
4. Continue until the connection is established
5. Reach out to `x3ero0` on discord if anything goes wrong.

### OpenVPN on Ubuntu/Linux
You can also use your Network Manager to connect to the VPN or you can do the following steps.

1. Install openvpn through apt or any other package manager `sudo apt install openvpn`
2. Download `player.ovpn` from [Team Downloads](/downloads/)
3. run `sudo openvpn --config <path to player.ovpn>` and keep it running in background.
4. Reach out to `x3ero0` on discord if anything goes wrong.

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

Flag submission is possible using a plaintext protocol on submission.x3ero0.dev:6666 from within the competition network. The protocol is specified in the CTF Gameserver documentation.

# Flag Format

Flags match this regular expression: FLAG_[A-Za-z0-9/+]{32}

# Service Status

The Gameserver's checks for the functioning of a service have one of these results:

- up: Everything is working fine
- flag not found: The service seems to be working, but flags from past ticks cannot be retrieved
- recovering: Flags from more recent ticks can be retrieved, but (still valid) flags from previous ticks are missing
- faulty: The service is reachable, but not working correctly
- down: The service is not reachable at all, e.g. because the port is closed or a timeout occurred

