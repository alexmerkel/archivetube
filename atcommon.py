#!/usr/bin/env python3
''' atcommon - common functions for archivetube scripts '''

import sys
import sqlite3

__prog__ = "archivetube"
__version__ = "0.4.0"
__dbversion__ = 5
__archivedbversion__ = 5

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

    #Upgrade database
    upgradeDB(dbCon)

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
                       dbversion INTEGER NOT NULL,
                       statisticsupdated INTEGER
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

    overallCmd = """ CREATE TABLE IF NOT EXISTS statsOverall (
                      id INTEGER PRIMARY KEY UNIQUE NOT NULL,
                      timestamp INTEGER NOT NULL,
                      videos INTEGER NOT NULL,
                      v8k INTEGER NOT NULL,
                      fraction8k REAL NOT NULL,
                      v4k INTEGER NOT NULL,
                      fraction4k REAL NOT NULL,
                      vFullHD INTEGER NOT NULL,
                      fractionFullHD REAL NOT NULL,
                      vHD INTEGER NOT NULL,
                      fractionHD REAL NOT NULL,
                      vSD INTEGER NOT NULL,
                      fractionSD REAL NOT NULL,
                      vLD INTEGER NOT NULL,
                      fractionLD REAL NOT NULL,
                      subtitles INTEGER NOT NULL,
                      fractionSubtitles REAL NOT NULL,
                      chapters INTEGER NOT NULL,
                      fractionChapters REAL NOT NULL,
                      totalDuration INTEGER NOT NULL,
                      avgDuration REAL NOT NULL
                 ); """

    weeklyCmd = """ CREATE TABLE IF NOT EXISTS statsWeekly (
                     id INTEGER PRIMARY KEY UNIQUE NOT NULL,
                     timestamp INTEGER NOT NULL,
                     year INTEGER NOT NULL,
                     week INTEGER NOT NULL,
                     mondaydate TEXT NOT NULL,
                     sundaydate TEXT NOT NULL,
                     videos INTEGER NOT NULL,
                     v8k INTEGER NOT NULL,
                     fraction8k REAL NOT NULL,
                     v4k INTEGER NOT NULL,
                     fraction4k REAL NOT NULL,
                     vFullHD INTEGER NOT NULL,
                     fractionFullHD REAL NOT NULL,
                     vHD INTEGER NOT NULL,
                     fractionHD REAL NOT NULL,
                     vSD INTEGER NOT NULL,
                     fractionSD REAL NOT NULL,
                     vLD INTEGER NOT NULL,
                     fractionLD REAL NOT NULL,
                     subtitles INTEGER NOT NULL,
                     fractionSubtitles REAL NOT NULL,
                     chapters INTEGER NOT NULL,
                     fractionChapters REAL NOT NULL,
                     totalDuration INTEGER NOT NULL,
                     avgDuration REAL NOT NULL
                ); """

    plotCmd = """ CREATE TABLE IF NOT EXISTS statsPlots (
                   name TEXT PRIMARY KEY UNIQUE NOT NULL,
                   timestamp INTEGER NOT NULL,
                   png BLOB,
                   svgLight BLOB,
                   svgDark BLOB
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
    db.execute(overallCmd)
    db.execute(weeklyCmd)
    db.execute(plotCmd)
    dbCon.commit()
    #Return database connection
    return dbCon
# ########################################################################### #

# --------------------------------------------------------------------------- #
def upgradeDB(dbCon):
    '''Create database with the required tables

    :param dbCon: Connection to the database
    :type dbCon: sqlite3.Connection

    :raises: :class:``sqlite3.Error: Unable to upgrade database
    '''
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
            #Perform upgrade to version 5
            if version < 5:
                #Add statistics updated to info
                db.execute('ALTER TABLE info ADD COLUMN statisticsupdated INTEGER;')
                #Add overall statistics table
                overallCmd = """ CREATE TABLE IF NOT EXISTS statsOverall (
                                  id INTEGER PRIMARY KEY UNIQUE NOT NULL,
                                  timestamp INTEGER NOT NULL,
                                  videos INTEGER NOT NULL,
                                  v8k INTEGER NOT NULL,
                                  fraction8k REAL NOT NULL,
                                  v4k INTEGER NOT NULL,
                                  fraction4k REAL NOT NULL,
                                  vFullHD INTEGER NOT NULL,
                                  fractionFullHD REAL NOT NULL,
                                  vHD INTEGER NOT NULL,
                                  fractionHD REAL NOT NULL,
                                  vSD INTEGER NOT NULL,
                                  fractionSD REAL NOT NULL,
                                  vLD INTEGER NOT NULL,
                                  fractionLD REAL NOT NULL,
                                  subtitles INTEGER NOT NULL,
                                  fractionSubtitles REAL NOT NULL,
                                  chapters INTEGER NOT NULL,
                                  fractionChapters REAL NOT NULL,
                                  totalDuration INTEGER NOT NULL,
                                  avgDuration REAL NOT NULL
                             ); """
                db.execute(overallCmd)
                #Add weekly statistics table
                weeklyCmd = """ CREATE TABLE IF NOT EXISTS statsWeekly (
                                 id INTEGER PRIMARY KEY UNIQUE NOT NULL,
                                 timestamp INTEGER NOT NULL,
                                 year INTEGER NOT NULL,
                                 week INTEGER NOT NULL,
                                 mondaydate TEXT NOT NULL,
                                 sundaydate TEXT NOT NULL,
                                 videos INTEGER NOT NULL,
                                 v8k INTEGER NOT NULL,
                                 fraction8k REAL NOT NULL,
                                 v4k INTEGER NOT NULL,
                                 fraction4k REAL NOT NULL,
                                 vFullHD INTEGER NOT NULL,
                                 fractionFullHD REAL NOT NULL,
                                 vHD INTEGER NOT NULL,
                                 fractionHD REAL NOT NULL,
                                 vSD INTEGER NOT NULL,
                                 fractionSD REAL NOT NULL,
                                 vLD INTEGER NOT NULL,
                                 fractionLD REAL NOT NULL,
                                 subtitles INTEGER NOT NULL,
                                 fractionSubtitles REAL NOT NULL,
                                 chapters INTEGER NOT NULL,
                                 fractionChapters REAL NOT NULL,
                                 totalDuration INTEGER NOT NULL,
                                 avgDuration REAL NOT NULL
                            ); """
                db.execute(weeklyCmd)
                #Add plots table
                plotCmd = """ CREATE TABLE IF NOT EXISTS statsPlots (
                               name TEXT PRIMARY KEY UNIQUE NOT NULL,
                               timestamp INTEGER NOT NULL,
                               png BLOB,
                               svgLight BLOB,
                               svgDark BLOB
                          ); """
                db.execute(plotCmd)
                #Update db version
                version = 5
                db.execute("UPDATE info SET dbversion = ? WHERE id = 1", (version,))
                dbCon.commit()
        except sqlite3.Error as e:
            dbCon.rollback()
            dbCon.close()
            sys.exit("ERROR: Unable to upgrade database (\"{}\")".format(e))

    dbCon.commit()
# ########################################################################### #
