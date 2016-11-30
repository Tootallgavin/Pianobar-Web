#!/bin/bash

function log {
    echo -e "[$(date +%F\ %T)] $1"
}

function kickstart_pianobar {
    log "Kickstarting pianobar"
    curl -L http://localhost:8080/start/$1 > /dev/null
}

log "Started $0"

SCHEDULE_PATH="/root/.config/pianobar/schedule"
STATION_LIST_PATH="/root/.config/pianobar/station_list"
HOUR="$(date +%H)"
SCHED_LINE=$(egrep "^${HOUR}\|" $SCHEDULE_PATH )
SCHED_STATION_NAME=${SCHED_LINE##*|}
SCHED_STATION_NUM=$(egrep "\|${SCHED_STATION_NAME}$" $STATION_LIST_PATH | awk -F"|" '{print $1}')

log "The hour is: $HOUR"
log "The scheduled station is: $SCHED_STATION_NAME (#$SCHED_STATION_NUM)"

log "Running pianobar_interrupt.py"
python pianobar_interrupt.py $SCHED_STATION_NUM

if [[ $? -eq 2 ]]; then
    kickstart_pianobar $SCHED_STATION_NUM
fi

log "Finished $0"

