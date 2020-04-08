# -*- coding: utf-8 -*-

###############################################################################

import logging
import sys

import xbmc
import xbmcvfs

from context import Context
from default import Events
from jellyfin import Jellyfin
from helper import loghandler, window

###############################################################################

loghandler.reset()
loghandler.config()
LOG = logging.getLogger('JELLYFIN.entrypoint')
Jellyfin.set_loghandler(loghandler.LogHandler, logging.DEBUG)

###############################################################################

if 'service' in sys.argv:
	from service import Service
else:
	Jellyfin().set_state(window('jellyfin.server.state.json'))

	for server in window('jellyfin.server.states.json') or []:
		Jellyfin(server).set_state(window('jellyfin.server.%s.state.json' % server))
