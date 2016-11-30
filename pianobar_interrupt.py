from datetime import datetime
import re
import time
import subprocess
import sys
import requests
import os
import select

def get_pianobar_pid():
    ps_aux = subprocess.Popen("""ps -ef | awk '{if ($8 == "pianobar") print $2}'""", stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
    output = ps_aux.stdout.read().strip()
    return output

def get_last_timecode(filename):
    f = open(filename, mode='rb')
    # flush pipe
    r, w, e = select.select([ f ], [], [], 0)
    if f in r:
        os.read(f.fileno(), 4096)
    else:
        log( "nothing available!" ) # or just ignore that case

    #read 32 bytes off of pipe
    data = f.read(32)
    f.close()

    #tranform timecodes
    data =  [x for x in data.split('\r') if x.startswith('\x1b[2K#')]
    data = [x for x in data if re.search(' -[0-9][0-9]:[0-9][0-9]/[0-9][0-9]:[0-9][0-9]', x)]
    return data[-1]

def get_seconds_left_in_song(raw_timecode):
    try:
        timecode = raw_timecode.split('-')[1].split('/')[0]
        dt = datetime.strptime(timecode, '%M:%S')
        td = dt - datetime.strptime('0', '%S')
        seconds = td.total_seconds()
        return seconds
    except IndexError as e:
        log( e )

def log(msg):
    print '[{}] [{}] {}'.format(datetime.strftime(datetime.now(), '%F %T'), sys.argv[0], msg)

log("Started {}".format(sys.argv[0]))
station = sys.argv[1]
pianobar_pid = get_pianobar_pid()
log("Pianobar proc is {}".format(pianobar_pid))

if not pianobar_pid:
    log( "Pianobar not running." )
    sys.exit(2)

raw_timecode = get_last_timecode("/proc/{}/fd/1".format(pianobar_pid))
seconds_left = get_seconds_left_in_song(raw_timecode)
log( 'Sleeping for {} seconds...'.format(seconds_left) )

time.sleep(seconds_left-1)

log( 'Changing station to #{}'.format(station) )
requests.get("http://localhost:8080/home/{}".format(station))

log( "Finished {}".format(sys.argv[0]) )

