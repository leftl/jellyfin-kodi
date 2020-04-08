# -*- coding: utf-8 -*-

###############################################################################

import imp
import logging
import os
import threading
import sys

import xbmc
import xbmcvfs
import xbmcaddon

###############################################################################

__addon__ = xbmcaddon.Addon(id='plugin.video.jellyfin')
__addon_path__ = __addon__.getAddonInfo('path').decode('utf-8')
__base__ = xbmc.translatePath(os.path.join(__addon_path__, 'resources', 'lib')).decode('utf-8')
__libraries__ = xbmc.translatePath(os.path.join(__addon_path__, 'libraries')).decode('utf-8')
__pcache__ = xbmc.translatePath(os.path.join(__addon__.getAddonInfo('profile'), 'jellyfin')).decode('utf-8')
__cache__ = xbmc.translatePath('special://temp/jellyfin').decode('utf-8')

sys.path.insert(0, __libraries__)

if not xbmcvfs.exists(__pcache__ + '/'):
    from resources.lib.helper.utils import copytree

    copytree(os.path.join(__base__, 'objects'), os.path.join(__pcache__, 'objects'))

sys.path.insert(0, __cache__)
sys.path.insert(0, __pcache__)
sys.path.insert(0, __base__)
sys.argv.append('service')

###############################################################################

from helper import settings
import entrypoint

###############################################################################

LOG = logging.getLogger("JELLYFIN.service")
DELAY = int(settings('startupDelay') if settings('SyncInstallRunDone.bool') else 4 or 0)

###############################################################################


class ServiceManager(threading.Thread):

    ''' Service thread. 
        To allow to restart and reload modules internally.

        Restart service
        Delete lib and objects entries to reload them as if it were the first time.
        Delete .pyo files to force Kodi to recreate them.
        Finally, re-initialize modules that are used in __main__ to reload all our modules.
    '''
    exception = None

    def __init__(self):
        threading.Thread.__init__(self)

    def run(self):
        global entrypoint
        global settings

        service = None

        try:
            service = entrypoint.Service()

            if DELAY and xbmc.Monitor().waitForAbort(DELAY):
                raise Exception("Aborted during startup delay")

            service.service()
        except Exception as error:
            self.exception = error
            LOG.error(error)
            if service is not None:

                if not 'ExitService' in error:
                    service.shutdown()
                
                if 'RestartService' in error:

                    for mod in dict(sys.modules):
                        module = sys.modules[mod]

                        try:
                            module_path = imp.find_module(mod.split('.')[0])[1]

                            if ('plugin.video.jellyfin' in module_path and not 'libraries' in module_path or 
                                mod.startswith('objects')):

                                LOG.debug("[ reload/%s ]", mod)
                                del sys.modules[mod]
                        except ImportError: #xbmc built-in functions or entries with None
                            pass

                    import entrypoint
                    import helper
                    import objects

                    try:
                        helper.utils.delete_pyo(__addon_path__)
                        helper.utils.delete_pyo(__pcache__)
                    except Exception:
                        pass

                    imp.reload(entrypoint)
                    imp.reload(helper)
                    imp.reload(objects)

                    from helper import settings


if __name__ == '__main__':

    LOG.warn("-->[ service ]")
    LOG.warn("Delay startup by %s seconds.", DELAY)

    while True:

        if not settings('enableAddon.bool'):
            LOG.warn("Jellyfin for Kodi is not enabled.")

            break

        try:
            session = ServiceManager()
            session.start()
            session.join() # Block until the thread exits.

            if 'RestartService' in session.exception:
                continue

        except Exception as error:
            LOG.exception(error)

        break

    LOG.warn("--<[ service ]")
