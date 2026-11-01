I want to build a script that can setup this server to run windows and macos VMs that can be remotely accessd via Cloudflare using RDP (windows) and Macos (VNC)

Cloudflare tunnel needs to be installed and cloudflare cloud needs to be configured using the APIs

We will use https://github.com/dockur/windows to run the windows VM and in this repo you can find how to setup the windows VMs https://github.com/soleng2018/docker-clients
We will alos install MACoSX as wired clients, but we want to use MAC VLANs. https://github.com/dockur/macos 
The docker containers will have two interfaces one for VNC management and the other wired and wireless
Both VMS's need a startup script so we can run them on fresh install. This ensures the device has the right software running. Since we have two interfaces on the device we need to ensure the USB or mavVLAN have higher weight
Do note that we dont need traefik and authentik is hosted externally. So this script will not need to worry about installed. Use docker-clients repo as reference and remove things like traefik labels
Cloudflare will need to re-direct users to these VMs. So once you get access to the API read exisitng Tunnel config for nova, CIDRs, targets, policies, etc as you will have to configure it using API'script
We will want a monitoring script that can monitor and recover the VMS and USB dongles.
On reboot the server needs to return to all VMs running correctly 
I want one single configuration and secrets file. It can be outside this dir but it has to be a single file that i can backup

Also the script should be able to work on an existing setup. If I want to add more clients i just update the configuration and it runs the delta not tocuhing things that are already running