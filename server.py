#!/usr/bin/env python3
''' Front-end server for archivetube using flask '''

import os
import io
import threading
import sqlite3
import math
import mimetypes
import re
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
from pycountry import languages
from PIL import Image
import flask
import waitress


__videosPerPage__ = 25
__latestVideos__ = 4

# =========================================================================== #
class Server(threading.Thread):
    '''
    Front-end server for archivetube using flask
    '''

    # --------------------------------------------------------------------------- #
    def __init__(self, dbPath, baseinfo, *args, **kw):
        '''
        Initialize the server
        '''
        #Call superclass init
        super(Server, self).__init__(*args, **kw)
        #Define url finder from https://gist.github.com/gruber/8891611
        self.urlfinder = re.compile("(?i)\\b((?:https?:(?:\\/{1,3}|[a-z0-9%])|[a-z0-9.\\-]+[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)\\/)(?:[^\\s()<>{}\\[\\]]+|\\([^\\s()]*?\\([^\\s()]+\\)[^\\s()]*?\\)|\\([^\\s]+?\\))+(?:\\([^\\s()]*?\\([^\\s()]+\\)[^\\s()]*?\\)|\\([^\\s]+?\\)|[^\\s`!()\\[\\]{};:'\".,<>?\u00AB\u00BB\u201C\u201D\u2018\u2019])|(?:(?<!@)[a-z0-9]+(?:[.\\-][a-z0-9]+)*[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)\\b\\/?(?!@)))")
        #Setup database
        self.db = sqlite3.connect(dbPath, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        #Base info dict
        self.baseinfo = baseinfo
        r = self.db.execute("SELECT id,name FROM channels ORDER BY name COLLATE NOCASE ASC")
        data = r.fetchall()
        del r
        channels = []
        for c in data:
            if c and c["name"]:
                channels.append(dict(c))
        self.baseinfo["channels"] = channels
        #Setup server
        self.app = flask.Flask("archivetube")
        #Add routes
        self.app.add_url_rule("/", "home", self.getHome)
        self.app.add_url_rule("/watch", "watch", self.getWatch)
        self.app.add_url_rule("/channel/<channelID>/", "channel", self.getChannel, defaults={"func": "home", "page": None})
        self.app.add_url_rule("/channel/<channelID>/<func>/", "channel-func", self.getChannel, defaults={"page": None})
        self.app.add_url_rule("/channel/<channelID>/<func>/page/<int:page>/", "channel-page", self.getChannel)
        self.app.add_url_rule("/res/thumb/<videoID>", "thumb", self.getThumbnail)
        self.app.add_url_rule("/res/video/<videoID>", "video", self.getVideo)
        self.app.add_url_rule("/res/subtitles/<videoID>", "subtitles", self.getSubtitles)
        self.app.add_url_rule("/res/profile/<channelID>", "profile", self.getProfile)
        self.app.add_url_rule("/res/banner/<channelID>", "banner", self.getBanner)
        #Add error handlers
        self.app.register_error_handler(403, self.getError)
        self.app.register_error_handler(404, self.getError)
        self.app.register_error_handler(410, self.getError)
        self.app.register_error_handler(500, self.getError)
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    def run(self):
        '''
        Start the server
        '''
        waitress.serve(self.app, threads=6)
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    def getHome(self):
        '''
        Return the landing page
        '''
        #Get channel info from database
        r = self.db.execute("SELECT id,name,videos,lastupdate FROM channels ORDER BY name COLLATE NOCASE ASC")
        data = r.fetchall()
        del r
        channels = []
        for c in data:
            if c and c["name"]:
                c = dict(c)
                c["agostring"] = self.timestampToHumanString(c["lastupdate"])
                c["lastupdate"] = self.timestampToLocalTimeString(c["lastupdate"])
                channels.append(c)
        if not channels:
            return self.getErrorPage(404, "No channel data in database")
        #Render template
        return flask.render_template("home.html", channels=channels, base=self.baseinfo)
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

        #Get video info from database
        r = self.db.execute("SELECT id,channelID,title,timestamp,description,subtitles,filepath,tags FROM videos WHERE id = ?", (videoID,))
        video = r.fetchone()
        del r
        if not video:
            return self.getErrorPage(404, "Video not found")
        video = dict(video)
        #Get channel from database
        r = self.db.execute("SELECT id,name,language,videos,lastupdate FROM channels WHERE id = ?", (video["channelID"],))
        channel = r.fetchone()
        del r
        if not channel:
            return self.getErrorPage(404, "Video channel not found")
        channel = dict(channel)
        #Convert timestamp
        channel["lastupdate"] = self.timestampToHumanString(channel["lastupdate"])
        #Get channel language code and name
        if video["subtitles"]:
            if channel["language"]:
                lang = languages.get(alpha_2=channel["language"])
                channel["language"] = lang.name
                channel["lang"] = lang.alpha_2
            else:
                video["subtitles"] = False
        #Get next video info from database
        r = self.db.execute("SELECT id,title,timestamp,duration FROM videos WHERE channelID = ? AND timestamp > ? ORDER BY timestamp ASC LIMIT 1;", (channel["id"], video["timestamp"]))
        nextVideo = r.fetchone()
        del r
        if nextVideo:
            nextVideo = dict(nextVideo)
            #Convert timestamp
            nextVideo["duration"] = self.secToTime(nextVideo["duration"])
            nextVideo["agestring"] = self.timestampToHumanString(nextVideo["timestamp"])
            nextVideo["timestamp"] = self.timestampToLocalTimeString(nextVideo["timestamp"])
        else:
            nextVideo = None
        #Get previous video info from database
        r = self.db.execute("SELECT id,title,timestamp,duration FROM videos WHERE channelID = ? AND timestamp < ? ORDER BY timestamp DESC LIMIT 1;", (channel["id"], video["timestamp"]))
        previousVideo = r.fetchone()
        del r
        if previousVideo:
            previousVideo = dict(previousVideo)
            #Convert timestamp
            previousVideo["duration"] = self.secToTime(previousVideo["duration"])
            previousVideo["agestring"] = self.timestampToHumanString(previousVideo["timestamp"])
            previousVideo["timestamp"] = self.timestampToLocalTimeString(previousVideo["timestamp"])
        else:
            previousVideo = None
        #Get latest video info from database
        r = self.db.execute("SELECT id,title,timestamp,duration FROM videos WHERE channelID = ? ORDER BY timestamp DESC LIMIT 1", (channel["id"],))
        latestVideo = r.fetchone()
        del r
        if latestVideo:
            latestVideo = dict(latestVideo)
            #Convert timestamp
            latestVideo["duration"] = self.secToTime(latestVideo["duration"])
            latestVideo["agestring"] = self.timestampToHumanString(latestVideo["timestamp"])
            latestVideo["timestamp"] = self.timestampToLocalTimeString(latestVideo["timestamp"])
            #Only show latest video if this or the next video is not the latest
            if latestVideo["id"] == video["id"] or latestVideo["id"] == nextVideo["id"]:
                latestVideo = None
        else:
            latestVideo = None
        #Only interested if subtitles exist or not
        video["subtitles"] = bool(video["subtitles"])
        #Convert timestamp
        video["agestring"] = self.timestampToHumanString(video["timestamp"])
        video["timestamp"] = self.timestampToLocalTimeString(video["timestamp"])
        #Get mime type
        video["mimetype"] = mimetypes.guess_type(video["filepath"])[0]
        #Convert links in description
        video["description"] = self.urlfinder.sub(r'<a href="\1">\1</a>', video["description"])
        #Render template
        return flask.render_template("watch.html", title=video["title"], video=video, nextVideo=nextVideo, previousVideo=previousVideo, latestVideo=latestVideo, channel=channel, base=self.baseinfo)
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    def getChannel(self, channelID, func, page):
        '''
        Return the channel page
        '''
        #If no id supplied, return 404
        if not channelID:
            return self.getErrorPage(404, "No channel ID specified")

        #Get info from database
        r = self.db.execute("SELECT id,name,description,location,joined,links,videos,lastupdate FROM channels WHERE id = ?", (channelID,))
        data = r.fetchone()
        del r
        if not data or not data["name"]:
            return self.getErrorPage(404, "Unable to find channel")
        data = dict(data)
        # Get channel home
        if func == "home":
            #Get 4 latest videos
            cmd = "SELECT id,title,timestamp,duration FROM videos WHERE channelID = ? ORDER BY timestamp DESC LIMIT {}".format(__latestVideos__)
            r = self.db.execute(cmd, (channelID,))
            videos = [dict(v) for v in r.fetchall()]
            del r
            #Convert timestamp and duration
            for v in videos:
                v["duration"] = self.secToTime(v["duration"])
                v["agestring"] = self.timestampToHumanString(v["timestamp"])
                v["timestamp"] = self.timestampToLocalTimeString(v["timestamp"])
            data["lastupdate"] = self.timestampToHumanString(data["lastupdate"])
            #Convert links in description
            data["description"] = self.urlfinder.sub(r'<a href="\1">\1</a>', data["description"])
            #Render template
            return flask.render_template("channel-home.html", title=data["name"], info=data, videos=videos, base=self.baseinfo)
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
            sorting = flask.request.args.get("s", "new")
            if sorting == "old":
                sorting = "ASC"
            else:
                sorting = "DESC"
            #Query database
            cmd = "SELECT id,title,timestamp,duration FROM videos WHERE channelID = ? ORDER BY timestamp {} LIMIT {} OFFSET {}".format(sorting, __videosPerPage__, (page - 1)*__videosPerPage__)
            r = self.db.execute(cmd, (channelID,))
            videos = [dict(v) for v in r.fetchall()]
            del r
            #Convert timestamp and duration
            for v in videos:
                v["duration"] = self.secToTime(v["duration"])
                v["agestring"] = self.timestampToHumanString(v["timestamp"])
                v["timestamp"] = self.timestampToLocalTimeString(v["timestamp"])
            #Render template
            return flask.render_template("channel-videos.html", title=data["name"] + " - Videos", info=data, videos=videos, base=self.baseinfo)
        #Get channel info
        if func == "info":
            #Convert timestamp
            data["lastupdate"] = self.timestampToLocalTimeString(data["lastupdate"])
            #Convert links
            links = []
            if data["links"]:
                for l in data["links"].splitlines():
                    l = l.split('\t')
                    links.append({"pretty": l[0], "url": l[1]})
                data["links"] = links
            #Convert links in description
            data["description"] = self.urlfinder.sub(r'<a href="\1">\1</a>', data["description"])
            #Render template
            return flask.render_template("channel-info.html", title=data["name"] + " - Info", info=data, base=self.baseinfo)
        #Unknown func, redirect to channel home
        return flask.redirect(flask.url_for("channel", channelID=channelID))
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
        #Try getting resize parameters
        if flask.request.args:
            try:
                width = self.floatOrNone(flask.request.args.get("w"))
                height = self.floatOrNone(flask.request.args.get("h"))
                relWidth = self.floatOrNone(flask.request.args.get("rw"))
                relHeight = self.floatOrNone(flask.request.args.get("rh"))
                cropLoc = flask.request.args.get("c")
                extra = flask.request.args.get("e")
                img = self.manipulateImage(data["thumb"], data["thumbformat"], width, height, relWidth, relHeight, cropLoc, extra)
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
        #Try getting resize parameters
        if flask.request.args:
            try:
                width = self.floatOrNone(flask.request.args.get("w"))
                height = self.floatOrNone(flask.request.args.get("h"))
                relWidth = self.floatOrNone(flask.request.args.get("rw"))
                relHeight = self.floatOrNone(flask.request.args.get("rh"))
                cropLoc = flask.request.args.get("c")
                extra = flask.request.args.get("e")
                img = self.manipulateImage(data["profile"], data["profileformat"], width, height, relWidth, relHeight, cropLoc, extra)
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

        #Try getting resize parameters
        if flask.request.args:
            try:
                width = self.floatOrNone(flask.request.args.get("w"))
                height = self.floatOrNone(flask.request.args.get("h"))
                relWidth = self.floatOrNone(flask.request.args.get("rw"))
                relHeight = self.floatOrNone(flask.request.args.get("rh"))
                cropLoc = flask.request.args.get("c")
                extra = flask.request.args.get("e")
                img = self.manipulateImage(data["banner"], data["bannerformat"], width, height, relWidth, relHeight, cropLoc, extra)
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
    def getVideo(self, videoID):
        '''
        Return a video file
        '''
        #If no id supplied, return 404
        if not videoID:
            return '', 404

        #Get info from database
        r = self.db.execute("SELECT filepath FROM videos WHERE id = ?", (videoID,))
        data = r.fetchone()
        del r
        #If not found, return 404
        if not data or not data[0]:
            return '', 404

        #Respond with video
        return flask.send_from_directory(os.path.dirname(data[0]), os.path.basename(data[0]))
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    def getSubtitles(self, videoID):
        '''
        Return subtitles of a video of they have any
        '''
        #If no id supplied, return 404
        if not videoID:
            return '', 404


        #Get info from database
        r = self.db.execute("SELECT subtitles FROM videos WHERE id = ?", (videoID,))
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
    def getError(self, error):
        '''
        Return the error page
        '''
        #Render template
        return self.getErrorPage(error.code, error.description)
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    def getErrorPage(self, code, description):
        '''
        Return the error page
        '''
        #Render template
        return flask.render_template("error.html", error=description, base=self.baseinfo), code
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    @staticmethod
    def manipulateImage(imgBin, imgFormat, width, height, relWidth, relHeight, cropLoc, extra):
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
    def floatOrNone(var):
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
    def timestampToHumanString(timestamp):
        '''Convert the difference between a timestamp and the current time to a
        human readable string (e.g "2 weeks" or "3 years")

        :param timestamp: The timestamp, has to be in the past
        :type timestamp: int

        :returns: Human readable time difference
        :rtype: string
        '''
        #Get datetime objects
        dt1 = datetime.fromtimestamp(timestamp)
        dt2 = datetime.utcnow()
        #Deffine Lambda
        attrs = ['years', 'months', 'days', 'hours', 'minutes']
        humanConverter = lambda delta: ['%d %s' % (getattr(delta, attr), getattr(delta, attr) > 1 and attr or attr[:-1]) for attr in attrs if getattr(delta, attr)]
        #Get human string elements
        humanElements = humanConverter(relativedelta(dt2, dt1))
        #Return most significant
        return humanElements[0]
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    @staticmethod
    def timestampToLocalTimeString(timestamp):
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
    def secToTime(sec):
        '''Convert duration in seconds to MM:SS or HH:MM:SS string

        :param sec: The duration in seconds
        :type args: int
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

# /////////////////////////////////////////////////////////////////////////// #
