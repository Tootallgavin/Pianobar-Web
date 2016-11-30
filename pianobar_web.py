# David Shure
# Pandora Bar (web interface for pianobar)
# Built using bottle.py

from bottle import *
from threading import Thread
from collections import Counter
import subprocess, os, signal, time, urllib, json, datetime

# Global variables
proc = None
stations = {}
music_playing = True
current_station = ""
default_station = 0
first_login = True
need_to_refresh_stations = True
caffeine = None
artist = None
track = None
album = None
can_read_proc = False
votes = {}
necessary_votes = 1
voting_interval = 30 # seconds
station_changer = None
admin_ip = ""
pianobar_config_path = '{}/.config/pianobar'.format(os.environ['HOME'])
station_config_path = '{}/station_list'.format(pianobar_config_path)

if not os.path.exists(pianobar_config_path):
    os.makedirs(pianobar_config_path)

email = ""
password = ""

# redirects to login
@get('/')
def index():
    redirect("/login")

@get('/vote/<station>')
def vote(station):
    global votes
    print "Client IP: " + request.remote_addr
    votes[request.remote_addr] = station
    redirect("/home")

# checks if we are already logged in
@get('/login')
def login():
    global proc
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

@get('/start/:station')
def start(station=0):
    global default_station
    print station
    print default_station
    default_station = int(station)
    print default_station
    authenticate()

# authenticates credentials with pandora
@get('/auth')
@post('/auth')
def authenticate():
    global proc, email, password, admin_ip
    proc = None
    proc = subprocess.Popen("pianobar", stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc is None:
        print "Something went wrong. Proc is none"
    else:
        print "Started pianobar proc"

    local_email = os.environ['PANDORA_EMAIL'] #request.forms.get("email")
    local_password = os.environ['PANDORA_PASS'] #request.forms.get("password")
    
    # Enter email and password when prompted
    proc.stdin.write(local_email + "\n")
    proc.stdin.write(local_password + "\n")

    auth = [proc.stdout.readline() for i in range(0, 4)][-1]
    print auth

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
    global email, password, proc, admin_ip

    if email and password:
        ps_aux = subprocess.Popen("ps aux | grep pianobar", stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        output = ps_aux.stdout.readlines()
        for line in output:
            ps_aux_output = line.split()
            if ps_aux_output[10] == "pianobar" and not ps_aux_output[1] == str(proc.pid):
                ps_aux.terminate()
                ps_aux.wait()
                return template("verify", output=ps_aux_output)

        admin_ip = request.remote_addr
        redirect("/home")
    else:
        redirect("/login")

# home route
@get('/home')
def home():
    global proc, stations, music_playing, default_station, current_station, first_login, need_to_refresh_stations, artist, track, album, caffeine, can_read_proc, email, station_changer, admin_ip

    if caffeine is None:
        caffeine = Thread(target=stay_alive)
        caffeine.start()

    if station_changer is None:
        station_changer = Thread(target=remote)
        station_changer.start()

    if proc is None:
        redirect("/login")

    if first_login or need_to_refresh_stations:
        print "... Refreshing ..."
        refreshed_stations = parse_stations(read_all(proc.stdout))
        try:
            stations[email] == refreshed_stations
        except KeyError, e:
            stations[email] = refreshed_stations
        with open(station_config_path, 'w') as output:
    
            print '--- Station List ---'
            for station in stations[email]:
                formatted_line = '{}|{}'.format(station.identifier, station.name)
                print formatted_line
                output.write(formatted_line + "\n")
            print '--------------------'

        print 'Default Station: {}'.format(stations[email][default_station])
        current_station = stations[email][default_station].name
        if not len(stations[email]) == 0:
            proc.stdin.write("{}\n".format(default_station))
        need_to_refresh_stations = False

    first_login = False
    
    #parse_now_playing(read_all(proc.stdout))
    can_read_proc = True

    if artist is not None:
        print "Artist: " + artist + " Track: " + track + " Album: " + album

    now_playing = { "track": track, "artist": artist, "album": album }
    
    is_admin = (request.remote_addr == admin_ip)
    if is_admin:
        print "You're the admin!"
    else:
        print "Admin IP: " + admin_ip + " You're IP: " + request.remote_addr

    return template("home", user_stations=stations[email], current_user=email, music_playing=music_playing, current_station=current_station, now_playing=now_playing, votes=votes, is_admin=is_admin)


def get_station_name(identifier):
    global stations, email
    for station in stations[email]:
        if int(identifier) == station.identifier:
            return station.name

@get('/current.json')
def current_track():
    global proc, artist, track, album, can_read_proc, votes, current_station

    if proc is not None and can_read_proc:
        parse_now_playing(read_all(proc.stdout))
        print "Reading from proc.."
    else:
        print "Not reading from proc.."
    print "Artist: " + str(artist) + "\t Album: " + str(album) + "\t Track: " + str(track)
    top_voted_ids = Counter(votes.values()).most_common()

    top_voted_stations = []

    for vote in top_voted_ids:
        top_voted_stations.append([get_station_name(vote[0]), vote[1]])

    if len(top_voted_stations) >= 5:
        top_voted_stations = top_voted_stations[0:5]
    print "Top Votes: " + str(top_voted_stations)
    return """{ "artist" : "%s", "track" : "%s", "album" : "%s", "votes" : %s, "station" : "%s"}""" % (artist, track, album, json.dumps(top_voted_stations, ensure_ascii=False), current_station)


# self explainatory, route for changing stations
@get('/home/:station')
def change_station(station):
    global proc, current_station, stations, email, music_playing
    if proc is None:
        redirect("/login")
    new_station = station
    proc.stdin.write("s")
    proc.stdin.write(new_station + "\n")
    current_station = stations[email][int(new_station)].name
    music_playing = True
    redirect("/home")

# decreases volume by two "notches"
@get('/up')
def increase_volume():
    global proc
    if proc is None:
        redirect("/login")
    proc.stdin.write("))")
    redirect("/home")

# increases volume by two "notches"
@get('/down')
def decrease_volume():
    global proc
    if proc is None:
        redirect("/login")
    proc.stdin.write("((")
    redirect("/home")

# skips current track
@get('/skip')
def skip():
    global proc, music_playing
    if proc is None:
        redirect("/login")
    proc.stdin.write("n")
    music_playing = True
    redirect("/home")

@get('/shift')
def playpause():
    global proc, music_playing
    if proc is None:
        redirect("/login")
    music_playing = not music_playing
    proc.stdin.write("p")
    redirect("/home")

@get('/thumbs_up')
def thumbs_up():
    global proc
    if proc is None:
        redirect("/login")
    proc.stdin.write("+")
    redirect("/home")

@get('/thumbs_down')
def thumbs_down():
    global proc, music_playing
    if proc is None:
        redirect("/login")
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
@get('/logout')
def logout():
    global proc, first_login, email, password, artist, track, album, can_read_proc, votes
    artist = None
    album = None
    track = None
    email = ""
    password = ""
    first_login = True
    votes = {}
    if proc is None:
        redirect("/login")
    else:
        proc.terminate()
        proc.wait()
        proc = None
    can_read_proc = False
    redirect("/login")

def stay_alive(): # please
    global proc
    while True:
        try:
            time.sleep(90)
            request = urllib.urlopen("http://0.0.0.0:8080/current")
            request = urllib.urlopen("http://0.0.0.0:8080/home")
        except Exception, e:
            continue


def get_top_votes(votes): # taking in votes as our global variable
    top_voted_ids = Counter(votes.values()).most_common()
    top_voted_stations = []

    for vote in top_voted_ids:
        top_voted_stations.append([vote[0], vote[1]]) # corrosponds to station id, then vote count

    if len(top_voted_stations) >= 5:
        top_voted_stations = top_voted_stations[0:5]

    return top_voted_stations


def remote():
    global proc, necessary_votes, votes, voting_interval, current_station
    while True:
        time.sleep(voting_interval)
        top_votes = get_top_votes(votes)
        try:
            if top_votes[0][1] >= necessary_votes:
                proc.stdin.write("s")
                proc.stdin.write(str(top_votes[0][0]) + "\n")
                votes = {}
                current_station = get_station_name(top_votes[0][0])
                print "Changing station"
            else:
                print "Not changing station"
        except Exception, e:
            print "No votes recorded."
            
            

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
        
def parse_now_playing(raw_lines):
    global artist, track, album
    if len(raw_lines) > 0 and "\" by \"" in raw_lines[-1] and "\" on \"" in raw_lines[-1]:
        cleaned_up = raw_lines[-1][raw_lines[-1].index("\""):-1]
        print "Before: " + str(cleaned_up)
        split = cleaned_up.replace("\" by \"", " | ").replace("\" on \"", " | ").split(" | ")

        tent_track = split[0]
        tent_artist = split[1]
        tent_album = split[2]


        if tent_track[0] == "\"":
            tent_track = tent_track[1:]
        if tent_track[-1] == "\"":
            tent_track = tent_track[0:-1]

        if tent_artist[0] == "\"":
            tent_artist = tent_artist[1:]
        if tent_artist[-1] == "\"":
            tent_artist = tent_artist[0:-1]

        if tent_album[0] == "\"":
            tent_album = tent_album[1:]
        if tent_album[-1] == "\"":
            tent_album = tent_album[0:-1]

        album = tent_album
        artist = tent_artist
        track = tent_track

        print repr("Track: " + track)
        print repr("Artist: " + artist)
        print repr("Album: " + album)

       

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

    def __str__(self):
        return '{} {}'.format(self.identifier, self.name)

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
            # for QuickMix station
            if split_station[i] == "Q":
                self.name = split_station[-1]
                return
        self.name = " ".join(self.name)

run(host="0.0.0.0", port=8080, debug=True)

