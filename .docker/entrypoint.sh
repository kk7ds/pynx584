#!/bin/bash
if [ -z "${SERIAL}" ]; then
    /srv/pynx584/.env/bin/nx584_server --listen 0.0.0.0 --serial $SERIAL --baudrate $BAUD
elif [ -z "${SOCKET}" ]; then
    /srv/pynx584/.env/bin/nx584_server --listen 0.0.0.0 --connect $SOCKET
fi;
