# David Shure
# Pandora Bar (web interface for pianobar)

from bottle import *
import subprocess
import os
import signal
import time

proc = None
stations = {}
music_playing = True
current_station = ""
first_login = True
need_to_refresh_stations = True

email = ""
password = ""

# redirects to login
@get('/')
def index():
    redirect("/login")

# checks if we are already logged in
@get('/login')
def login():
    if proc is not None:
        redirect("/home")
    else:
        return template("login", error=None)

# gets rendered when we have an authenication error with pandora
@get('/login/<error>')
def login_error(error):
    return template("login", error=error)

# serves our static files, like CSS and javascript
@get('/static/<filename>')
def serve_static(filename):
    return static_file(filename, root="./static")

# authenticates credentials with pandora
@post('/auth')
def authenticate():
    global proc, email, password
    proc = None
    proc = subprocess.Popen("pianobar", stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    local_email = request.forms.get("email")
    local_password = request.forms.get("password")
    
    # Enter email and password when prompted
    proc.stdin.write(local_email + "\n")
    proc.stdin.write(local_password + "\n")

    auth = [proc.stdout.readline() for i in range(0, 4)][-1]

    proc.stdout.readline() # dicard the line '(i) Get stations..'

    # This is what the login success line looks like
    if auth == "\x1b[2K(i) Login... Ok.\n":
        email = local_email
        password = local_password
        redirect("/verify")
    else:
        # kill the process, it is useless to us
        proc.terminate()
        proc.wait()
        redirect("/login/auth")

# verifies no existing pianobar processes are running 
# besides those that were spawned by this user and prompts
# user to kill any existing pianobar processes
@get('/verify')
def verify():
    global email, password, proc

    if email and password:
        ps_aux = subprocess.Popen("ps aux | grep pianobar", stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        output = ps_aux.stdout.readlines()
        for line in output:
            ps_aux_output = line.split()
            if ps_aux_output[10] == "pianobar" and not ps_aux_output[1] == str(proc.pid):
                ps_aux.terminate()
                ps_aux.wait()
                return template("verify", output=ps_aux_output)

        redirect("/home")
    else:
        redirect("/login")

# home route
@get('/home')
def home():
    global proc, stations, music_playing, current_station, first_login, need_to_refresh_stations

    if proc is None:
        redirect("/login")

    if first_login or need_to_refresh_stations:
        raw_stations = read_all(proc.stdout)
        stations[email] = parse_stations(raw_stations)
        current_station = stations[email][1].name
        proc.stdin.write("1\n")
        need_to_refresh_stations = False

    first_login = False

    return template("home", user_stations=stations[email], current_user=email, music_playing=music_playing, current_station=current_station)

@post('/home')
def change_station():
    global proc, current_station, stations, email, music_playing
    new_station = request.forms.get("PID")
    proc.stdin.write("s")
    proc.stdin.write(new_station + "\n")
    current_station = stations[email][int(new_station)].name
    music_playing = True
    redirect("/home")

# decreases volume by three "notches"
@post('/up')
def increase_volume():
    global proc
    proc.stdin.write("))")
    redirect("/home")

# increases volume by three "notches"
@post('/down')
def decrease_volume():
    global proc
    proc.stdin.write("((")
    redirect("/home")

# skips current track
@post('/skip')
def skip():
    global proc, music_playing
    proc.stdin.write("n")
    music_playing = True
    redirect("/home")

@post('/change')
def playpause():
    global proc, music_playing
    music_playing = not music_playing
    proc.stdin.write("p")
    redirect("/home")

@post('/thumbs_up')
def thumbs_up():
    global proc
    proc.stdin.write("+")
    redirect("/home")

@post('/thumbs_down')
def thumbs_down():
    global proc, music_playing
    proc.stdin.write("-")
    music_playing = True
    redirect("/home")

# kills any existing pianobar process that was already running
@post('/kill')
def kill():
    kill = subprocess.Popen("kill " + request.forms.get("PID"), shell=True)
    kill.wait()
    redirect("/verify")

# logs user out, and terminates the pianobar process spawned by user
@post('/logout')
def logout():
    global proc, first_login, email, password
    proc.terminate()
    proc.wait()
    proc = None
    stations[email] = []
    email = ""
    password = ""
    first_login = True
    redirect("/login")

def signal_handler(signum, frame):
    raise Exception("! readline() took too long !")

# reads all the lines possible in a file without EOF (e.g. a stream)
def read_all(file_object):
    lines = []
    try:
        signal.signal(signal.SIGALRM, signal_handler)
        while True:
            signal.alarm(1)
            line = file_object.readline()
            lines.append(line)
            signal.alarm(0)
    except Exception, e:
        return lines
    
def filter_lines(lines):
    for line in lines:
        print line

def parse_stations(stations_array):
    station_list = []
    for station_string in stations_array:
        cleaned = station_string[4:-1]
        # sometimes the wrong lines are sent to this function
        if "\t" in cleaned:
            station_list.append(Station(station_string))
    return station_list

class Station:
    def __init__(self, station_string):
        self.parse(station_string)

    # not very clever (God awful) use of not regexes
    def parse(self, station_string):
        cleaned = station_string[4:-1]
        self.identifier = int(cleaned[cleaned.index("\t"):cleaned.index(")")].strip())
        split_station = cleaned.split()
        if (split_station[1].strip() == "q" and split_station[2]):
            self.name = split_station[2:-1]
        else:
            self.name = split_station[1:-1]
        for i in range(0, len(split_station)):
            if split_station[i] == "Q":
                self.name = split_station[-1]
                return
        self.name = " ".join(self.name)


run(host="192.168.1.119", port=8080, debug=True)
