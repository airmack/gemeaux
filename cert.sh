#!/bin/bash
l=()
for i in `ip -o -6 addr show | sed -e 's/^.*inet6 \([^ ]\+\).*/\1/' | cut -d / -f1`
do
    l+=", IP:$i"
done

for i in `ip addr show | grep -Po 'inet \K[\d.]+'`
do
    l+=",IP:$i"
done
l+=",DNS:`cat /etc/hostname`"
echo "Generating for $l"


openssl req -new -x509 -days 365 -nodes -out cert.pem -keyout key.pem -subj "/CN=localhost" -newkey rsa:4096 -addext "subjectAltName = DNS:localhost$l"

