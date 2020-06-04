#!/usr/bin/env python3
''' Front-end server for archivetube using flask '''

import threading
import flask
import waitress

# =========================================================================== #
class Server(threading.Thread):
    '''
    Front-end server for archivetube using flask
    '''

    # --------------------------------------------------------------------------- #
    def __init__(self, db, *args, **kw):
        '''
        Initialize the server
        '''
        #Call superclass init
        super(Server, self).__init__(*args, **kw)
        #Setup server
        self.app = flask.Flask("archivetube")
        self.db = db
        #Add routes
    # ########################################################################### #

    # --------------------------------------------------------------------------- #
    def run(self):
        '''
        Start the server
        '''
        waitress.serve(self.app)
    # ########################################################################### #


# /////////////////////////////////////////////////////////////////////////// #
