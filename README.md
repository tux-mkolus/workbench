# workbench

## Objetivo

**Armar una red que simule tanto las LAN como WANs de un cliente**, con las IPs reales, para facilitar las pruebas que se necesitan en la migración de un router.

## Funcionamiento

Vamos a **suponer** el caso de una **migración de Mikrotik a FortiGate**, con un cliente que tiene esta red:
 
 - LAN: 192.168.1.0/24
   - Gateway: 192.168.1.1
   - Webserver: 192.168.1.10
 - WAN: 168.121.37.30/24
   - Gateway: 168.121.37.1
   - Webserver publicado en los ports 80 y 443
 
Para simular la WAN usaremos 192.168.37.0/24.
 
En todo momento se usará el el FortiGate destino las direcciones IP reales en todas las interfaces.
 
Para el caso de las **WANs** hay que tener en consideración que **no podemos poner en este FortiGate una IP de WAN y accederla desde nuestra red ya que, al ser de WAN, el tráfico saldrá a internet**. Esto se resuelve *mapeando* las WANs en otra red cuyo rango esté en nuestra LAN.
 
Por ejemplo, supongamos que en la WAN el FortiGate usa 168.121.37.30/24, con gateway 168.121.37.1. Para la simulación de esa WAN usamos 192.168.37.0/24. El router que *simule* el entorno de cliente tendrá configurada una regla que diga que cualquier tráfico entrante a 192.168.37.0/24 se *NATeará* a 168.121.37.0/24 y viceversa. Con esto, para acceder el FortiGate simplemente usamos la IP 192.168.37.30.
 
Esto facilita mucho el testeo de la publicación servicios a Internet. Siguiendo el ejemplo anterior, para publicar una página web:
 
 - Creamos *virtual ips* en el FortiGate que pasen tráfico de 168.121.37.30 puertos 80 y 443 a un servidor interno, digamos, 192.168.1.10.
 - Creamos las policies que permiten el tráfico.
 - Ponemos un sniffer en el FortiGate para la IP destino 192.168.1.10.
 - Generamos tráfico, si lo vemos pasar en el sniffer la publicación funciona.

## Requisitos

- **Router Mikrotik** con al menos dos puertos ethernet libres, de ahora en más **lo llamaremos simulador**.
- **Rango de red** que no esté en uso, de ahora en más será **rango mapeado**.
- **Switch con soporte de VLANS**. *Nota: no hace falta un switch, alcanza con que sea "algo" que soporte VLANs*

## Estructura

Los dos puertos quedan configurados así:

- Puerto afectado a la simulación: habrá una VLAN por cada rango de red simulado, incluyendo las WANs.
- Puerto de acceso: 
  - Salida a Internet del simulador.
  - Es el que tiene el rango mapeado y se usa para acceder las WANs de la simulación.

## Modo de uso

El script genera una configuración que queda así:
 
### Puerto de acceso

- IP de nuestro router hacia LAN: 192.168.37.1/24
- IP del simulador: 192.168.37.200/24 (es una IP en desuso para lograr que salga a Internet por su cuenta).

### Puerto de simulación

 Va en modo trunk.
 
- VLAN 1000: LAN cliente
- VLAN 1001: WAN cliente

Estas VLANs deben configurarse manualmente en el switch.
 
### NAT

- Cualquier cosa dirigida a 192.168.37.0/24 se reescribe a 168.121.37.0/24
- Cualquier cosa que salga desde 168.121.37.0/24 se reescribe a 192.168.37.0/24

### LAN

- El simulador tendrá la IP 192.168.1.10 en la VLAN 1001 para simular la existencia del webserver.

## Simulación

Cuando necesitemos meter un equipo en la red del cliente, configuramos un puerto del switch en la VLAN 1000 y simplemente conectamos el cable de red.

Por el momento, los servers solo se emulan con la presencia de la IP en la red del server (usualmente la LAN). Solo se puede verificar que el paquete llegue.
 
## Configuración

### Sección: trunk

#### interface: INTERFACE

Interface del mikrotik donde se crearán las VLANs que simulan las LANs interna del cliente.

#### Ejemplo

```
[trunk]
interface = ether1
```

### Sección: uplink

#### interface: INTERFACE

Interface del Mikrotik que conecta a nuestra red e Internet. Sobre esta interface se crean las IPs que mapean a las WANs simuladas.

#### address: {dhcp|IP/MASCARA}

Configurar la dirección IP por DHCP o con IP/MÁSCARA en formato CIDR. En caso de configurarla fija, se requiere la opción **gateway**

#### gateway: IP

Dirección IP del default gateway en caso de que se configure IP fija.

#### Ejemplo

```
[uplink]
address = 172.20.3.100
gateway = 172.20.3.1
```

### Secciones: lans y wans

#### interfaces: INTERFACE [, INTERFACE ...]

Especifican los nombres de las secciones de configuración con los datos de las LANs y WANs simuladas. Por cada una que se especifique debe existir una sección de configuración con el mismo nombre.

#### Ejemplo

```
[lans]
interfaces = lan-usuarios, lan-servidores

[wans]
interfaces = wan-teco, wan-claro
```

### Secciones interfaces LAN

#### vlan: VLAN

VLAN id de la red. Con este id se enviarán los paquetes al puerto configurado como trunk. La idea es conectar ese puerto a un switch *-o algo que soporte VLANs-* en modo troncal, y luego en ese switch configuran puertos en esa VLAN en modo acceso. De esta forma pueden conectar equipos como si estuvieran en ese rango IP.

#### description: DESCRIPCION

**OPCIONAL**.

Descripcion de la interface.

#### address: IP/MASCARA

**OPCIONAL**.

Dirección IP y máscara de la interface.

#### dhcp server: {yes|no}

**OPCIONAL**.

Habilita un DHCP server en la interface. Requiere que se configure una dirección IP en la misma. El pool tendrá todas las direcciones del scope excepto la IP configurada en la interface. Si se requiere otra cosa, configurar manualmente.

#### dhcp server dns: DNS_SERVER [, DNS_SERVER ...]

**OPCIONAL**.

Listado de servidores DNS que va a pasar el DHCP server.

#### dhcp server gateway: IP

**OPCIONAL**.

Dirección IP del default gateway. Usar solo en caso de que sea diferente a la IP configurada en la interface.


#### dhcp server domain: DOMINIO

**OPCIONAL**.

Dominio DNS que pasará el DHCP server a los clientes.

#### Ejemplo

```
[lan-usuarios]
address = 192.168.0.1/24
vlan = 1000
description = LAN Usuarios
dhcp server = yes
dhcp dns = 8.8.8.8, 8.8.4.4
dhcp domain = usuarios.dominio.com.ar

[lan-servidores]
vlan = 1001
description = LAN Servidores
```