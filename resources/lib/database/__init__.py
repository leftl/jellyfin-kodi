# -*- coding: utf-8 -*-

###############################################################################

import datetime
import logging
import json
import os
import sqlite3

import xbmc
import xbmcvfs

import jellyfin_db
from helper.utils import delete_folder
from helper import _, settings, window, dialog

###############################################################################

LOG = logging.getLogger("JELLYFIN."+__name__)

###############################################################################


def test_databases():

    ''' Open the databases to test if the file exists.
    '''
    with Database('video') as kodidb:
        with Database('music') as musicdb:
            pass

    with Database('jellyfin') as jellyfindb:
        jellyfin_tables(jellyfindb.cursor)


class KodiLock(object):

    ''' Custom lock, based on built-in lock for database manipulation. 
        Made for Kodi usage, to communicate across add-on instances. 
        Use before starting db interactions.

        with KodiLock('video'):
            # do stuff
    '''
    def __init__(self, file, *args, **kwargs):

        threading.Lock.__init__(self, *args, **kwargs)
        self.file = file
        self._locked = self._get_lock()

    def _get_lock(self):
        return window('kodidb.%s.bool' % self.file)

    def _set_lock(self, lock):
        window('kodidb.%s.bool' % self.file, lock)

    def acquire(self, blocking=True, timeout=None):

        if blocking:
            delay = 0.0005

            if timeout is None:

                while self._locked:
                    delay = wait(delay)
            else:
                end = time() + timeout
                while time() < end:

                    if not self._locked:
                        break

                    delay = wait(delay)
                else:
                    return False

            self._locked = True
            self._set_lock(True)

            return True

        elif timeout is not None:
            raise ValueError("can't specify a timeout for a non-blocking call")

        if self._locked:
            return False

        self._locked = True
        self._set_lock(True)

        return True

    def release(self):

        if not self._locked:
            raise RuntimeError("release unlocked lock")

        self._locked = False
        self._set_lock(False)

    def locked(self):
        return self._locked


class Database(object):

    ''' This should be called like a context.
        i.e. with Database('jellyfin') as db:
            db.cursor
            db.conn.commit()
    '''
    timeout = 120
    discovered = False
    discovered_file = None

    def __init__(self, file=None, commit_close=True):

        ''' file: jellyfin, texture, music, video, :memory: or path to file
        '''
        self.db_file = file or "video"
        self.commit_close = commit_close

    def __enter__(self):

        ''' Open the connection and return the Database class.
            This is to allow for the cursor, conn and others to be accessible.
        '''
        self.path = self._sql(self.db_file)
        self.conn = sqlite3.connect(self.path, timeout=self.timeout)
        self.cursor = self.conn.cursor()

        if self.db_file in ('video', 'music', 'texture', 'jellyfin'):
            self.conn.execute("PRAGMA journal_mode=WAL") # to avoid writing conflict with kodi

        LOG.debug("--->[ database: %s ] %s", self.db_file, id(self.conn))

        return self

    def _get_database(self, path, silent=False):

        path = xbmc.translatePath(path).decode('utf-8')

        if not silent:

            if not xbmcvfs.exists(path):
                raise Exception("Database: %s missing" % path)

            conn = sqlite3.connect(path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            conn.close()

            if not len(tables):
                raise Exception("Database: %s malformed?" % path)

        return path

    def _sql(self, file):

        ''' Get the database path based on the file objects/obj_map.json
            Compatible check, in the event multiple db version are supported with the same Kodi version.
            Load video, music, texture databases from the log file. Will only run once per service thread.
            Running database version lines
        '''
        from objects import Objects

        databases = Objects().objects

        if file not in ('video', 'music', 'texture') or databases.get('database_set%s' % file):
            return self._get_database(databases[file], True)

        folder = xbmc.translatePath("special://database/").decode('utf-8')
        dirs, files = xbmcvfs.listdir(folder)
        dbs = {
            'Textures': "texture",
            'MyMusic': "music",
            'MyVideos': "video"
        }
        for db in dbs:

            count = 0
            filename = None

            for name in files:

                if (name.startswith(db) and not name.endswith('-wal') and
                    not name.endswith('-shm') and not name.endswith('db-journal')):

                    count += 1
                    filename = name

            if count == 1:

                key = dbs[db]
                databases[key] = os.path.join(folder, filename.decode('utf-8')).decode('utf-8')
                databases['database_set%s' % key] = True

                continue

            break
        else:
            return databases[file]

        with open(xbmc.translatePath('special://logpath/kodi.log').decode('utf-8'), 'r') as log:
            found_lines = len(dbs)

            for line in log:
                if 'Running database version' in line:

                    filename = line.rsplit('version ', 1)[1].strip()
                    filename = "%s.db" % filename

                    for database in dbs:
                        if database in line:

                            key = dbs[database]
                            databases[key] = os.path.join(folder, filename.decode('utf-8')).decode('utf-8')
                            databases['database_set%s' % key] = True
                            found_lines -= 1

                            break

                elif not found_lines:
                    break

        return databases[file]

    def find_databases(self, databases):

        dbs = {
            'Textures': "texture",
            'MyMusic': "music",
            'MyVideos': "video"
        }
        for db in dbs:

            count = 0
            filename = None

            for name in files:

                if (name.startswith(db) and not name.endswith('-wal') and
                    not name.endswith('-shm') and not name.endswith('db-journal')):

                    count += 1
                    filename = name

            if count == 1:

                key = dbs[db]
                databases[key] = os.path.join(folder, filename.decode('utf-8')).decode('utf-8')
                databases['database_set%s' % key] = True

                continue


    def __exit__(self, exc_type, exc_val, exc_tb):

        ''' Close the connection and cursor.
        '''
        changes = self.conn.total_changes

        if exc_type is not None: # errors raised
            LOG.error("type: %s value: %s", exc_type, exc_val)

        if self.commit_close and changes:

            LOG.info("[%s] %s rows updated.", self.db_file, changes)
            self.conn.commit()

        LOG.debug("---<[ database: %s ] %s", self.db_file, id(self.conn))
        self.cursor.close()
        self.conn.close()

def jellyfin_tables(cursor):

    ''' Create the tables for the jellyfin database.
        jellyfin, view, version
    '''
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS jellyfin(
        jellyfin_id TEXT UNIQUE, media_folder TEXT, jellyfin_type TEXT, media_type TEXT,
        kodi_id INTEGER, kodi_fileid INTEGER, kodi_pathid INTEGER, parent_id INTEGER,
        checksum INTEGER, jellyfin_parent_id TEXT)""")
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS view(
        view_id TEXT UNIQUE, view_name TEXT, media_type TEXT)""")
    cursor.execute("CREATE TABLE IF NOT EXISTS version(idVersion TEXT)")

    columns = cursor.execute("SELECT * FROM jellyfin")
    descriptions = [description[0] for description in columns.description]

    if 'jellyfin_parent_id' not in descriptions:
        
        LOG.info("Add missing column jellyfin_parent_id")
        cursor.execute("ALTER TABLE jellyfin ADD COLUMN jellyfin_parent_id 'TEXT'")

    if 'presentation_key' not in descriptions:

        LOG.info("Add missing column presentation_key")
        cursor.execute("ALTER TABLE jellyfin ADD COLUMN presentation_key 'TEXT'")

def reset():

    ''' Reset both the jellyfin database and the kodi database.
    '''
    from views import Views
    views = Views()

    if not dialog("yesno", heading="{jellyfin}", line1=_(33074)):
        return

    window('jellyfin_should_stop.bool', True)
    count = 10

    while window('jellyfin_sync.bool'):

        LOG.info("Sync is running...")
        count -= 1

        if not count:
            dialog("ok", heading="{jellyfin}", line1=_(33085))

            return

        if xbmc.Monitor().waitForAbort(1):
            return

    reset_kodi()
    reset_jellyfin()
    views.delete_playlists()
    views.delete_nodes()

    if dialog("yesno", heading="{jellyfin}", line1=_(33086)):
        reset_artwork()

    addon_data = xbmc.translatePath("special://profile/addon_data/plugin.video.jellyfin/").decode('utf-8')

    if dialog("yesno", heading="{jellyfin}", line1=_(33087)):

        xbmcvfs.delete(os.path.join(addon_data, "settings.xml"))
        xbmcvfs.delete(os.path.join(addon_data, "data.json"))
        LOG.info("[ reset settings ]")

    if xbmcvfs.exists(os.path.join(addon_data, "sync.json")):
        xbmcvfs.delete(os.path.join(addon_data, "sync.json"))

    settings('enableMusic.bool', False)
    settings('MinimumSetup', "")
    settings('MusicRescan.bool', False)
    settings('SyncInstallRunDone.bool', False)
    dialog("ok", heading="{jellyfin}", line1=_(33088))
    xbmc.executebuiltin('RestartApp')

def reset_kodi():

    with Database() as videodb:
        videodb.cursor.execute("SELECT tbl_name FROM sqlite_master WHERE type='table'")

        for table in videodb.cursor.fetchall():
            name = table[0]

            if name != 'version':
                videodb.cursor.execute("DELETE FROM " + name)

    if settings('enableMusic.bool') or dialog("yesno", heading="{jellyfin}", line1=_(33162)):

        with Database('music') as musicdb:
            musicdb.cursor.execute("SELECT tbl_name FROM sqlite_master WHERE type='table'")

            for table in musicdb.cursor.fetchall():
                name = table[0]

                if name != 'version':
                    musicdb.cursor.execute("DELETE FROM " + name)

    LOG.warn("[ reset kodi ]")

def reset_jellyfin():
    
    with Database('jellyfin') as jellyfindb:    
        jellyfindb.cursor.execute("SELECT tbl_name FROM sqlite_master WHERE type='table'")

        for table in jellyfindb.cursor.fetchall():
            name = table[0]

            if name not in ('version', 'view'):
                jellyfindb.cursor.execute("DELETE FROM " + name)

            jellyfindb.cursor.execute("DROP table IF EXISTS jellyfin")
            jellyfindb.cursor.execute("DROP table IF EXISTS view")
            jellyfindb.cursor.execute("DROP table IF EXISTS version")

    LOG.warn("[ reset jellyfin ]")

def reset_artwork():

    ''' Remove all existing texture.
    '''
    thumbnails = xbmc.translatePath('special://thumbnails/').decode('utf-8')

    if xbmcvfs.exists(thumbnails):
        dirs, ignore = xbmcvfs.listdir(thumbnails)

        for directory in dirs:
            ignore, thumbs = xbmcvfs.listdir(os.path.join(thumbnails, directory.decode('utf-8')))

            for thumb in thumbs:
                LOG.debug("DELETE thumbnail %s", thumb)
                xbmcvfs.delete(os.path.join(thumbnails, directory.decode('utf-8'), thumb.decode('utf-8')))

    with Database('texture') as texdb:
        texdb.cursor.execute("SELECT tbl_name FROM sqlite_master WHERE type='table'")

        for table in texdb.cursor.fetchall():
            name = table[0]

            if name != 'version':
                texdb.cursor.execute("DELETE FROM " + name)

    LOG.warn("[ reset artwork ]")

def get_sync():

    path = xbmc.translatePath("special://profile/addon_data/plugin.video.jellyfin/").decode('utf-8')
    
    if not xbmcvfs.exists(path):
        xbmcvfs.mkdirs(path)

    try:
        with open(os.path.join(path, 'sync.json')) as infile:
            sync = json.load(infile)
    except Exception:
        sync = {}

    sync['Libraries'] = sync.get('Libraries', [])
    sync['RestorePoint'] = sync.get('RestorePoint', {})
    sync['Whitelist'] = list(set(sync.get('Whitelist', [])))
    sync['SortedViews'] = sync.get('SortedViews', [])

    return sync

def save_sync(sync):

    path = xbmc.translatePath("special://profile/addon_data/plugin.video.jellyfin/").decode('utf-8')
    
    if not xbmcvfs.exists(path):
        xbmcvfs.mkdirs(path)

    sync['Date'] = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

    with open(os.path.join(path, 'sync.json'), 'w') as outfile:
        json.dump(sync, outfile, sort_keys=True, indent=4, ensure_ascii=False)

def get_credentials():

    path = xbmc.translatePath("special://profile/addon_data/plugin.video.jellyfin/").decode('utf-8')
    
    if not xbmcvfs.exists(path):
        xbmcvfs.mkdirs(path)

    try:
        with open(os.path.join(path, 'data.json')) as infile:
            credentials = json.load(infile)
    except Exception:

        try:
            with open(os.path.join(path, 'data.txt')) as infile:
                credentials = json.load(infile)
                save_credentials(credentials)
            
            xbmcvfs.delete(os.path.join(path, 'data.txt'))
        except Exception:
            credentials = {}

    credentials['Servers'] = credentials.get('Servers', [])

    return credentials

def save_credentials(credentials):

    credentials = credentials or {}
    path = xbmc.translatePath("special://profile/addon_data/plugin.video.jellyfin/").decode('utf-8')
    
    if not xbmcvfs.exists(path):
        xbmcvfs.mkdirs(path)

    credentials = json.dumps(credentials, sort_keys=True, indent=4, ensure_ascii=False)

    with open(os.path.join(path, 'data.json'), 'w') as outfile:
        outfile.write(credentials.encode('utf-8'))

def get_item(kodi_id, media):

    ''' Get jellyfin item based on kodi id and media.
    '''
    with Database('jellyfin') as jellyfindb:
        item = jellyfin_db.JellyfinDatabase(jellyfindb.cursor).get_full_item_by_kodi_id(kodi_id, media)

        if not item:
            LOG.debug("Not an jellyfin item")

            return

    return item
