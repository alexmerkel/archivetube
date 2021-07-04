#!/usr/bin/env python3
''' Front-end server for archivetube using flask '''

import os
import io
import threading
import locale
import sqlite3
import math
import mimetypes
import time
from datetime import datetime, timezone
from pycountry import languages
from PIL import Image
import flask
import waitress
from urlfinder import URLFinder


__videosPerPage__ = 25
__latestVideos__ = 4

# =========================================================================== #
class Server(threading.Thread):
    '''
    Front-end server for archivetube using flask
    '''

    # --------------------------------------------------------------------------- #
    def __init__(self, dbCon, baseinfo, listen, *args, **kw):
        '''
        Initialize the server

        :param dbCon: Connection to the database
        :type dbCon: sqlite3.Connection
        :param baseinfo: A dict containing the name and the version
        :type baseinfo: dict
        :param listen: ip:port combination the server should listen on
        :type listen: string
        '''
        #Call superclass init
        super(Server, self).__init__(*args, **kw)
        self._listen = listen
        #Set locale
        locale.setlocale(locale.LC_ALL, '')
        #Define url finder
        self._urlfinder = URLFinder()
        #Setup database
        self._db = dbCon
        self._db.row_factory = sqlite3.Row
        #Base info dict
        self._baseinfo = baseinfo
        r = self._db.execute("SELECT id,name FROM channels WHERE active = 1 ORDER BY name COLLATE NOCASE ASC")
        data = r.fetchall()
        del r
        channels = []
        for c in data:
            if c and c["name"]:
                channels.append(dict(c))
        self._baseinfo["channels"] = channels
        #Setup server
        self._app = flask.Flask(self._baseinfo["name"])
        #Add routes
        self._app.add_url_rule("/", "home", self._getHome)
        self._app.add_url_rule("/watch", "watch", self._getWatch)
        self._app.add_url_rule("/channel/<channelID>/", "channel", self._getChannel, defaults={"func": "home", "page": None, "sorting": "new"})
        self._app.add_url_rule("/channel/<channelID>/<func>/", "channel-func", self._getChannel, defaults={"page": None, "sorting": "new"})
        self._app.add_url_rule("/channel/<channelID>/<func>/<sorting>/", "channel-sorting", self._getChannel, defaults={"page": None})
        self._app.add_url_rule("/channel/<channelID>/<func>/page/<int:page>/", "channel-page", self._getChannel, defaults={"sorting": "new"})
        self._app.add_url_rule("/channel/<channelID>/<func>/<sorting>/page/<int:page>/", "channel-page", self._getChannel)
        self._app.add_url_rule("/statistics", "statistics", self._getStatistics)
        self._app.add_url_rule("/res/thumb/<videoID>", "thumb", self._getThumbnail)
        self._app.add_url_rule("/res/video/<videoID>", "video", self._getVideo)
        self._app.add_url_rule("/res/subtitles/<videoID>", "subtitles", self._getSubtitles)
        self._app.add_url_rule("/res/chapters/<videoID>", "chapters", self._getChapters)
        self._app.add_url_rule("/res/profile/<channelID>", "profile", self._getProfile)
        self._app.add_url_rule("/res/banner/<channelID>", "banner", self._getBanner)
        self._app.add_url_rule("/res/plot/<plotName>", "plot", self._getPlot)
        #Add error handlers
        self._app.register_error_handler(403, self._getError)
        self._app.register_error_handler(404, self._getError)
        self._app.register_error_handler(410, self._getError)
        self._app.register_error_handler(500, self._getError)
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    def run(self):
        '''
        Start the server
        '''
        urls = ["http://{}/".format(u) for u in self._listen.split()]
        print("Starting server at {}".format(", ".join(urls)))
        waitress.serve(self._app, threads=os.cpu_count(), listen=self._listen)
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    def _getHome(self):
        '''
        Return the landing page
        '''
        #Get channel info from database
        r = self._db.execute("SELECT id,name,videos,lastupdate FROM channels WHERE active = 1 ORDER BY name COLLATE NOCASE ASC")
        data = r.fetchall()
        del r
        channels = []
        for c in data:
            if c and c["name"]:
                c = dict(c)
                c["agostring"] = self._timestampToHumanString(c["lastupdate"])
                c["lastupdate"] = self._timestampToLocalTimeString(c["lastupdate"])
                channels.append(c)
        if not channels:
            return self._getErrorPage(404, "No channel data in database")
        #Get general info from database
        r = self._db.execute("SELECT lastupdate,channels,videos FROM info ORDER BY id DESC LIMIT 1;")
        info = dict(r.fetchone())
        del r
        info["agostring"] = self._timestampToHumanString(info["lastupdate"])
        info["lastupdate"] = self._timestampToLocalTimeString(info["lastupdate"])
        #Render template
        return flask.render_template("home.html", channels=channels, info=info, base=self._baseinfo)
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    def _getWatch(self):
        '''
        Return the video watch page
        '''
        #Read video id
        videoID = flask.request.args.get("v")
        #If no id supplied, redirect to home
        if not videoID:
            return flask.redirect(flask.url_for("home"))

        #Get video info from database
        r = self._db.execute("SELECT id,channelID,title,timestamp,description,subtitles,filepath,tags,language,viewcount,statisticsupdated,likecount,dislikecount,chapters FROM videos WHERE id = ?", (videoID,))
        video = r.fetchone()
        del r
        if not video:
            return self._getErrorPage(404, "Video not found")
        video = dict(video)
        #Get channel from database
        r = self._db.execute("SELECT id,name,videos,lastupdate FROM channels WHERE id = ?", (video["channelID"],))
        channel = r.fetchone()
        del r
        if not channel:
            return self._getErrorPage(404, "Video channel not found")
        channel = dict(channel)
        #Convert timestamp
        channel["lastupdate"] = self._timestampToHumanString(channel["lastupdate"])
        #Prepare statistics
        video["views"] = self._intToHuman(video["viewcount"])
        video["viewcount"] = self._intToStr(video["viewcount"])
        video["likes"] = self._intToHuman(video["likecount"])
        video["likecount"] = self._intToStr(video["likecount"])
        video["dislikes"] = self._intToHuman(video["dislikecount"])
        video["dislikecount"] = self._intToStr(video["dislikecount"])
        video["statisticsupdated"] = self._timestampToHumanString(video["statisticsupdated"])
        #Turn subtitles and chapters into boolean
        video["subtitles"] = bool(video["subtitles"])
        video["chapters"] = bool(video["chapters"])
        #Get channel language code and name
        if video["language"]:
            lang = languages.get(alpha_2=video["language"])
            video["language"] = lang.name
            video["lang"] = lang.alpha_2
        else:
            video["subtitles"] = False
            video["chapters"] = False
        #Get next video info from database
        r = self._db.execute("SELECT id,title,timestamp,duration,resolution,viewcount,statisticsupdated FROM videos WHERE channelID = ? AND timestamp > ? ORDER BY timestamp ASC LIMIT 1;", (channel["id"], video["timestamp"]))
        nextVideo = r.fetchone()
        del r
        if nextVideo:
            nextVideo = dict(nextVideo)
            #Convert timestamp
            nextVideo["duration"] = self._secToTime(nextVideo["duration"])
            nextVideo["agestring"] = self._timestampToHumanString(nextVideo["timestamp"])
            nextVideo["timestamp"] = self._timestampToLocalTimeString(nextVideo["timestamp"])
            nextVideo["views"] = self._intToHuman(nextVideo["viewcount"])
            nextVideo["statisticsupdated"] = self._timestampToHumanString(nextVideo["statisticsupdated"])
            nextVideo["quality"] = self._qualityLabel(nextVideo["resolution"])
        else:
            nextVideo = None
        #Get previous video info from database
        r = self._db.execute("SELECT id,title,timestamp,duration,resolution,viewcount,statisticsupdated FROM videos WHERE channelID = ? AND timestamp < ? ORDER BY timestamp DESC LIMIT 1;", (channel["id"], video["timestamp"]))
        previousVideo = r.fetchone()
        del r
        if previousVideo:
            previousVideo = dict(previousVideo)
            #Convert timestamp
            previousVideo["duration"] = self._secToTime(previousVideo["duration"])
            previousVideo["agestring"] = self._timestampToHumanString(previousVideo["timestamp"])
            previousVideo["timestamp"] = self._timestampToLocalTimeString(previousVideo["timestamp"])
            previousVideo["views"] = self._intToHuman(previousVideo["viewcount"])
            previousVideo["statisticsupdated"] = self._timestampToHumanString(previousVideo["statisticsupdated"])
            previousVideo["quality"] = self._qualityLabel(previousVideo["resolution"])
        else:
            previousVideo = None
        #Get latest video info from database
        r = self._db.execute("SELECT id,title,timestamp,duration,resolution,viewcount,statisticsupdated FROM videos WHERE channelID = ? ORDER BY timestamp DESC LIMIT 1", (channel["id"],))
        latestVideo = r.fetchone()
        del r
        if latestVideo:
            latestVideo = dict(latestVideo)
            #Convert timestamp
            latestVideo["duration"] = self._secToTime(latestVideo["duration"])
            latestVideo["agestring"] = self._timestampToHumanString(latestVideo["timestamp"])
            latestVideo["timestamp"] = self._timestampToLocalTimeString(latestVideo["timestamp"])
            latestVideo["views"] = self._intToHuman(latestVideo["viewcount"])
            latestVideo["statisticsupdated"] = self._timestampToHumanString(latestVideo["statisticsupdated"])
            latestVideo["quality"] = self._qualityLabel(latestVideo["resolution"])
            #Only show latest video if this or the next video is not the latest
            if latestVideo["id"] == video["id"] or latestVideo["id"] == nextVideo["id"]:
                latestVideo = None
        else:
            latestVideo = None
        #Only interested if subtitles exist or not
        video["subtitles"] = bool(video["subtitles"])
        #Convert timestamp
        video["agestring"] = self._timestampToHumanString(video["timestamp"])
        video["timestamp"] = self._timestampToLocalTimeString(video["timestamp"])
        #Get mime type
        video["mimetype"] = mimetypes.guess_type(video["filepath"])[0]
        #Convert links in description
        video["description"] = self._urlfinder.find(video["description"])
        #Render template
        return flask.render_template("watch.html", title=video["title"], video=video, nextVideo=nextVideo, previousVideo=previousVideo, latestVideo=latestVideo, channel=channel, base=self._baseinfo)
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    def _getChannel(self, channelID, func, page, sorting):
        '''
        Return the channel page
        '''
        #If no id supplied, return 404
        if not channelID:
            return self._getErrorPage(404, "No channel ID specified")

        #Get info from database
        r = self._db.execute("SELECT id,name,description,location,joined,links,videos,lastupdate FROM channels WHERE id = ?", (channelID,))
        data = r.fetchone()
        del r
        if not data or not data["name"]:
            return self._getErrorPage(404, "Unable to find channel")
        data = dict(data)
        # Get channel home
        if func == "home":
            #Get 4 latest videos
            cmd = "SELECT id,title,timestamp,duration,resolution,viewcount,statisticsupdated FROM videos WHERE channelID = ? ORDER BY timestamp DESC LIMIT {}".format(__latestVideos__)
            r = self._db.execute(cmd, (channelID,))
            videos = [dict(v) for v in r.fetchall()]
            del r
            #Convert timestamp and duration
            for v in videos:
                v["views"] = self._intToHuman(v["viewcount"])
                v["statisticsupdated"] = self._timestampToHumanString(v["statisticsupdated"])
                v["quality"] = self._qualityLabel(v["resolution"])
                v["duration"] = self._secToTime(v["duration"])
                v["agestring"] = self._timestampToHumanString(v["timestamp"])
                v["timestamp"] = self._timestampToLocalTimeString(v["timestamp"])
            data["lastupdate"] = self._timestampToHumanString(data["lastupdate"])
            #Convert links in description
            data["description"] = self._urlfinder.find(data["description"])
            #Render template
            return flask.render_template("channel-home.html", title=data["name"], info=data, videos=videos, base=self._baseinfo)
        #Get channel videos
        if func == "videos":
            #Calc number of pages
            data["maxpage"] = math.ceil(data["videos"]/__videosPerPage__)
            #Sanitize page number
            if not page or page < 1:
                page = 1
            if page > data["maxpage"]:
                page = data["maxpage"]
            data["page"] = page
            #Get sorting direction
            if sorting != "new":
                data["sorting"] = sorting
            if sorting == "old":
                sorting = "timestamp ASC"
            elif sorting == "view":
                sorting = "viewcount DESC"
            else:
                sorting = "timestamp DESC"
            #Query database
            cmd = "SELECT id,title,timestamp,duration,resolution,viewcount,statisticsupdated FROM videos WHERE channelID = ? ORDER BY {} LIMIT {} OFFSET {}".format(sorting, __videosPerPage__, (page - 1)*__videosPerPage__)
            r = self._db.execute(cmd, (channelID,))
            videos = [dict(v) for v in r.fetchall()]
            del r
            #Convert timestamp and duration
            for v in videos:
                v["views"] = self._intToHuman(v["viewcount"])
                v["statisticsupdated"] = self._timestampToHumanString(v["statisticsupdated"])
                v["quality"] = self._qualityLabel(v["resolution"])
                v["duration"] = self._secToTime(v["duration"])
                v["agestring"] = self._timestampToHumanString(v["timestamp"])
                v["timestamp"] = self._timestampToLocalTimeString(v["timestamp"])
            #Render template
            return flask.render_template("channel-videos.html", title=data["name"] + " - Videos", info=data, videos=videos, base=self._baseinfo)
        #Get channel info
        if func == "info":
            #Convert timestamp
            data["lastupdate"] = self._timestampToLocalTimeString(data["lastupdate"])
            #Convert links
            links = []
            if data["links"]:
                for l in data["links"].splitlines():
                    l = l.split('\t')
                    links.append({"pretty": l[0], "url": l[1]})
                data["links"] = links
            #Convert links in description
            data["description"] = self._urlfinder.find(data["description"])
            #Render template
            return flask.render_template("channel-info.html", title=data["name"] + " - Info", info=data, base=self._baseinfo)
        #Unknown func, redirect to channel home
        return flask.redirect(flask.url_for("channel", channelID=channelID))
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    def _getStatistics(self):
        '''
        Return the statistics page
        '''
        #Get last updated from database
        r = self._db.execute("SELECT statisticsupdated FROM info WHERE id=1;")
        data = r.fetchone()
        del r
        #If not found, no statistics were generated yet, return 404
        if not data or not data["statisticsupdated"]:
            return '', 404
        info = {"lastupdate": self._timestampToLocalTimeString(data["statisticsupdated"]), "agostring": self._timestampToHumanString(data["statisticsupdated"])}
        #Get latest stats from database
        r = self._db.execute("SELECT * FROM statsOverall ORDER BY timestamp DESC LIMIT 1;")
        data = r.fetchone()
        del r
        #If not found, no statistics were generated yet, return 404
        if not data:
            return '', 404
        info = {**info, **dict(data)}
        return flask.render_template("statistics.html", title=self._baseinfo["name"] + " - Statistics", info=info, base=self._baseinfo)
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    def _getThumbnail(self, videoID):
        '''
        Return the video thumbnail
        '''
        #If no id supplied, return 404
        if not videoID:
            return '', 404

        #Get info from database
        r = self._db.execute("SELECT thumb,thumbformat FROM videos WHERE id = ?", (videoID,))
        data = r.fetchone()
        del r
        #If not found, return 404
        if not data or not data["thumb"]:
            return '', 404
        #Try getting resize parameters
        if flask.request.args:
            try:
                width = self._floatOrNone(flask.request.args.get("w"))
                height = self._floatOrNone(flask.request.args.get("h"))
                relWidth = self._floatOrNone(flask.request.args.get("rw"))
                relHeight = self._floatOrNone(flask.request.args.get("rh"))
                cropLoc = flask.request.args.get("c")
                extra = flask.request.args.get("e")
                img = self._manipulateImage(data["thumb"], data["thumbformat"], width, height, relWidth, relHeight, cropLoc, extra)
            except ValueError:
                img = data["thumb"]
        else:
            img = data["thumb"]
        #Respond with image
        r = flask.make_response(img)
        r.headers.set('Content-Type', data["thumbformat"])
        r.cache_control.public = True
        r.cache_control.max_age = 300
        return r
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    def _getProfile(self, channelID):
        '''
        Return the profile picture of a channel
        '''
        #If no id supplied, return 404
        if not channelID:
            return '', 404

        #Get info from database
        r = self._db.execute("SELECT profile,profileformat FROM channels WHERE id = ?", (channelID,))
        data = r.fetchone()
        del r
        #If not found, return 404
        if not data or not data["profile"]:
            return '', 404
        #Try getting resize parameters
        if flask.request.args:
            try:
                width = self._floatOrNone(flask.request.args.get("w"))
                height = self._floatOrNone(flask.request.args.get("h"))
                relWidth = self._floatOrNone(flask.request.args.get("rw"))
                relHeight = self._floatOrNone(flask.request.args.get("rh"))
                cropLoc = flask.request.args.get("c")
                extra = flask.request.args.get("e")
                img = self._manipulateImage(data["profile"], data["profileformat"], width, height, relWidth, relHeight, cropLoc, extra)
            except ValueError:
                img = data["profile"]
        else:
            img = data["profile"]
        #Respond with image
        r = flask.make_response(img)
        r.headers.set('Content-Type', data["profileformat"])
        r.cache_control.public = True
        r.cache_control.max_age = 300
        return r
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    def _getBanner(self, channelID):
        '''
        Return the banner image of a channel
        '''
        #If no id supplied, return 404
        if not channelID:
            return '', 404

        #Get info from database
        r = self._db.execute("SELECT banner,bannerformat FROM channels WHERE id = ?", (channelID,))
        data = r.fetchone()
        del r
        #If not found, return 404
        if not data or not data["banner"]:
            return '', 404

        #Try getting resize parameters
        if flask.request.args:
            try:
                width = self._floatOrNone(flask.request.args.get("w"))
                height = self._floatOrNone(flask.request.args.get("h"))
                relWidth = self._floatOrNone(flask.request.args.get("rw"))
                relHeight = self._floatOrNone(flask.request.args.get("rh"))
                cropLoc = flask.request.args.get("c")
                extra = flask.request.args.get("e")
                img = self._manipulateImage(data["banner"], data["bannerformat"], width, height, relWidth, relHeight, cropLoc, extra)
            except ValueError:
                img = data["banner"]
        else:
            img = data["banner"]

        #Respond with image
        r = flask.make_response(img)
        r.headers.set('Content-Type', data["bannerformat"])
        r.cache_control.public = True
        r.cache_control.max_age = 300
        return r
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    def _getPlot(self, plotName):
        '''
        Return the plot with a given name incl. file extention
        '''
        #If no id supplied, return 404
        if not plotName:
            return '', 404

        #See if dark or light mode was requested
        darkMode = False
        if flask.request.args:
            try:
                mode = flask.request.args.get("m")
                if mode == "dark":
                    darkMode = True
            except ValueError:
                pass

        #Get requested file type
        name, ext = os.path.splitext(plotName)
        if ext == ".svg":
            field = "svgDark" if darkMode else "svgLight"
            mime = "image/svg+xml"
        else:
            field = "png"
            mime = "image/png"

        #Get plot from database
        cmd = "SELECT {} FROM statsPlots WHERE name = ?".format(field)
        r = self._db.execute(cmd, (name,))
        data = r.fetchone()
        del r
        #If not found, return 404
        if not data or not data[field]:
            return '', 404

        #Respond with image
        r = flask.make_response(data[field])
        r.headers.set('Content-Type', mime)
        r.cache_control.public = True
        r.cache_control.max_age = 300
        return r
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    def _getVideo(self, videoID):
        '''
        Return a video file
        '''
        #If no id supplied, return 404
        if not videoID:
            return '', 404

        #Get info from database
        r = self._db.execute("SELECT filepath FROM videos WHERE id = ?", (videoID,))
        data = r.fetchone()
        del r
        #If not found, return 404
        if not data or not data[0]:
            return '', 404

        #Respond with video
        return flask.send_from_directory(os.path.dirname(data[0]), os.path.basename(data[0]))
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    def _getSubtitles(self, videoID):
        '''
        Return subtitles of a video if it has any
        '''
        #If no id supplied, return 404
        if not videoID:
            return '', 404

        #Get info from database
        r = self._db.execute("SELECT subtitles FROM videos WHERE id = ?", (videoID,))
        data = r.fetchone()
        del r
        #If not found, return 404
        if not data or not data[0]:
            return '', 404

        #Respond with subtitles
        r = flask.make_response(data[0])
        r.headers.set('Content-Type', "text/vtt")
        r.cache_control.public = True
        r.cache_control.max_age = 300
        return r
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    def _getChapters(self, videoID):
        '''
        Return chapters of a video if it has any
        '''
        #If no id supplied, return 404
        if not videoID:
            return '', 404

        #Get info from database
        r = self._db.execute("SELECT chapters FROM videos WHERE id = ?", (videoID,))
        data = r.fetchone()
        del r
        #If not found, return 404
        if not data or not data[0]:
            return '', 404

        #Covert chapters to webvtt
        chapters = data[0].splitlines()
        vtt= ["WEBVTT"]
        for i in range(len(chapters)):
            starttime, name = chapters[i].split(maxsplit=1)
            if i+1 < len(chapters):
                endtime, _ = chapters[i+1].split(maxsplit=1)
            else:
                endtime = "99:59:59.999"
            vtt.append("")
            vtt.append("{}".format(i+1))
            vtt.append("{} --> {}".format(starttime, endtime))
            vtt.append(name)


        #Return webvtt chapters
        r = flask.make_response('\n'.join(vtt))
        r.headers.set('Content-Type', "text/vtt")
        r.cache_control.public = True
        r.cache_control.max_age = 300
        return r
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    def _getError(self, error):
        '''
        Return the error page
        '''
        #Render template
        return self._getErrorPage(error.code, error.description)
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    def _getErrorPage(self, code, description):
        '''
        Return the error page
        '''
        #Render template
        return flask.render_template("error.html", error=description, base=self._baseinfo), code
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    @staticmethod
    def _manipulateImage(imgBin, imgFormat, width, height, relWidth, relHeight, cropLoc, extra):
        '''Manipulate image using PIL

        :param imgBin: The image to manipulate
        :type imgBin: binary
        :param imgFormat: The mime type of the image
        :type imgFormat: string
        :param width: The desired width of the image in pixel
        :type width: float
        :param height: The desired height of the image in pixel
        :type height: float
        :param relWidth: The desired width of the image as a factor of the height
        :type relWidth: float
        :param relHeight: The desired height of the image as a factor of the width
        :type relHeight: float
        :param cropLoc: The location to keep fixed during crop (tl, tc, tr, cl, cc, cr, bl, bc, br)
        :type cropLoc: string
        :param extra: Additional extras like "stretch"
        :type extra: string

        :returns: The manipulate image in the given mime type
        :rtype: binary
        '''
        #Get image object
        img = Image.open(io.BytesIO(imgBin))
        #Get image size
        (iWidth, iHeight) = img.size
        iRel = iWidth / iHeight
        #Get extras:
        stretch = False
        if extra:
            extra = extra.split(',')
            if "stretch" in extra:
                stretch = True
            if "circle" in extra:
                circle = True
        #Get desired size
        if width and height:
            dWidth = width
            dHeight = height
        elif width and relHeight:
            dWidth = width
            dHeight = relHeight * dWidth
        elif height and relWidth:
            dHeight = height
            dWidth = relWidth * dHeight
        elif width:
            dWidth = width
            dHeight = dWidth / iRel
        elif height:
            dHeight = height
            dWidth = dHeight * iRel
        else:
            dWidth = iWidth
            dHeight = iHeight
        #Check if desired size larger then actual
        if dWidth > iWidth or dHeight > iHeight:
            r = dWidth / dHeight
            #If not stretch, correct desired width and height
            if not stretch:
                if dWidth > iWidth:
                    dWidth = iWidth
                    dHeight = dWidth / r
                    if dHeight > iHeight:
                        dHeight = iHeight
                        dWidth = dHeight * r
                else:
                    dHeight = iHeight
                    dWidth = dHeight * r
                    if dWidth > iWidth:
                        dWidth = iWidth
                        dHeight = dWidth / r
            #If stretch, resize to the required size
            else:
                if dWidth > iWidth:
                    rWidth = dWidth
                    rHeight = rWidth / r
                    if dHeight > rHeight:
                        rHeight = dHeight
                        rWidth = rHeight * r
                else:
                    rHeight = dHeight
                    rWidth = rHeight * r
                    if dWidth > rWidth:
                        rWidth = dWidth
                        rHeight = rHeight / r
                img = img.resize(tuple(int(i) for i in (rWidth, rHeight)))
        #Check if the desired size is smaller than actual and no fixed size was given
        if dWidth < iWidth or dHeight < iHeight:
            if not (width and height):
                if iWidth > iHeight:
                    rWidth = dWidth
                    rHeight = rWidth / iRel
                    img = img.resize(tuple(int(i) for i in (rWidth, rHeight)))
                else:
                    rHeight = dHeight
                    rWidth = rHeight * iRel
                    img = img.resize(tuple(int(i) for i in (rWidth, rHeight)))
        #Get crop box
        (iWidth, iHeight) = img.size
        ch = iWidth - dWidth
        h = ch / 2
        cv = iHeight - dHeight
        v = cv / 2
        if cropLoc == "tl":
            crop = (0, 0, dWidth, dHeight)
        elif cropLoc == "tc":
            crop = (h, 0, dWidth + h, dHeight)
        elif cropLoc == "tr":
            crop = (ch, 0, dWidth + ch, dHeight)
        elif cropLoc == "cl":
            crop = (0, v, dWidth, dHeight + v)
        elif cropLoc == "cc":
            crop = (h, v, dWidth + h, dHeight + v)
        elif cropLoc == "cr":
            crop = (ch, v, dWidth + ch, dHeight + v)
        elif cropLoc == "bl":
            crop = (0, cv, dWidth, dHeight + cv)
        elif cropLoc == "bc":
            crop = (h, cv, dWidth + h, dHeight + cv)
        elif cropLoc == "br":
            crop = (ch, cv, dWidth + ch, dHeight + cv)
        else:
            crop = None
        #Crop image or scale it down
        if crop:
            img = img.crop(tuple(int(c) for c in crop))
        else:
            img = img.resize(tuple(int(i) for i in (dWidth, dHeight)))
        #Return image
        f = imgFormat.split('/')[1].upper()
        stream = io.BytesIO()
        img.save(stream, format=f)
        return stream.getvalue()
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    @staticmethod
    def _floatOrNone(var):
        '''Cast variable to float if not none

        :returns: Float value or None
        :rtype: float or None

        :raises: :class:``ValueError: Unable to cast
        '''
        if not var:
            return None
        return float(var)
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    @staticmethod
    def _timestampToHumanString(timestamp):
        '''Convert the difference between a timestamp and the current time to a
        human readable string (e.g "2 weeks" or "3 years")

        :param timestamp: The timestamp, has to be in the past
        :type timestamp: int

        :returns: Human readable time difference
        :rtype: string
        '''
        #Get times
        dt1 = int(timestamp)
        dt2 = int(time.time())
        #Get delta in minutes
        delta = abs(dt2 - dt1)
        #Get human string elements
        humanElements = []
        if delta >= 31536000: #A year
            t = delta // 31536000
            delta = delta % 31536000
            s = "years" if t > 1 else "year"
            humanElements.append("{} {}".format(t, s))
        if delta >= 2592000: #A month
            t = delta // 2592000
            delta = delta % 2592000
            s = "months" if t > 1 else "month"
            humanElements.append("{} {}".format(t, s))
        if delta >= 604800: #A week
            t = delta // 604800
            delta = delta % 604800
            s = "weeks" if t > 1 else "week"
            humanElements.append("{} {}".format(t, s))
        if delta >= 86400: #A day
            t = delta // 86400
            delta = delta % 86400
            s = "days" if t > 1 else "day"
            humanElements.append("{} {}".format(t, s))
        if delta >= 3600: #An hour
            t = delta // 3600
            delta = delta % 3600
            s = "hours" if t > 1 else "hour"
            humanElements.append("{} {}".format(t, s))
        if delta >= 60: #A minute
            t = delta // 60
            delta = delta % 60
            s = "minutes" if t > 1 else "minute"
            humanElements.append("{} {}".format(t, s))
        #Add remaining seconds
        s = "seconds" if delta > 1 else "second"
        humanElements.append("{} {}".format(delta, s))
        #Return most significant
        return humanElements[0]
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    @staticmethod
    def _timestampToLocalTimeString(timestamp):
        '''Convert a UTC timestamp to local timestring
        :param timestamp: The timestamp
        :type timestamp: int
        :returns: Local time in the format YYYY-MM-DD HH:MM:SS
        :rtype: string
        '''
        #Get datetime objects
        dt = datetime.fromtimestamp(timestamp)
        #Change timezone
        dt.replace(tzinfo=timezone.utc).astimezone(tz=None)
        #Return time string
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    @staticmethod
    def _secToTime(sec):
        '''Convert duration in seconds to MM:SS or HH:MM:SS string

        :param sec: The duration in seconds
        :type sec: int
        :returns: The duration as MM:SS or HH:MM:SS
        :rtype: string
        '''
        h = sec // 3600
        sec = sec % 3600
        m = sec // 60
        sec = sec % 60
        if h > 0:
            return "{:02d}:{:02d}:{:02d}".format(h, m, sec)
        return "{:02d}:{:02d}".format(m, sec)
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    @staticmethod
    def _intToHuman(i):
        '''Convert an integer to a human readable shortstring (e.g 1205 > 1K, 153934 > 1M)
        If None, it returns "-"

        :param i: The number
        :type i: int
        :returns: Human readable string
        :rtype: string
        '''
        if not i:
            return "-"
        if i >= 1000000000000:
            return "{:d}T".format(int(i/1000000000000))
        if i >= 1000000000:
            return "{:d}B".format(int(i/1000000000))
        if i >= 1000000:
            return "{:d}M".format(int(i/1000000))
        if i >= 1000:
            return "{:d}K".format(int(i/1000))
        return "{:d}".format(i)
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    @staticmethod
    def _intToStr(i):
        '''Convert an integer to string or return "-" if None

        :param i: The number
        :type i: int
        :returns: String representation or "-"
        :rtype: string
        '''
        if not i:
            return "-"
        return "{:n}".format(i)
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    @staticmethod
    def _qualityLabel(resolution):
        '''Takes ytarchiver's resolution string and returns text for a quality label

        :param resolution: ytarchiver's resolution string
        :type resolution: string
        :returns: text for a quality label
        :rtype: string
        '''
        if not resolution:
            return "-"
        if resolution == "Full HD":
            return "HD"
        if resolution == "4K UHD":
            return "4K"
        if resolution == "8K UHD":
            return "8K"
        return resolution
    # ########################################################################### #

# /////////////////////////////////////////////////////////////////////////// #
