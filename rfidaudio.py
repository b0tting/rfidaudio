#!/usr/bin/python
## Mijn USB device ID 08ff:0009
from keyboard_alike import reader
import pygame
import datetime
import threading
import traceback
import time
import logging
from logging import handlers
from threading import Thread
from flask import Flask, render_template, request, redirect, url_for, send_from_directory
from werkzeug import secure_filename
from os import listdir
from os.path import isfile, join
import sqlite3
import os
import sys

spEvent = threading.Event();
global lastRFID
lastRFID = 0;
lastTime = 0;
currentTune = "";

## Afspeeltijd in seconden
## Set to 0 to play until end of file
playMP3Duration = 30
playMP3FadeDuration = 2
MP3Dir = '/usr/local/rfidaudio/mp3'
logfile = '/var/log/rfidaudio'

## Setup logging
logger = logging.getLogger(__name__)
handler = handlers.RotatingFileHandler(logfile, maxBytes=500000, backupCount=3)
handler.setLevel(logging.INFO)
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

def getConnection():
    return sqlite3.connect('rfidaudio.sql3')

def runUpdateQuery(query):
    conn = getConnection()
    try:
        c = conn.cursor()
        c.execute(query)
        conn.commit()
    except Exception as e:
        logger.error('Failed with query ' + query)
    conn.close()

def getNiceTime(seconds):
     if(seconds == 0):
        return "none"     
     elif seconds < 60:
        return str(round(seconds)) + " seconds"
     elif seconds < 3600:
        return str(round(seconds / 60)) + " minutes"
     else:
        return str(round(seconds / 3600)) + " hour(s)"

## DAO functies
def fetchRFIDRecord(rfid):
    if(rfid == 0):
        row = False;
    else:
        conn = getConnection();
        c = conn.cursor()
        row = c.execute("select * from known_rfid where rfid = '" + rfid + "'").fetchone();
        conn.close();
    if row:
        god = row[4] if row[4] else "" 
        return ({'rfid':row[0],'plin':row[1],'mp3':row[2],'god':god,'lasttime': getNiceTime(time.time() - row[3])})
    else:
        return False

def getAllRFID():
    c = getConnection().cursor()
    result = c.execute("select * from known_rfid order by lasttime desc")
    niceResult = [];
    for row in result:
        if(row[3] == 0):
            lasttime = "(not seen)"
        else:
            lasttime =  datetime.datetime.fromtimestamp(row[3]).strftime('%Y-%m-%d %H:%M')
        niceResult.append({'rfid':row[0],'plin':row[1],'mp3':row[2],'god':row[4],'lasttime': lasttime})
    return niceResult

def updateAccessTime(rfid):
    logger.info("Updating access time for RFID " + rfid)
    runUpdateQuery("update known_rfid set lasttime = " + str(round(time.time())) + " where rfid = '" + lastRFID + "'")

def updateOrInsertRFID(rfid, plin, mp3, god):
    current = fetchRFIDRecord(rfid)
    if(current):
        sql = "UPDATE known_rfid set plin = " + plin + ", mp3 = '" + mp3 + "', god = '" + god + "' where rfid = '" + rfid + "';"
        logger.info("Attempting to update RFID " + rfid + " with values plin = " + plin + ", mp3 = '" + mp3 + "', god = '" + god)
    else: 
        sql = "INSERT INTO known_rfid VALUES ('" + rfid + "', " + plin + ", '" + mp3 + "', 0, '" + god + "');"
        logger.info("Inserting new RFID " + rfid + ", values '" + rfid + "', " + plin + ", '" + mp3 + "', 0, '" + god + "'")
    runUpdateQuery(sql)

def deleteRFID(rfid):
    sql = "DELETE FROM known_rfid WHERE RFID = '" + rfid + "'"
    runUpdateQuery(sql)


def getAllMP3():
   return [ f for f in listdir(MP3Dir) if isfile(join(MP3Dir,f)) ] 

def getLogs():
    with open(logfile) as f:
        content = f.readlines()
    if(len(content) > 40):
        content = content[-40:]
    return content[::-1]

## RFID listener thread. 
## Ik gebruik het even om geluid te triggeren, zodat deze thread weer beschikbaar
## komt om ondertussen naar andere RFIDs te luisteren
def RFIDListener(spEvent):
    global lastRFID
    global lastTime
    myReader = reader.Reader(0x08ff, 0x0009, 84, 16, should_reset=False)
    logger.info("Starting reader")
    while (True):
        myReader.initialize()
        logger.info("Thread waiting for RFID")
        try: 
            value = myReader.read().strip();
            logger.info("Received RFID: " + value);
            lastRFID = value
            lastTime = round(time.time());
            myReader.disconnect()
            if(spEvent.is_set()):
                logger.info("..but already working on other key")
            elif(getPlayingMP3()):
                logger.info("..but already playing a song")
            else:
                logger.info("Looking for sound now") 
                spEvent.set()
        except Exception as e:
            logger.error("Could not read USD RFID, trying later")
            time.sleep(2)
            traceback.print_exc()

## Geluid functies
# AKA startSound
def tossMP3(mp3, loop = 0, force = False):
    if not getPlayingMP3() or force:
        mp3file =  MP3Dir + '/' + mp3
        try:
            if getPlayingMP3() and force:
                pygame.mixer.stop();
                logger.info("Now forcing next play and ignoring current");
            global currentTune
            currentTune = mp3
            pygame.mixer.music.load(mp3file)
            if loop == 1:
                pygame.mixer.music.play(-1)
                logger.info("Now looping: " + mp3)
            else:
                pygame.mixer.music.play()
                logger.info("Now playing: " + mp3)
        except Exception as e:
            logger.error("Could not play MP3 file " + mp3file +". Does this file exist? Wrong format perhaps?")
            traceback.print_exc()
    else: 
        logger.info("Somebody tried to fire " + mp3 + " but we are already playing something else")

        

def getPlayingMP3():
    if pygame.mixer.music.get_busy():
        return currentTune
    else:
        return False
        
def stopMP3():
    logger.info("Fading mp3")
    if(getPlayingMP3()):
        pygame.mixer.music.fadeout(playMP3FadeDuration * 1000)
    else: 
        logger.error("Tried to stop playing, but nothing was actually playing")
########


## Badly named, general event handler, kicks audio into action on RFID event
def SoundPlayer(spEvent):
    pygame.mixer.init()
    while not spEvent.isSet():
        event_is_set = spEvent.wait()
        if(event_is_set):
            ## New key read!
            niceRFID = fetchRFIDRecord(lastRFID)
            if niceRFID:
                logger.info("RFID is known in database")
                logger.info(niceRFID)
                mp3 = niceRFID['mp3']
                then = time.time()
                updateAccessTime(lastRFID)
                tossMP3(mp3)
                while getPlayingMP3():
                    now = time.time();
                    if (playMP3Duration > 0) and ((now - then) > playMP3Duration):
                        stopMP3()
                        time.sleep(playMP3FadeDuration + 1)
                        ## Sleep terwijl de fade afloopt zodat daarna pas de RFID reader weer reset
                    else:
                        time.sleep(1)
                    continue
                logger.info("Done playing " + mp3)
            else: 
                logger.info("No match found for " + str(lastRFID)) 
        spEvent.clear()
        logger.info("Ready for next assignment")


## Alle routing
app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html', knownrfid = getAllRFID(), editrfid = None, mp3s = getAllMP3(), logs=getLogs())

## Edit een gegeven RFID
@app.route('/edit/<rfid>')
def editRFID(rfid):
    niceRFID = fetchRFIDRecord(rfid)
    ## Dat moet !@#$ toch makkelijker kunnen? Nu copypasta ik de index methode!
    return render_template('index.html', knownrfid = getAllRFID(), editrfid = niceRFID, mp3s = getAllMP3(), logs=getLogs())

@app.route('/refreshlog')
def refreshlog():
    return render_template('index.html', knownrfid = getAllRFID(), editrfid = None, mp3s = getAllMP3(), logs=getLogs(), refreshlog = True)


## JSON code die toont of er nu een geluid loopt
@app.route('/altarstate')
def getAltarState():
    mp3 = getPlayingMP3()
    if(mp3):
        return ('{ "playing": true, "playstate":"' + mp3 + '" , "volume":' + str(pygame.mixer.music.get_volume() * 100) + '}')
    else: 
        return ('{ "playing" : false , "volume":' + str(pygame.mixer.music.get_volume() * 100) + '}')

## Geef opdracht om een audio stuk te starten op het altaar
@app.route('/altarplay/<mp3>')
@app.route('/altarplay/<mp3>/<loop>')
def altarplay(mp3, loop = "0"):
    loop = int(loop)
    tossMP3(mp3, loop, True)
    return redirect("/")

## Stop een spelende audio track
@app.route('/altarplaystop')
def altarplaystop():
    stopMP3()
    return redirect("/")


## Stuur een audio bestand naar de client
@app.route('/localplay/<mp3>')
def localplay(mp3):
    return send_from_directory(app.config['UPLOAD_FOLDER'],mp3)

## Verwijder een gegeven bestand
@app.route('/deletemp3/<mp3>')
def deletemp3(mp3):
    ## Om eventuele grappenmakers tegen te gaan check ik of er geen directory traversal plaats vind 
    if "/" not in mp3:
        os.remove(MP3Dir + "/" + mp3)
    return redirect("/")

## Shut the dajumn thing down
@app.route('/shutdown')
def shutdown():
    os.system("/sbin/shutdown -h now")
    return redirect("/")

## ..or reboot it
@app.route('/reboot')
def reboot():
    os.system("/sbin/reboot")
    return redirect("/")

## Save een RFID naar audio koppeling
@app.route('/saverfid', methods=['POST'])
def saverfid():
    ## Geen validatie. Validatie is stom
    updateOrInsertRFID(request.form['rfid'], request.form['plin'], request.form['mp3'], request.form['god'])
    return redirect("/")


@app.route('/deleterfid/<rfid>')
def deleterfid(rfid):
    deleteRFID(rfid)
    return redirect("/")

## Set volume van de pygame unit
@app.route('/setvolume/<newvol>')
def setvolume(newvol):
    pygame.mixer.music.set_volume(float(newvol) / 100)
    return getAltarState();

@app.route('/savemp3', methods=['POST'])
def saveMP3():
    file = request.files['newmp3']  
    filename = secure_filename(file.filename)
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    return redirect("/")        

## JSON code zodat de interface de laatst bekende RFID op kan halen    
@app.route('/last')
def fetchLastRFID():
    niceRFID = fetchRFIDRecord(lastRFID)
    if(lastTime == 0):
        diff = lastTime
    else:
        diff = round(time.time() - lastTime)
    
    if niceRFID:
        logger.info(niceRFID)
        lastrfid = niceRFID['rfid']
        
        ## This is a fix. If you hammer the USB with RFID devices it sometimes jams more then one into a single
        ## keyboard sequence
        if(len(lastrfid) > 10): 
                lastrfid = lastrfid[:10]

        return '{ "last":"'+ lastrfid +'", "time":"' + getNiceTime(diff) + ' ago", "isnew":false,"mp3":"' + niceRFID['mp3'] + '","plin":'+ str(niceRFID['plin']) + ',"god":"' + niceRFID['god'] + '"}'
    else:
        lastrfid = str(lastRFID)

        ## This is a fix. If you hammer the USB with RFID devices it sometimes jams more then one into a single
        ## keyboard sequence
        if(len(lastrfid) > 10):
                lastrfid = lastrfid[:10]

        lastrfid = lastrfid[0:10]
        return '{ "last":"' + lastrfid + '", "time":"' + getNiceTime(diff) + ' ago",  "isnew":true }'

####
## Main program
## Kick off threads
logger.info("Starting RFID listener")
RFIDThread = Thread(target = RFIDListener, args = (spEvent,))
RFIDThread.daemon = True
RFIDThread.start()
logger.info("Starting sound listener")
SPThread = Thread(target = SoundPlayer, args = (spEvent,))
SPThread.daemon = True
SPThread.start()

logger.info("Starting Webserver")
#app.debug = True
app.config['PROPAGATE_EXCEPTIONS'] = True
app.config['UPLOAD_FOLDER'] = MP3Dir
app.run(host='0.0.0.0', port=80)


