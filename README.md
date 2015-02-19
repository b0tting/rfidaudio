# Rfidaudio
A Python program that links incoming RFID tags to audio files, with a web front-end for administration

This is a small python program that will listen for RFID tags and play a specific audio file when one is detected. You can use the web interface to see what is playing, link new RFIDs and sound files and manage existing pairs

I tested with a nameless USB RFID reader that emulates keyboard input. My device identified as "ID 08ff:0009 AuthenTec, Inc.". Mine was sold for 20 euros and was labeled "Windows only". 

# Installation
This script assumes some files at specific locations, see MP3Dir in rfidaudio.py. We also use a number of Python libraries so install these fisr
- pip install pygame
- pip install flask
- pip install pyusb

I had some issues with the latest version of pyusb and had to resort to an earlier version (pip install -Iv pyusb==1.0.0b). The keyboard_alike library came from https://github.com/riklaunim/pyusb-keyboard-alike. You may also need to install the sqlite3 and libusb linux packages. 

For convenience, there is an init.d script in the init.d directory. Please change file locations mentioned in the script before deploying. 

# Usage
Start script. Assuming it managed to connect to the RFID reader without errors, it will pull up a webserver on 0.0.0.0:80. Full logging is done to /var/log/rfidaudio.log

Currently, audio triggered from the RFID fades after 20 seconds, you can change this by setting the playMP3Duration value in the script (to 0 for play until end).

# Test setup
This script was developed on a Raspberry Pi B and a Raspberry Pi B+. It works perfectly on the former, but I suggest the latter (or the Raspberry Pi 2) because USB got a little flaky with the RFID reader I used. Sound on the B+ is also audibly better. 

Stress testing was done by giving my toddler a handful of RFID tags linked to his favourite songs. 
