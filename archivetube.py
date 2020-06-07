#!/usr/bin/env python3
''' archivetube - web interface for archived videos '''

import os
import sys
import sqlite3
import argparse
from server import Server


# --------------------------------------------------------------------------- #
def main(args):
    '''The main archive tube function

    :param args: The command line arguments given by the user
    :type args: list
    '''
    parser = argparse.ArgumentParser(prog="archivetube", description="Serve a web interface for archived videos")
    parser.add_argument("-r", "--recursive", action="store_const", dest="recursive", const=True, default=False, help="Add all archives in subdirectories of the specified location to the database")
    parser.add_argument("-f", "--folder", action="store", dest="folder", help="Add an archive directory to the database (Path will be stored as relative to DIR)")
    parser.add_argument("DIR", help="The directory to work in")

    args = parser.parse_args()

    #Validate path
    path = os.path.normpath(os.path.abspath(args.DIR))
    if not os.path.isdir(path):
        parser.error("An existing directory must be specified")

    #Check if database exists
    dbPath = os.path.join(path, "tube.db")
    if not os.path.isfile(dbPath):
        #No database found, write message
        print("No database found, creating one")

    try:
        #Connect to database
        try:
            dbCon = createOrConnectDB(dbPath)
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

        #Print status
        print("(Re-)building index")
#TODO Reactivate        reIndex(db, path)

        #Write changes to database
        if dbCon:
            dbCon.commit()
            dbCon.close()
    except KeyboardInterrupt:
        print("Aborted!")

    #Start server
    try:
        server = Server(dbPath)
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
        print("ERROR: No archives in database")
        return

    #Copy info
    for relpath in archives:
        abspath = os.path.normpath(os.path.abspath(os.path.join(dirpath, relpath)))
        #Try opening archive database
        try:
            archivedbPath = os.path.join(abspath, "archive.db")
            archivedb = sqlite3.connect(archivedbPath)
        except sqlite3.Error:
            print("ERROR: Unable to open '{}' archive database".format(os.path.basename(relpath)))
            return

        #Read channel info from archive database
        try:
            r = archivedb.execute("SELECT name,url,language,description,location,joined,links,profile,profileformat,banner,bannerformat FROM channel ORDER BY id DESC LIMIT 1;")
            info = (relpath, abspath) + r.fetchone()
        except sqlite3.Error:
            print("ERROR: Unable to read channel info from '{}' archive database".format(os.path.basename(relpath)))
            return

        #Add or update channel info and get channel id
        try:
            insert = "INSERT INTO channels(relpath,abspath,name,url,language,description,location,joined,links,profile,profileformat,banner,bannerformat) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?);"
            db.execute(insert, info)
        except sqlite3.Error:
            try:
                info = info[1:] + (relpath,)
                update = "UPDATE channels SET abspath=?,name=?,url=?,language=?,description=?,location=?,joined=?,links=?,profile=?,profileformat=?,banner=?,bannerformat=? WHERE relpath = ?;"
                db.execute(update, info)
            except sqlite3.Error:
                print("ERROR: Unable to write channel info from '{}'".format(os.path.basename(relpath)))
                return
        cmd = "SELECT id FROM channels WHERE relpath = ?"
        r = db.execute(cmd, (relpath,)).fetchone()
        channelID = r[0]

        #Read video info
        try:
            r = archivedb.execute("SELECT youtubeID,title,timestamp,description,subtitles,filename,thumb,thumbformat,duration,tags FROM videos;")
            videos = r.fetchall()
        except sqlite3.Error:
            print("ERROR: Unable to read videos from '{}' archive database".format(os.path.basename(relpath)))
            return

        #Add or update video info
        try:
            for video in videos:
                #Get video id and convert filename to absolute file path
                videoID = video[0]
                info = list(video[1:])
                info[4] = os.path.join(abspath, info[4])
                info = tuple(info)
                try:
                    insert = "INSERT INTO videos(id,channelID,title,timestamp,description,subtitles,filepath,thumb,thumbformat,duration,tags) VALUES(?,?,?,?,?,?,?,?,?,?,?);"
                    db.execute(insert, (videoID, channelID) + info)
                except sqlite3.Error:
                    update = "UPDATE videos SET channelID=?,title=?,timestamp=?,description=?,subtitles=?,filepath=?,thumb=?,thumbformat=?,duration=?,tags=? WHERE id = ?;"
                    db.execute(update, (channelID,) + info + (videoID,))
        except sqlite3.Error:
            print("ERROR: Unable to write video info from '{}'".format(os.path.basename(relpath)))
            return

        #Close archive database
        archivedb.close()
# ########################################################################### #

# --------------------------------------------------------------------------- #
def createOrConnectDB(path):
    '''Create database with the required tables

    :param path: Path at which to store the new database
    :type path: string

    :raises: :class:``sqlite3.Error: Unable to create database

    :returns: Connection to the newly created database
    :rtype: sqlite3.Connection
    '''
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
                       bannerformat TEXT
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
                     tags TEXT
                ); """

    #Create database
    dbCon = sqlite3.connect(path)
    db = dbCon.cursor()
    #Set encoding
    db.execute("pragma encoding=UTF8")
    #Create tables
    db.execute(archivesCmd)
    db.execute(channelsCmd)
    db.execute(videosCmd)
    #Return database connection
    return dbCon
# ########################################################################### #

# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    main(sys.argv)
# ########################################################################### #
