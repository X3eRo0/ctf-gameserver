<iframe width="560" height="315" src="https://www.youtube.com/embed/RkaLyji9pNs?si=5Ii4eX0kCr6TijCn" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>


---

A typical attack/defense CTF consists of three components:

## The Gameserver

It is provided by the organizers and runs throughout the competition, starting when the network is opened. It periodically stores flags on your Vulnbox using functionality in the provided services. It then later retrieves these flags, again using existing functionality. The Gameserver does *not* run exploits! It simply uses the service as intended.

> **Now, why can't the other teams then simply do what the Gameserver does?**

The Gameserver has more information. Every service is either designed to allow the Gameserver to store a specific token for each flag or generates one and returns it to the Gameserver.

The Gameserver uses this token to check periodically that the flag is still there. Whether or not it gets the stored flag using that token determines your SLA (Service Level Agreement). You **mustn't** remove or break any legitimate functionality.

Some services can have a vulnerability that directly leaks the flag, which will let you retrieve the flag easily. For others, it will require more effort.

---

## Your Vulnbox

The Vulnbox is your running instance of the virtual machine image given to you by the organizers. It contains and runs all the services of the competition and should be reachable at all times. The Gameserver stores its flags here and uses the communication with this machine to decide if your services are working as intended or not. This machine is accessible to everyone on the network, and is the target for all the exploits from other teams.

Protecting the flags on this machine is what determines your **defense points!**

You normally have one hour from getting the decryption password of the services until the network between teams is opened and everyone can attack each other. Use this time to decrypt the services and start analyzing what's running on your VM. It has happened that services with vulnerabilities that are easy to find have been exploited as soon as the actual competition starts.

---

## The Other Teams

All the other registered teams are connected to the same VPN as you. Their Vulnboxes have known IP addresses; all other machines are off-limits! The other teams will run exploits from their own machines, but the VPN infrastructure will use NAT to obfuscate whether a packet came from the Gameserver or another team.

Successfully stealing and submitting flags from the Vulnbox of other teams determines your **attack score!**

If you have played Jeopardy-style CTFs before, you already know flag submission. In this game, however, you’ll have to run your exploits periodically, as new flags get stored by the Gameserver every few minutes. So you probably want to script exploits and submit flags automatically and avoid spending all your time manually exploiting everyone.


---
This page was adapted from [faustctf2024](https://2024.faustctf.net/information/attackdefense-for-beginners/)
