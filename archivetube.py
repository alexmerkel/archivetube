#!/usr/bin/env python3
''' archivetube - web interface for archived videos '''

import os
import sys
import sqlite3
import argparse
import time
from server import Server

__prog__ = "archivetube"
__version__ = "0.4.0"
__dbversion__ = 4
__archivedbversion__ = 5

# --------------------------------------------------------------------------- #
def main(args):
    '''The main archive tube function

    :param args: The command line arguments given by the user
    :type args: list
    '''
    parser = argparse.ArgumentParser(prog=__prog__, description="Serve a web interface for archived videos")
    parser.add_argument("-v", "--verbose", action="store_const", dest="verbose", const=True, default=False, help="Print more status info")
    parser.add_argument("-r", "--recursive", action="store_const", dest="recursive", const=True, default=False, help="Add all archives in subdirectories of the specified location to the database")
    parser.add_argument("-f", "--folder", action="store", dest="folder", help="Add an archive directory to the database (Path will be stored as relative to DIR)")
    parser.add_argument("-m", "--memory", action="store_const", dest="memory", const=True, default=False, help="Keep whole database in memory (faster, but requires a lot of memory)")
    parser.add_argument("-V", "--version", action="version", version='%(prog)s {}'.format(__version__))
    parser.add_argument("DIR", help="The directory to work in")

    args = parser.parse_args()

    #Validate path
    path = os.path.normpath(os.path.abspath(args.DIR))
    if not os.path.isdir(path):
        parser.error("An existing directory must be specified")

    if args.memory:
        print("Using in-memory database")

    try:
        #Check if database exists
        dbPath = os.path.join(path, "tube.db")
        try:
            if os.path.isfile(dbPath):
                #Connect to database
                t1 = time.perf_counter()
                if args.memory:
                    print("Reading existing database")
                    fileDBCon = connectDB(dbPath)
                    dbCon = sqlite3.connect(":memory:", check_same_thread=False)
                    fileDBCon.backup(dbCon)
                    fileDBCon.close()
                else:
                    print("Connect to existing database")
                    dbCon = connectDB(dbPath, checkThread=False)
                t2 = time.perf_counter()
                t = t2 - t1
                if args.verbose:
                    print("Read time: {:0.4f} seconds".format(t))
            else:
                #No database found
                print("No database found, creating one")
                if args.memory:
                    dbCon = createDB(":memory:", checkThread=False)
                else:
                    dbCon = createDB(dbPath, checkThread=False)
            db = dbCon.cursor()
        except sqlite3.Error as e:
            print(e)
            return

        #Check if folder to add to database
        if args.folder:
            rel = os.path.relpath(args.folder, path)
            if args.recursive:
                print("Adding archives in subdirectories of '{}' to the database".format(rel))
            else:
                print("Adding archive '{}' to the database".format(rel))
            cmd = "INSERT INTO archives(relpath, abspath, recursive) VALUES(?,?,?)"
            db.execute(cmd, (rel, args.folder, args.recursive))

        #(Re-) indexing
        print("(Re-)building index")
        t1 = time.perf_counter()
        reIndex(db, path)
        dbCon.commit()
        t2 = time.perf_counter()
        t = t2 - t1
        if args.verbose:
            print("Index time: {:0.4f} seconds".format(t))

        #Write changes to database
        if args.memory:
            print("Writing new database")
            t1 = time.perf_counter()
            try:
                os.remove(dbPath)
            except OSError:
                pass
            fileDBCon = sqlite3.connect(dbPath)
            dbCon.backup(fileDBCon)
            fileDBCon.close()
            t2 = time.perf_counter()
            t = t2 - t1
            if args.verbose:
                print("Write time: {:0.4f} seconds".format(t))

    except KeyboardInterrupt:
        print("Aborted!")

    #Start server
    try:
        baseinfo = {"name": __prog__, "version": __version__}
        server = Server(dbCon, baseinfo)
        server.daemon = True
        server.start()
        server.join()
    except KeyboardInterrupt:
        #Stop server and exit
        print("Exiting...")
# ########################################################################### #

# --------------------------------------------------------------------------- #
def reIndex(db, dirpath):
    '''(Re-)build the database

    :param db: Connection to the metadata database
    :type db: sqlite3.Cursor
    :param dirpath: The path of the working directory
    :type dirpath: string

    :raises: :class:``sqlite3.Error: Database error
    '''
    #Get all archives from database
    archives = []
    r = db.execute("SELECT relpath, recursive FROM archives;")
    a = r.fetchall()
    del r
    for item in a:
        abspath = os.path.normpath(os.path.abspath(os.path.join(dirpath, item[0])))
        #Extract archives
        if item[1]:
            subdirs = [os.path.join(abspath, name) for name in os.listdir(abspath) if os.path.isdir(os.path.join(abspath, name))]
            archives += [os.path.relpath(sub, dirpath) for sub in subdirs if os.path.isfile(os.path.join(sub, "archive.db"))]
        else:
            if os.path.isfile(os.path.join(abspath, "archive.db")):
                archives.append(item[0])
    if not archives:
        sys.exit("ERROR: No archives in database")

    #Set all channels and videos to inactive
    db.execute("UPDATE channels SET active = 0;")
    db.execute("UPDATE videos SET active = 0;")

    #Copy info
    for relpath in archives:
        abspath = os.path.normpath(os.path.abspath(os.path.join(dirpath, relpath)))
        #Try opening archive database
        try:
            archivedbPath = os.path.join(abspath, "archive.db")
            archivedb = sqlite3.connect(archivedbPath)
        except sqlite3.Error as e:
            print("ERROR: Unable to open '{}' archive database (Error: {})".format(os.path.basename(relpath), e))
            continue

        #Check archive db version
        try:
            version = archivedb.execute("SELECT dbversion FROM channel ORDER BY id DESC LIMIT 1;").fetchone()[0]
        except (sqlite3.Error, TypeError):
            version = 1
        if version < __archivedbversion__:
            print("ERROR: Archive database '{}' uses old database format. Please upgrade database using the latest version of ytarchiver".format(os.path.basename(relpath)))
            continue

        #Read channel info from archive database
        try:
            r = archivedb.execute("SELECT name,url,language,description,location,joined,links,profile,profileformat,banner,bannerformat,videos,lastupdate FROM channel ORDER BY id DESC LIMIT 1;")
            info = (relpath, abspath) + r.fetchone()
            del r
        except sqlite3.Error as e:
            print("ERROR: Unable to read channel info from '{}' archive database (Error: {})".format(os.path.basename(relpath), e))
            continue

        #Add or update channel info and get channel id
        try:
            insert = "INSERT INTO channels(relpath,abspath,name,url,language,description,location,joined,links,profile,profileformat,banner,bannerformat,videos,lastupdate,active) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1);"
            db.execute(insert, info)
        except sqlite3.Error:
            try:
                info = info[1:] + (relpath,)
                update = "UPDATE channels SET abspath=?,name=?,url=?,language=?,description=?,location=?,joined=?,links=?,profile=?,profileformat=?,banner=?,bannerformat=?,videos=?,lastupdate=?,active=1 WHERE relpath = ?;"
                db.execute(update, info)
            except sqlite3.Error as e:
                print("ERROR: Unable to write channel info from '{}' (Error: {})".format(os.path.basename(relpath), e))
                continue
        cmd = "SELECT id FROM channels WHERE relpath = ?"
        r = db.execute(cmd, (relpath,)).fetchone()
        channelID = r[0]
        del r

        #Read video info
        try:
            r = archivedb.execute("SELECT youtubeID,title,timestamp,description,subtitles,filename,thumb,thumbformat,duration,tags,language,width,height,resolution,viewcount,likecount,dislikecount,statisticsupdated,chapters FROM videos;")
            videos = r.fetchall()
            del r
        except sqlite3.Error as e:
            print("ERROR: Unable to read videos from '{}' archive database (Error: {})".format(os.path.basename(relpath), e))
            continue

        #Add or update video info
        try:
            for video in videos:
                #Get video id and convert filename to absolute file path
                videoID = video[0]
                info = list(video[1:])
                info[4] = os.path.join(abspath, info[4])
                info = tuple(info)
                try:
                    insert = "INSERT INTO videos(id,channelID,title,timestamp,description,subtitles,filepath,thumb,thumbformat,duration,tags,language,width,height,resolution,viewcount,likecount,dislikecount,statisticsupdated, chapters, active) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1);"
                    db.execute(insert, (videoID, channelID) + info)
                except sqlite3.Error:
                    update = "UPDATE videos SET channelID=?,title=?,timestamp=?,description=?,subtitles=?,filepath=?,thumb=?,thumbformat=?,duration=?,tags=?,language=?,width=?,height=?,resolution=?,viewcount=?,likecount=?,dislikecount=?,statisticsupdated=?,chapters=?,active=1 WHERE id = ?;"
                    db.execute(update, (channelID,) + info + (videoID,))
        except sqlite3.Error as e:
            print("ERROR: Unable to write video info from '{}' (Error: {})".format(os.path.basename(relpath), e))
            continue

        #Close archive database
        archivedb.close()

    #Update info fields
    videos = db.execute("SELECT count(*) FROM videos WHERE active = 1;").fetchone()[0]
    channels = db.execute("SELECT count(*) FROM channels WHERE active = 1;").fetchone()[0]
    db.execute("UPDATE info SET lastupdate = ?, videos = ?, channels = ? WHERE id = 1", (int(time.time()), videos, channels))
# ########################################################################### #

# --------------------------------------------------------------------------- #
def connectDB(path, checkThread=True):
    '''Connect to existing db and upgrade it if necessary

    :param path: Path at which to store the new database
    :type path: string
    :param checkThread: Whether sqlite3 should check the thread (default: True)
    :type checkThread: boolean

    :raises: :class:``sqlite3.Error: Unable to create database

    :returns: Connection to database
    :rtype: sqlite3.Connection
    '''

    #Connect to database
    dbCon = sqlite3.connect(path, check_same_thread=checkThread)
    db = dbCon.cursor()

    #Get database version
    try:
        r = db.execute("SELECT dbversion FROM info ORDER BY id DESC LIMIT 1;")
        version = r.fetchone()[0]
        del r
    except (sqlite3.Error, TypeError):
        sys.exit("ERROR: Unsupported database!")

    #Check if not up to date
    if version < __dbversion__:
        print("Upgrading database")
        try:
            #Perform upgrade to version 2
            if version < 2:
                #Clear video database
                db.execute("DELETE FROM videos")
                #Add new columns
                db.execute('ALTER TABLE videos ADD COLUMN language TEXT NOT NULL;')
                db.execute('ALTER TABLE videos ADD COLUMN width INTEGER NOT NULL;')
                db.execute('ALTER TABLE videos ADD COLUMN height INTEGER NOT NULL;')
                db.execute('ALTER TABLE videos ADD COLUMN resolution TEXT NOT NULL;')
                db.execute('ALTER TABLE videos ADD COLUMN viewcount INTEGER;')
                db.execute('ALTER TABLE videos ADD COLUMN likecount INTEGER;')
                db.execute('ALTER TABLE videos ADD COLUMN dislikecount INTEGER;')
                db.execute('ALTER TABLE videos ADD COLUMN statisticsupdated INTEGER NOT NULL;')
                #Update db version
                version = 2
                db.execute("UPDATE info SET dbversion = ? WHERE id = 1", (version,))
                dbCon.commit()
            #Perform upgrade to version 3
            if version < 3:
                #Add active channel and video column
                db.execute('ALTER TABLE channels ADD COLUMN active INTEGER NOT NULL DEFAULT 0;')
                db.execute('ALTER TABLE videos ADD COLUMN active INTEGER NOT NULL DEFAULT 0;')
                #Update db version
                version = 3
                db.execute("UPDATE info SET dbversion = ? WHERE id = 1", (version,))
                dbCon.commit()
            #Perform upgrade to version 4
            if version < 4:
                #Add active channel and video column
                db.execute('ALTER TABLE videos ADD COLUMN chapters TEXT;')
                #Update db version
                version = 4
                db.execute("UPDATE info SET dbversion = ? WHERE id = 1", (version,))
                dbCon.commit()
        except sqlite3.Error as e:
            dbCon.rollback()
            dbCon.close()
            sys.exit("ERROR: Unable to upgrade database (\"{}\")".format(e))

    dbCon.commit()

    #Return database connection
    return dbCon
# ########################################################################### #

# --------------------------------------------------------------------------- #
def createDB(path, checkThread=True):
    '''Create database with the required tables

    :param path: Path at which to store the new database
    :type path: string
    :param checkThread: Whether sqlite3 should check the thread (default: True)
    :type checkThread: boolean

    :raises: :class:``sqlite3.Error: Unable to create database

    :returns: Connection to the newly created database
    :rtype: sqlite3.Connection
    '''
    infoCmd = """ CREATE TABLE IF NOT EXISTS info (
                       id INTEGER PRIMARY KEY AUTOINCREMENT UNIQUE NOT NULL,
                       lastupdate INTEGER NOT NULL,
                       channels INTEGER NOT NULL,
                       videos INTEGER NOT NULL,
                       dbversion INTEGER NOT NULL
                  ); """

    archivesCmd = """ CREATE TABLE IF NOT EXISTS archives (
                       id INTEGER PRIMARY KEY AUTOINCREMENT UNIQUE NOT NULL,
                       relpath TEXT NOT NULL,
                       abspath TEXT NOT NULL,
                       recursive BOOLEAN NOT NULL
                  ); """

    channelsCmd = """ CREATE TABLE IF NOT EXISTS channels (
                       id INTEGER PRIMARY KEY AUTOINCREMENT UNIQUE NOT NULL,
                       relpath TEXT UNIQUE NOT NULL,
                       abspath TEXT UNIQUE NOT NULL,
                       name TEXT NOT NULL,
                       url TEXT NOT NULL,
                       language TEXT NOT NULL,
                       description TEXT,
                       location TEXT,
                       joined TEXT,
                       links TEXT,
                       profile BLOB,
                       profileformat TEXT,
                       banner BLOB,
                       bannerformat TEXT,
                       videos INTEGER NOT NULL,
                       lastupdate INTEGER NOT NULL,
                       active INTEGER NOT NULL DEFAULT 0
                  ); """

    videosCmd = """ CREATE TABLE IF NOT EXISTS videos (
                     id TEXT PRIMARY KEY UNIQUE NOT NULL,
                     channelID INTEGER NOT NULL,
                     title TEXT NOT NULL,
                     timestamp INTEGER NOT NULL,
                     description TEXT,
                     subtitles TEXT,
                     filepath TEXT NOT NULL,
                     thumb BLOB,
                     thumbformat TEXT,
                     duration INTEGER,
                     tags TEXT,
                     language TEXT NOT NULL,
                     width INTEGER NOT NULL,
                     height INTEGER NOT NULL,
                     resolution TEXT NOT NULL,
                     viewcount INTEGER,
                     likecount INTEGER,
                     dislikecount INTEGER,
                     statisticsupdated INTEGER NOT NULL,
                     active INTEGER NOT NULL DEFAULT 0,
                     chapters TEXT
                ); """

    #Create database
    dbCon = sqlite3.connect(path, check_same_thread=checkThread)
    db = dbCon.cursor()
    #Set encoding
    db.execute("pragma encoding=UTF8")
    #Create tables
    db.execute(infoCmd)
    db.execute("INSERT INTO info(lastupdate, channels, videos, dbversion) VALUES(?,?,?,?)", (0, 0, 0, __dbversion__))
    db.execute(archivesCmd)
    db.execute(channelsCmd)
    db.execute(videosCmd)
    dbCon.commit()
    #Return database connection
    return dbCon
# ########################################################################### #

# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    main(sys.argv)
# ########################################################################### #
