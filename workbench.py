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

# create dhcp pool excluding gateway address
def dhcp_pool (address, network):
    if network[1] == address:
        # gateway is in the first ip
        return([ (network[2], network[-2])])
    elif network[-2] == address:
        # gateway is in the last ip
        return([ (network[1], network[-3])])
    else:
        gateway_offset = list(network).index(address)
        return([
            (network[1], network[gateway_offset-1]),
            (network[gateway_offset+1], network[-2])
        ])

# create IP pools
def create_ip_pool(basename, pools):
    pool_script = ""
    if len(pools) == 1:
        pool_script += "/ip pool add name={interface}_pool0 ranges={ranges} comment=\"workbench\"\n".format(
            interface=basename,
            ranges=mktrange(pools[0][0], pools[0][1])
        )
    else:
        pool_script += "/ip pool add name={interface}_pool1 ranges={ranges} comment=\"workbench\"\n".format(
            interface=basename,
            ranges=mktrange(pools[1][0], pools[1][1])
        )

        pool_script += "/ip pool add name={interface}_pool0 next-pool={interface}_pool1 ranges={ranges} comment=\"workbench\"\n".format(
            interface=basename,
            ranges=mktrange(pools[0][0], pools[0][1])
        )

    return(pool_script)

# create dhcp server script
def dhcp_server (interface, address, network):
    dhcp_server = dict()
    dhcp_log = ""
    dhcp_script = ""

    # default gateway
    dhcp_server["gateway"] = address

    # address pools
    dhcp_server["pools"] = dhcp_pool(address, network)

    # dns servers
    if config.has_option(interface, "dhcp dns"):
        dhcp_server["dns servers"] = [ ipaddress.ip_address(x) for x in csl(config[interface]["dhcp dns"])]
        dhcp_log += " dns servers={dns_servers}".format(
            dns_servers = ",".join([str(x) for x in dhcp_server["dns servers"]])
        )

    # dns domain
    if config.has_option(interface, "dhcp domain"):
        dhcp_server["domain"] = config[interface]["dhcp domain"]
        dhcp_log += " dns domain={domain}".format(
            domain=dhcp_server["domain"]
        )        

    # DHCP Server Config Script
    dhcp_script += "\n# WAN: {interface} DHCP Server\n".format(
        interface=interface
    )

    dhcp_script += create_ip_pool(interface, dhcp_server["pools"])

    dhcp_log += " pools={pools}".format(
        pools = ",".join([mktrange(x[0], x[1]) for x in dhcp_server["pools"]])
    )

    dhcp_script += "/ip dhcp-server add address-pool={interface}_pool0 bootp-support=none disabled=no interface={interface} lease-time=1h name={interface}_server comment=\"workbench\"\n".format(
        interface=interface
    )

    dhcp_script += "/ip dhcp-server network add address={network} {dns_server}{domain} gateway={gateway} netmask={prefixlen} comment=\"workbench\"\n".format(
        network=network,
        dns_server = ("dns-server=" + (",".join(dhcp_server["dns servers"]))) if "dns_servers" in dhcp_server else "",
        domain="domain=" + dhcp_server["domain"] if "domain" in dhcp_server else "",
        gateway=dhcp_server["gateway"],
        prefixlen=network.prefixlen
    )

    log("\tdhcp server: {dhcp_log}".format(
        dhcp_log=dhcp_log
    ))

    return(dhcp_script)

# convert cidr string to ip address and network
def cidr_to_ip_network(addr):
    return(
        ipaddress.ip_address(addr.split("/")[0]),
        ipaddress.ip_network(addr, strict=False)
    )

# convert network address to ip address list
def network_to_ip_list(network: str, strict: bool=True):
    if "/" in network:
        # network address
        try:
            mapped_addrs = list(ipaddress.ip_network(network, strict=strict))
        except ValueError:
            log("network_to_ip_list(): invalid network address: {mapped_expr}".format(
                mapped_expr=network
            ))
            return(None)
    else:
        # ip address
        try:
            mapped_addrs = [ ipaddress.ip_address(network) ]
        except ValueError:
            log("network_to_ip_list():: {mapped_expr}".format(
                mapped_expr=network
            ))
            return(None)
    
    return(mapped_addrs)

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

log("reading configuration file '{config}'".format(
    config=args.config
))

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
    log("created output file {output_filename}".format(
        output_filename=output_filename
    ))    
except:
    log("can't create output file {output_filename}, aborting.".format(
        output_filename=output_filename
    ))
    sys.exit(-1)

# Uplink
o.write("# Uplink interface\n")

if config["uplink"]["address"] == "dhcp":
    o.write("/ip dhcp-client add disabled=no interface={uplink} comment=\"workbench\"\n".format(
        uplink=config["uplink"]["interface"] 
    ))
    log("configured uplink interface {uplink}: dhcp client".format(
        uplink=config["uplink"]["interface"] 
    ))
else:
    (ul_ip, ul_network) = str2ipnetwork(config["uplink"]["address"])
    o.write("/ip address add interface={uplink} address={address}/{netmask} comment=\"workbench\"\n".format(
        uplink=config["uplink"]["interface"],
        address=ul_ip,
        netmask=ul_network.prefixlen
    ))

    if "gateway" in config["uplink"]:
        (gw_ip, gw_network) = str2ipnetwork(config["uplink"]["gateway"])

        o.write("/ip route add distance=1 gateway={gateway} comment=\"workbench\"\n".format(
            gateway=gw_ip
        ))

    log("configured uplink interface {uplink}: address={address}/{prefixlen} gateway={gateway}".format(
        uplink=config["uplink"]["interface"],
        address=ul_ip,
        prefixlen=ul_network.prefixlen,
        gateway=gw_ip if "gateway" in config["uplink"] else "none"
    ))    

# LAN: layer 2/3 configuration
trunk_interface = config["trunk"]["interface"]
used_vlans = set()

for lan_interface in csl(config["lans"]["interfaces"]):
    log("configuring lan interface '{lan_interface}'".format(
        lan_interface=lan_interface
    ))

    o.write("\n# LAN: {lan_interface}\n".format(
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
        comment = " comment=\"workbench/" + config[lan_interface]["description"] + "\""
    else:
        comment = "comment=\"workbench\""

    used_vlans.add(vlan_id)

    # VLAN interface
    o.write("/interface vlan add interface={trunk} name={interface} vlan-id={vlan_id}{comment}\n".format(
        trunk=trunk_interface,
        interface=lan_interface,
        vlan_id=vlan_id,
        comment=comment
    ))

    log("\tvlan id {vlan_id}".format(
        vlan_id=vlan_id
    ))

    # LAN interface address
    if config.has_option(lan_interface, "address"):
        (address, network) = cidr_to_ip_network(config[lan_interface]["address"])

        o.write("/ip address add address={ip}/{netmask}{comment} interface={interface} network={network}\n".format(
            ip=address,
            netmask=network.prefixlen,
            comment=comment,
            interface=lan_interface,
            network=network.network_address
        ))

        log("\taddress={ip}/{netmask} network={network}{comment}".format(
            ip=address,
            netmask=network.prefixlen,
            network=network.network_address,
            comment=comment            
        ))

        # DHCP Server
        if config.has_option(lan_interface, "dhcp server"):

            # default gateway
            if config.has_option(lan_interface, "dhcp gateway"):
                gateway = ipaddress.ip_address(config[lan_interface]["dhcp gateway"])
            else:
                gateway = address
            
            o.write(dhcp_server(lan_interface, gateway, network))
            
# WAN: layer 2/3 configuration
for wan_interface in csl(config["wans"]["interfaces"]):
    log("configuring wan interface '{wan_interface}'".format(
        wan_interface=wan_interface
    ))

    o.write("\n# WAN: {wan_interface}\n".format(
        wan_interface=wan_interface
    ))

    # optional description
    if config.has_option(wan_interface,"description"):
        comment = " comment=\"workbench/" + config[wan_interface]["description"] + "\""
    else:
        comment = " comment=\"workbench\""

    # vlan 
    vlan_id = int(config[wan_interface]["vlan"])
    if vlan_id in used_vlans:
        log("vlan id {vlan_id} already used".format(
            vlan_id=vlan_id
        ))
        sys.exit(-1)

    # VLAN interface
    o.write("/interface vlan add interface={trunk} name={interface} vlan-id={vlan_id}{comment}\n".format(
        trunk=trunk_interface,
        interface=wan_interface,
        vlan_id=vlan_id,
        comment=comment
    ))

    # wan types
    if not config.has_option(wan_interface,"type") or config[wan_interface]["type"] == "static":
        # static address
        (address, network) = cidr_to_ip_network(config[wan_interface]["address"])
        o.write("/ip address add address={ip}/{netmask}{comment} interface={interface} network={network}\n".format(
            ip=address,
            netmask=network.prefixlen,
            comment=comment,
            interface=wan_interface,
            network=network.network_address
        ))
    elif config.has_option(wan_interface, "type"):
        if config[wan_interface]["type"] == "dhcp":
            # dhcp addressing
            (address, network) = cidr_to_ip_network(config[wan_interface]["address"])
            o.write("/ip address add address={ip}/{netmask}{comment} interface={interface} network={network}\n".format(
                ip=address,
                netmask=network.prefixlen,
                comment=comment,
                interface=wan_interface,
                network=network.network_address
            ))

            # DHCP Server
            o.write(dhcp_server(wan_interface, address, network))
        elif config[wan_interface]["type"] == "pppoe":
            # pppoe
            (address, network) = cidr_to_ip_network(config[wan_interface]["pppoe gateway"])
            # ip pools
            o.write(create_ip_pool(wan_interface, dhcp_pool(address, network)))
            # ppp profile
            o.write("/ppp profile add change-tcp-mss=yes local-address={address} name={interface}_profile remote-address={interface}_pool0 use-encryption=yes{comment}\n".format(
                interface=wan_interface,
                comment=comment,
                address=address
            ))
            # ppp secret
            o.write("/ppp secret add name=\"{username}\" password=\"{password}\" profile={interface}_profile service=pppoe{comment}\n".format(
                interface=wan_interface,
                username=config[wan_interface]["pppoe user"],
                password=config[wan_interface]["pppoe password"],
                comment=comment
            ))
            # pppoe server
            o.write("/interface pppoe-server server add default-profile={interface}_profile disabled=no interface={interface} service-name={interface}{comment}\n".format(
                interface=wan_interface,
                comment=comment
            ))

    if config.has_option(wan_interface, "map"):
        ip_mapping = csl(config[wan_interface]["map"])
        for mapping in ip_mapping:
            # mapping expression validation
            (mapped_expr, wan_expr) = mapping.strip().split(":")
            mapped_addrs = network_to_ip_list(mapped_expr)
            wan_addrs = network_to_ip_list(wan_expr, strict=False)

            if mapped_addrs is None or wan_addrs is None:
                sys.exit(-1)

            wan_spec = str(ipaddress.ip_network(wan_expr, strict=False))

            if len(mapped_addrs) != len(wan_addrs):
                log("\tcannot map {mapped_expr} to {wan_expr}, aborting.".format(
                    mapped_expr=mapped_expr,
                    wan_expr=wan_spec
                ))
                sys.exit(-1)

            comment="workbench/map {mapped_expr} to {wan_spec}".format(
                    mapped_expr=mapped_expr,
                    wan_spec=wan_spec                        
                )

            o.write("\n# map {mapped_expr} to {wan_spec}\n".format(
                    mapped_expr=mapped_expr,
                    wan_spec=wan_spec
                ))

            # address
            o.write("/ip address\n")
            for ip in mapped_addrs:

                o.write("add address={ip}/{network.prefixlen} comment=\"{comment}\" interface={interface}\n".format(
                    ip=ip,
                    comment=comment,
                    network=ul_network,
                    interface=config["uplink"]["interface"]
                ))

            # destination nat
            o.write("/ip firewall nat add action=dst-nat chain=dstnat comment=\"{comment}\" dst-address={mapped_expr} in-interface={interface} to-addresses={wan_spec}\n".format(
                mapped_expr=mapped_expr,
                wan_spec=wan_spec,
                comment=comment,
                interface=config["uplink"]["interface"]
            ))

            # source nat
            o.write("/ip firewall nat add action=src-nat chain=srcnat comment=\"{comment}\" src-address={wan_spec} to-addresses={mapped_expr}\n".format(
                mapped_expr=mapped_expr,
                wan_spec=wan_spec,
                comment=comment,
            ))                

log("done.")
o.close()