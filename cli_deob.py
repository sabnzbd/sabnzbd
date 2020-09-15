#!/usr/bin/env python3

import logging, sys
logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

#logging.info('start...')

from sabnzbd.deobfuscate_filenames import *

try:
	fakefilename = sys.argv[1]
except:
	fakefilename = "bbbbbbbbbbbbbbb.avi"

print(fakefilename, ":", is_probably_obfuscated(fakefilename), "\n")


#logging.debug("DONE")
