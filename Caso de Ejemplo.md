# Ejemplo

## Cliente

- Compró un FortiGate 100F, de aquí solo nos interesan los puertos **port1 a port3, wan1 y wan2**.
- Tiene un Mikrotik configurado así:
    - ether1: LAN 192.168.0.1/24
    - ether2: DMZ 192.168.1.1/24
    - ether3: Servers 192.168.2.1/24
    - ether4: WAN1 20 mbps 168.121.37.30/24, gateway: 168.121.37.1
    - ether5: WAN2 50 mbps 186.138.64.106/29, gateway: 186.138.64.105
- Las WANs tienen configuración estática.
- Su Mikrotik oficial de DHCP server en las ether1, ether2 y ether3, por lo que no necesitaremos configurar uno nosotros.

## ¿Qué necesitamos?

- Leer el manual antes de seguir con esta lista :)
- **5 VLANs**, cada una corresponderá a cada conexión del Mikrotik que estamos migrando.
    - PRO TIP: Es conveniente tener creado un *stock* de VLANs siempre, ej: 4 para LANs, 4 para WANs, así no hay que borrarlas y volver a crearlas por cada cliente.
- **2 ports por cada conexión LAN**, **1 port por cada conexión WAN**.
    - *NOTA*: como las LAN las vamos a probar, en un puerto asignado a una LAN vamos a conectar el futuro router (el que estamos configurando) y en el otro puerto vamos a conectar la PC para hacer las pruebas, por eso necesitamos dos.
- Un **rango de red** que usaremos para mapear (dst-nat + src-nat) las IPs de WAN1 y WAN2. El script está preparado para usar un rango aparte, no uno existente, la idea es que no haya conflictos con nuestra LAN.
    - PRO TIP: Se puede usar un rango de interfaz virtual de metarouter.

## Planificando

### Ports y VLANS

| VLAN | Propósito | Port |
| ---- | --------- | ---- |
| 1001 | Red LAN 192.168.0.1/24 | 1, 2
| 1002 | Red DMZ 192.168.1.0/24 | 3, 4
| 1003 | Red Servers 192.168.2.1/24 | 5, 6
| 1004 | Red WAN1 168.121.37.30/24 | 7
| 1005 | Red WAN2 186.138.64.106/29| 8
| 1001-1005 | troncal | 9

Creamos esas VLANs y configuramos los puertos según la tabla.

### Mapeos

Usaremos un truco de *NAT* para *comunicarnos con las IP de WAN 168.121.37.30 y 186.138.64.106 usando el rango 192.168.11.0/24*. Para hacerlo simple:

- 192.168.11.30 -> 168.121.37.30
- 192.168.11.106 -> 186.138.64.106

### Metarouter

Para no usar un puerto físico aprovecharemos un *MetaRouter* que tendrá una *pata* hacia el Mikrotik real en nuestra LAN, usando una interfaz virtual. Para los fines de documentación asumiremos que esta interfaz es ether1 del lado del router virtual. El *Mikrotik real*, que oficiará de *gateway a Internet*, tendrá la IP *192.168.11.1* mientras que el *router virtual* -que hace toda la magia para emular el entorno del cliente- tendrá *192.168.11.2*.

En el caso del **troncal** que va al switch **necesitamos una física** (también asignada al *MetaRouter*), haremos de cuenta que es **ether4 en el Mikrotik real**, **ether2 en el virtual**.

### Archivo de configuración

`[trunk]
interface=ether2

[uplink]
interface = ether1
address = 192.168.11.2/24
gateway = 192.168.11.1

[lans]
interfaces = ex-ether1, ex-ether2, ex-ether3

[wans]
interfaces = wan-lemmon, wan-iplan

[ex-ether1]
vlan = 1001
description = ether1 - LAN 192.168.0.1/24

[ex-ether2]
vlan = 1002
description = ether2 - DMZ 192.168.1.1/24

[ex-ether3]
vlan = 1003
description = ether3 - Servers 192.168.2.1/24

[wan-lemmon]
address = 181.13.142.1/29
vlan = 1004
description = Lemmon 168.121.37.30/24 
map = 192.168.11.30:168.121.37.30

[wan-iplan]
address = 186.138.64.105/29
vlan = 1005
description = Iplan 186.138.64.106/29
map = 192.168.11.106:186.138.64.106
`

### Ejecutando el script

Al ejecutar el script con los parámetros `--config archivo.conf --output archivo.rsc`, debería generar este script:

`
# Uplink interface
/ip address add interface=ether1 address=192.168.11.2/24 comment="workbench"
/ip route add distance=1 gateway=192.168.11.1 comment="workbench"

# LAN: ex-ether1
/interface vlan add interface=ether2 name=ex-ether1 vlan-id=1001 comment="workbench/ether1 - LAN 192.168.0.1/24"

# LAN: ex-ether2
/interface vlan add interface=ether2 name=ex-ether2 vlan-id=1002 comment="workbench/ether2 - DMZ 192.168.1.1/24"

# LAN: ex-ether3
/interface vlan add interface=ether2 name=ex-ether3 vlan-id=1003 comment="workbench/ether3 - Servers 192.168.2.1/24"

# WAN: wan-lemmon
/interface vlan add interface=ether2 name=wan-lemmon vlan-id=1004 comment="workbench/Lemmon 168.121.37.30/24"
/ip address add address=181.13.142.1/29 comment="workbench/Lemmon 168.121.37.30/24" interface=wan-lemmon network=181.13.142.0

# map 192.168.11.30 to 168.121.37.30/32
/ip address
add address=192.168.11.30/24 comment="workbench/map 192.168.11.30 to 168.121.37.30/32" interface=ether1
/ip firewall nat add action=dst-nat chain=dstnat comment="workbench/map 192.168.11.30 to 168.121.37.30/32" dst-address=192.168.11.30 in-interface=ether1 to-addresses=168.121.37.30/32
/ip firewall nat add action=src-nat chain=srcnat comment="workbench/map 192.168.11.30 to 168.121.37.30/32" src-address=168.121.37.30/32 to-addresses=192.168.11.30

# WAN: wan-iplan
/interface vlan add interface=ether2 name=wan-iplan vlan-id=1005 comment="workbench/Iplan 186.138.64.106/29"
/ip address add address=186.138.64.105/29 comment="workbench/Iplan 186.138.64.106/29" interface=wan-iplan network=186.138.64.104

# map 192.168.11.106 to 186.138.64.106/32
/ip address
add address=192.168.11.106/24 comment="workbench/map 192.168.11.106 to 186.138.64.106/32" interface=ether1
/ip firewall nat add action=dst-nat chain=dstnat comment="workbench/map 192.168.11.106 to 186.138.64.106/32" dst-address=192.168.11.106 in-interface=ether1 to-addresses=186.138.64.106/32
/ip firewall nat add action=src-nat chain=srcnat comment="workbench/map 192.168.11.106 to 186.138.64.106/32" src-address=186.138.64.106/32 to-addresses=192.168.11.106
`

Lo ejecutamos en nuestro *MetaRouter* y todo listo.

### Conectando el router

Siguiendo **lo que planificamos** con los ports y VLANS, conectamos las cosas así:

| Dispositivo | Port | Switch Port |
| ----------- | ---- | ----------- |
| Mikrotik | ether4 | 9 |
| FortiGate | port1 | 1 |
| FortiGate | port2 | 3 | 
| FortiGate | port3 | 5 |
| FortiGate | wan1 | 7 | 
| FortiGate | wan2 | 8 |

### ¡Listo!

Ya tenemos todo para empezar a configurarlo y probarlo.
