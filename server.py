#!/usr/bin/env python3
''' Front-end server for archivetube using flask '''

import threading
import sqlite3
import flask
import waitress

# =========================================================================== #
class Server(threading.Thread):
    '''
    Front-end server for archivetube using flask
    '''

    # --------------------------------------------------------------------------- #
    def __init__(self, dbPath, *args, **kw):
        '''
        Initialize the server
        '''
        #Call superclass init
        super(Server, self).__init__(*args, **kw)
        #Setup server
        self.app = flask.Flask("archivetube")
        self.db = sqlite3.connect(dbPath, check_same_thread=False)
        #Add routes
        self.app.add_url_rule("/", "home", self.getHome)
        self.app.add_url_rule("/watch", "watch", self.getWatch)
        self.app.add_url_rule("/res/thumb/<videoID>", "thumb", self.getThumbnail)
        self.app.add_url_rule("/res/profile/<channelID>", "profile", self.getProfile)
        self.app.add_url_rule("/res/banner/<channelID>", "banner", self.getBanner)
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    def run(self):
        '''
        Start the server
        '''
        waitress.serve(self.app)
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    def getHome(self):
        '''
        Return the landing page
        '''
        return "archivetube home" #Just for testing
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    def getWatch(self):
        '''
        Return the video watch page
        '''
        #Read video id
        videoID = flask.request.args.get("v")
        #If no id supplied, redirect to home
        if not videoID:
            return flask.redirect(flask.url_for("home"))

        #Get info from database
        r = self.db.execute("SELECT channelID,title,timestamp,description,subtitles,filepath,duration,tags FROM videos WHERE id = ?", (videoID,))
        video = r.fetchone()
        del r
        #Check if video with this id is in database
        if not video:
            return "Video not found", 404
        return "{}".format(video) #Just for testing
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    def getThumbnail(self, videoID):
        '''
        Return the video thumbnail
        '''
        #If no id supplied, return 404
        if not videoID:
            return '', 404

        #Get info from database
        r = self.db.execute("SELECT thumb,thumbformat FROM videos WHERE id = ?", (videoID,))
        thumb = r.fetchone()
        del r
        #If not found, return 404
        if not thumb or not thumb[0]:
            return '', 404
        #Respond with image
        r = flask.make_response(thumb[0])
        r.headers.set('Content-Type', thumb[1])
        return r
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    def getProfile(self, channelID):
        '''
        Return the profile picture of a channel
        '''
        #If no id supplied, return 404
        if not channelID:
            return '', 404

        #Get info from database
        r = self.db.execute("SELECT profile,profileformat FROM channels WHERE id = ?", (channelID,))
        profile = r.fetchone()
        del r
        #If not found, return 404
        if not profile or not profile[0]:
            return '', 404
        #Respond with image
        r = flask.make_response(profile[0])
        r.headers.set('Content-Type', profile[1])
        return r
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    def getBanner(self, channelID):
        '''
        Return the banner image of a channel
        '''
        #If no id supplied, return 404
        if not channelID:
            return '', 404

        #Get info from database
        r = self.db.execute("SELECT banner,bannerformat FROM channels WHERE id = ?", (channelID,))
        banner = r.fetchone()
        del r
        #If not found, return 404
        if not banner or not banner[0]:
            return '', 404
        #Respond with image
        r = flask.make_response(banner[0])
        r.headers.set('Content-Type', banner[1])
        return r
    # ########################################################################### #

# /////////////////////////////////////////////////////////////////////////// #
