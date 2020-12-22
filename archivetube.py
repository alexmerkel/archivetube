#!/usr/bin/env python3
''' archivetube - web interface for archived videos '''

import os
import sys
import sqlite3
import argparse
import time
from server import Server
import atcommon as atc
import atstatistics as ats

# --------------------------------------------------------------------------- #
def main(args):
    '''The main archive tube function

    :param args: The command line arguments given by the user
    :type args: list
    '''
    parser = argparse.ArgumentParser(prog=atc.__prog__, description="Serve a web interface for archived videos")
    parser.add_argument("-v", "--verbose", action="store_const", dest="verbose", const=True, default=False, help="Print more status info")
    parser.add_argument("-m", "--memory", action="store_const", dest="memory", const=True, default=False, help="Keep whole database in memory (faster, but requires a lot of memory)")
    parser.add_argument("-r", "--recursive", action="store_const", dest="recursive", const=True, default=False, help="Add all archives in subdirectories of the specified location to the database")
    parser.add_argument("-f", "--folder", action="store", dest="folder", help="Add an archive directory to the database (path will be stored as relative to DIR). This will force -i and -s")
    parser.add_argument("-i", "--index", action="store_const", dest="index", const=True, default=False, help="(Re-)create the index (this might take a while)")
    parser.add_argument("-s", "--statistics", action="store_const", dest="statistics", const=True, default=False, help="(Re-)calculate the statistics (this might take a while)")
    parser.add_argument("-V", "--version", action="version", version='%(prog)s {}'.format(atc.__version__))
    parser.add_argument("DIR", help="The directory to work in")

    args = parser.parse_args()

    #Validate path
    path = os.path.normpath(os.path.abspath(args.DIR))
    if not os.path.isdir(path):
        parser.error("An existing directory must be specified")

    #Check tasks
    taskIndex = False
    taskStats = False
    if args.index or args.folder:
        taskIndex = True
    if args.statistics or args.folder:
        taskStats = True

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
                    fileDBCon = atc.connectDB(dbPath)
                    dbCon = sqlite3.connect(":memory:", check_same_thread=False)
                    fileDBCon.backup(dbCon)
                    fileDBCon.close()
                else:
                    print("Connect to existing database")
                    dbCon = atc.connectDB(dbPath, checkThread=False)
                t2 = time.perf_counter()
                t = t2 - t1
                if args.verbose:
                    print("Read time: {:0.4f} seconds".format(t))
            else:
                #No database found
                print("No database found, creating one")
                if args.memory:
                    dbCon = atc.createDB(":memory:", checkThread=False)
                else:
                    dbCon = atc.createDB(dbPath, checkThread=False)
        except sqlite3.Error as e:
            sys.exit("ERROR: Database error \"{}\"".format(e))

        #Check if folder to add to database
        if args.folder:
            rel = os.path.relpath(args.folder, path)
            if args.recursive:
                print("Adding archives in subdirectories of '{}' to the database".format(rel))
            else:
                print("Adding archive '{}' to the database".format(rel))
            cmd = "INSERT INTO archives(relpath, abspath, recursive) VALUES(?,?,?)"
            dbCon.execute(cmd, (rel, args.folder, args.recursive))
            if args.verbose:
                print("Forcing index and statistics")

        #(Re-)indexing
        if taskIndex:
            print("(Re-)building index")
            t1 = time.perf_counter()
            db = dbCon.cursor()
            reIndex(db, path)
            dbCon.commit()
            t2 = time.perf_counter()
            t = t2 - t1
            if args.verbose:
                print("Index time: {:0.4f} seconds".format(t))
        else:
            if args.verbose:
                print("Skip indexing")

        #(Re-)calculating statistics
        if taskStats:
            print("(Re-)calculating statistics")
            t1 = time.perf_counter()
            dbCon.row_factory = sqlite3.Row
            db = dbCon.cursor()
            try:
                ats.run(db, verbose=args.verbose)
            except ats.StatisticsError as e:
                sys.exit("ERROR in statistics: {}".format(e))
            dbCon.commit()
            t2 = time.perf_counter()
            t = t2 - t1
            if args.verbose:
                print("Statistics time: {:0.4f} seconds".format(t))
        else:
            if args.verbose:
                print("Skip calculting statistics")

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
        baseinfo = {"name": atc.__prog__, "version": atc.__version__}
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

    :param db: Connection to the tube database
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
        if version < atc.__archivedbversion__:
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
if __name__ == "__main__":
    main(sys.argv)
# ########################################################################### #
