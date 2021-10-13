import argparse
import datetime
import ipaddress
import configparser
import os
from re import L
import sys

# logger
def log (message, level="INFO"):
    print("{date} {level:8s} {message}".format(
        date=datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        level=level,
        message=message
    ))

# comma separated list to python list
def csl (s):
    return([i.strip() for i in s.split(",")])

# str2ip
def str2ipnetwork (s):
    try:
        network = ipaddress.ip_network(s, strict=False)
        address = ipaddress.ip_address(s.split("/")[0])
    except:
        return(None, None)
    
    return(address, network)

# range expression optimizer
def mktrange (start, end):
    if start == end:
        return(str(start))
    else:
        return("{start}-{end}".format(
            start=start,
            end=end
        ))

# command line
parser = argparse.ArgumentParser(description="configurador de entornos simulados de red WAN y LAN")
parser.add_argument("--config", help="archivo de configuración", required=True)
parser.add_argument("--output", help="archivo .rsc a generar")

args = parser.parse_args()

# load config if exists
if not os.path.isfile(args.config):
    log("configuration file {config} not found, aborting.".format(
        config=args.config
    ), "CRITICAL")
    sys.exit(-1)

log("reading configuration file")

config = configparser.ConfigParser()
try:
    config.read(args.config)
except:
    log("error parsing configuration file, aborting.", "CRITICAL")
    sys.exit(-1)

# create output file
if args.output is not None:
    # specified
    output_filename = args.output
else:
    # based on the input file
    output_filename = args.config.rsplit(".", 1)[0] + ".rsc"

try:
    o = open(output_filename, "w", encoding="utf-8")
    log("created output file {output_filename}, aborting.".format(
        output_filename=output_filename
    ))    
except:
    log("can't create output file {output_filename}, aborting.".format(
        output_filename=output_filename
    ))
    sys.exit(-1)

# Uplink
log("configuring uplink interface")
o.write("# Uplink interface\n")

if config["uplink"]["address"] == "dhcp":
    o.write("/ip dhcp-client add disabled=no interface={uplink}\n".format(
        uplink=config["uplink"]["interface"] 
    ))
else:
    (ul_ip, ul_network) = str2ipnetwork(config["uplink"]["address"])
    (gw_ip, gw_network) = str2ipnetwork(config["uplink"]["gateway"])
    o.write("/ip address add interface={uplink} address={address}/{netmask}\n".format(
        uplink=config["uplink"]["interface"],
        address=ul_ip,
        netmask=ul_network.prefixlen
    ))
    o.write("/ip route add distance=1 gateway={gateway}\n".format(
        gateway=gw_ip
    ))

o.write("\n")

# LAN: layer 2/3 configuration
trunk_interface = config["trunk"]["interface"]
used_vlans = set()

for lan_interface in csl(config["lans"]["interfaces"]):
    log("configuring lan interface '{lan_interface}'".format(
        lan_interface=lan_interface
    ))

    o.write("# LAN: {lan_interface}\n".format(
        lan_interface=lan_interface
    ))
    
    # vlan 
    vlan_id = int(config[lan_interface]["vlan"])
    if vlan_id in used_vlans:
        log("vlan id {vlan_id} already used".format(
            vlan_id=vlan_id
        ))
        sys.exit(-1)

    # optional description
    if config.has_option(lan_interface,"description"):
        comment = " comment=\"" + config[lan_interface]["description"] + "\""
    else:
        comment = ""

    used_vlans.add(vlan_id)

    # VLAN interface
    o.write("/interface vlan add interface={trunk} name={interface} vlan-id={vlan_id}{comment}\n".format(
        trunk=trunk_interface,
        interface=lan_interface,
        vlan_id=vlan_id,
        comment=comment
    ))

    # LAN interface address
    if config.has_option(lan_interface, "address"):
        network = ipaddress.ip_network(config[lan_interface]["address"], strict=False)
        address = ipaddress.ip_address(config[lan_interface]["address"].split("/")[0])

        o.write("/ip address add address={ip}/{netmask}{comment} interface={interface} network={network}\n".format(
            ip=address,
            netmask=network.prefixlen,
            comment=comment,
            interface=lan_interface,
            network=network.network_address
        ))

        # DHCP Server
        if config.has_option(lan_interface, "dhcp server"):
            dhcp_server = dict()

            # default gateway
            if config.has_option(lan_interface, "dhcp gateway"):
                dhcp_server["gateway"] = config[lan_interface]["dhcp gateway"]
            else:
                dhcp_server["gateway"] = address
            
            # pools
            if network[1] == address:
                # gateway is in the first ip
                dhcp_server["pools"] = [ (network[2], network[-2])]
            elif network[-2] == address:
                # gateway is in the last ip
                dhcp_server["pools"] = [ (network[1], network[-3])]
            else:
                gateway_offset = list(network).index(address)
                dhcp_server["pools"] = [
                    (network[1], network[gateway_offset-1]),
                    (network[gateway_offset+1], network[-2])
                ]

            # dns
            if config.has_option(lan_interface, "dhcp dns"):
                dhcp_server["dns servers"] = [ ipaddress.ip_address(x) for x in csl(config[lan_interface]["dhcp dns"])]

            if config.has_option(lan_interface, "dhcp domain"):
                dhcp_server["domain"] = config[lan_interface]["dhcp domain"]

            # DHCP Server Config Script
            o.write("\n# LAN: {interface} DHCP Server\n".format(
                interface=lan_interface
            ))

            # Pools
            if len(dhcp_server["pools"]) == 1:
                o.write("/ip pool add name={interface}_pool0 ranges={ranges}\n".format(
                    interface=lan_interface,
                    ranges=mktrange(dhcp_server["pools"][0][0], dhcp_server["pools"][0][1])
                ))
            else:
                o.write("/ip pool add name={interface}_pool1 ranges={ranges}\n".format(
                    interface=lan_interface,
                    ranges=mktrange(dhcp_server["pools"][1][0], dhcp_server["pools"][1][1])
                ))

                o.write("/ip pool add name={interface}_pool0 next-pool={interface}_pool1 ranges={ranges}\n".format(
                    interface=lan_interface,
                    ranges=mktrange(dhcp_server["pools"][0][0], dhcp_server["pools"][0][1])
                ))

            # Server
            o.write("/ip dhcp-server add address-pool={interface}_pool0 bootp-support=none disabled=no interface={interface} lease-time=1h name={interface}_server\n".format(
                interface=lan_interface
            ))

            # Network
            o.write("/ip dhcp-server network add address={network} {dns_server}{domain} gateway={gateway} netmask={prefixlen}\n".format(
                network=network,
                dns_server = ("dns-server=" + (",".join(dhcp_server["dns servers"]))) if "dns_servers" in dhcp_server else "",
                domain="domain=" + dhcp_server["domain"] if "domain" in dhcp_server else "",
                gateway=dhcp_server["gateway"],
                prefixlen=network.prefixlen
            ))
            
    o.write("\n")

log("done.")
o.close()