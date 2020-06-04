#!/usr/bin/env python3
''' Front-end server for archivetube using flask '''

import os
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
        self.db.row_factory = sqlite3.Row
        #Add routes
        self.app.add_url_rule("/", "home", self.getHome)
        self.app.add_url_rule("/watch", "watch", self.getWatch)
        self.app.add_url_rule("/channel/<channelID>/", "channel", self.getChannel, defaults={"func": "home", "page": None})
        self.app.add_url_rule("/channel/<channelID>/<func>/", "channel-func", self.getChannel, defaults={"page": None})
        self.app.add_url_rule("/channel/<channelID>/<func>/page/<int:page>/", "channel-page", self.getChannel)
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
    def getChannel(self, channelID, func, page):
        '''
        Return the channel page
        '''
        #If no id supplied, return 404
        if not channelID:
            return '', 404

        #Get info from database
        r = self.db.execute("SELECT name,description,location,joined,links FROM channels WHERE id = ?", (channelID,))
        data = r.fetchone()
        del r
        if not data or not data["name"]:
            return '', 404
        msg = "<h1>{}</h1>".format(data["name"])
        if data["description"]:
            msg += "<br><br>{}".format(data["description"].replace("\n", "<br>"))
        msg += "<br><br>Func: {}, Page: {}".format(func, page)
        return flask.render_template("channel.html", title=data["name"], msg=msg)
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
        data = r.fetchone()
        del r
        #If not found, return 404
        if not data or not data["thumb"]:
            return '', 404
        #Respond with image
        r = flask.make_response(data["thumb"])
        r.headers.set('Content-Type', data["thumbformat"])
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
        data = r.fetchone()
        del r
        #If not found, return 404
        if not data or not data["profile"]:
            return '', 404
        #Respond with image
        r = flask.make_response(data["profile"])
        r.headers.set('Content-Type', data["profileformat"])
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
        data = r.fetchone()
        del r
        #If not found, return 404
        if not data or not data["banner"]:
            return '', 404
        #Respond with image
        r = flask.make_response(data["banner"])
        r.headers.set('Content-Type', data["bannerformat"])
        return r
    # ########################################################################### #

# /////////////////////////////////////////////////////////////////////////// #
