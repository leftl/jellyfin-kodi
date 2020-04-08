# -*- coding: utf-8 -*-

###############################################################################
import logging

import xbmc
import xbmcgui

from helper import window

###############################################################################
LOG = logging.getLogger("JELLYFIN."+__name__)

###############################################################################
def listener():

    ''' Corner cases that needs to be listened to.
        This is run in a loop within monitor.py
    '''
    player = xbmc.Player()
    isPlaying = player.isPlaying()

    if not isPlaying and xbmc.getCondVisibility('Window.IsVisible(DialogContextMenu.xml)'):
        control = int(xbmcgui.Window(10106).getFocusId())

        if xbmc.getInfoLabel('Control.GetLabel(1002)') == xbmc.getLocalizedString(12021):
            if control == 1002: # Start from beginning

                LOG.info("Resume dialog: Start from beginning selected.")
                window('jellyfin.resume.bool', False)
                window('jellyfin.context.widget.bool', True)
            elif control == 1001:

                LOG.info("Resume dialog: Resume selected.")
                window('jellyfin.resume.bool', True)
                window('jellyfin.context.widget.bool', True)
            elif control == 1005:

                LOG.info("Reset resume point selected.")
                window('jellyfin.context.resetresume.bool', True)
            else:
                window('jellyfin.resume', clear=True)
                window('jellyfin.context.resetresume', clear=True)
                window('jellyfin.context.widget', clear=True)
        else: # Item without a resume point
            if control == 1001:

                LOG.info("Play dialog selected.")
                window('jellyfin.context.widget.bool', True)
            else:
                window('jellyfin.context.widget', clear=True)

    elif isPlaying and not window('jellyfin.external_check'):

        window('jellyfin.external.bool', player.isExternalPlayer())
        window('jellyfin.external_check.bool', True)
