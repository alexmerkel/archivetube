#!/usr/bin/env python3
''' Front-end server for archivetube using flask '''

import io
import threading
import sqlite3
from PIL import Image
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
        r = self.db.execute("SELECT id,name,description,location,joined,links FROM channels WHERE id = ?", (channelID,))
        data = r.fetchone()
        del r
        if not data or not data["name"]:
            return '', 404
        if func == "home":
            msg = ""
            if data["description"]:
                msg += "<br><br>{}".format(data["description"].replace("\n", "<br>"))
            msg += "<br><br>Func: {}, Page: {}".format(func, page)
            return flask.render_template("channel-home.html", title=data["name"], info=data)
        else:
            return '', 404
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
        return r
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
            if not width:
                rHeight = dHeight
                rWidth = rHeight * iRel
                img = img.resize(tuple(int(i) for i in (rWidth, rHeight)))
            elif not height:
                rWidth = dWidth
                rHeight = rWidth / iRel
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

# /////////////////////////////////////////////////////////////////////////// #
