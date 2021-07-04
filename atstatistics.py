#!/usr/bin/env python3
''' atstatistics - statistics for archived videos '''

import os
import io
import sys
import sqlite3
import argparse
import time
from datetime import datetime, timezone
from scipy.signal import savgol_filter as sf
import matplotlib.pyplot as plt
import matplotlib.dates as md
import atcommon as atc

__startMidweek__ = 1108641600 #Timestamp middle of the week (thursday noon) of the founding week of Youtube (Feb 14 2005)

# --------------------------------------------------------------------------- #
def main(args):
    '''The main atstatistics function

    :param args: The command line arguments given by the user
    :type args: list
    '''
    parser = argparse.ArgumentParser(prog="atstatistics", description="Calculate statistics for archived videos")
    parser.add_argument("-m", "--memory", action="store_const", dest="memory", const=True, default=False, help="Keep whole database in memory (faster, but requires a lot of memory)")
    parser.add_argument("-v", "--verbose", action="store_const", dest="verbose", const=True, default=False, help="Print more status info")
    parser.add_argument("-V", "--version", action="version", version='%(prog)s {}'.format(atc.__version__))
    parser.add_argument("DIR", help="The directory to work in")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-c", "--calculate", action="store_const", dest="calculate", const=True, default=False, help="Calculate only, don't plot")
    group.add_argument("-p", "--plot", action="store_const", dest="plot", const=True, default=False, help="Plot only, don't calculate")

    args = parser.parse_args()

    #Validate path
    path = os.path.normpath(os.path.abspath(args.DIR))
    if not os.path.isdir(path):
        parser.error("An existing directory must be specified")

    #Check tasks
    taskCalc = True
    taskPlot = True
    if args.calculate:
        taskPlot = False
    if args.plot:
        taskCalc = False

    if args.memory:
        print("Using in-memory database")

    #Check if database exists
    dbPath = os.path.join(path, "tube.db")
    try:
        if os.path.isfile(dbPath):
            #Connect to database
            t1 = time.perf_counter()
            if args.memory:
                print("Reading existing database")
                fileDBCon = atc.connectDB(dbPath)
                dbCon = sqlite3.connect(":memory:")
                fileDBCon.backup(dbCon)
                fileDBCon.close()
            else:
                print("Connect to existing database")
                dbCon = atc.connectDB(dbPath)
            t2 = time.perf_counter()
            t = t2 - t1
            if args.verbose:
                print("Read time: {:0.4f} seconds".format(t))
            dbCon.row_factory = sqlite3.Row
            db = dbCon.cursor()
        else:
            sys.exit("ERROR: No database found")
    except sqlite3.Error as e:
        sys.exit("ERROR: Database error \"{}\"".format(e))

    errorMsg = ""
    try:
        run(db, taskCalc, taskPlot, args.verbose)
        dbCon.commit()
    except StatisticsError as e:
        errorMsg = "ERROR: " + str(e)


    #Write changes to database
    if args.memory:
        if errorMsg:
            print("Error occurred, writing database before exiting")
        else:
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

    if errorMsg:
        sys.exit(errorMsg)
    else:
        print("DONE")
# ########################################################################### #

# --------------------------------------------------------------------------- #
def run(db, runCalc=True, runPlot=True, verbose=False):
    '''The main atstatistics function

    :param db: Connection to the tube database
    :type db: sqlite3.Cursor
    :param runCalc: Whether to perform the calculation (Default: True)
    :type runCalc: boolean, optional
    :param runPlot: Whether to plot the data (Default: True)
    :type runPlot: boolean, optional
    :param verbose: Whether to print more status messages (Default: False)
    :type verbose: boolean, optional

    :raises: :class:``StatisticsError: An error occurred
    '''
    if runCalc:
        t1 = time.perf_counter()
        calculate(db, verbose)
        t2 = time.perf_counter()
        t = t2 - t1
        if verbose:
            print("Calculation time: {:0.4f} seconds".format(t))
    if runPlot:
        t1 = time.perf_counter()
        plot(db, verbose)
        t2 = time.perf_counter()
        t = t2 - t1
        if verbose:
            print("Plot time: {:0.4f} seconds".format(t))
# ########################################################################### #

# --------------------------------------------------------------------------- #
def calculate(db, verbose=False, veryverbose=False):
    '''Calculate statistics for archived videos

    :param db: Connection to the tube database
    :type db: sqlite3.Cursor
    :param verbose: Whether to print more status messages (Default: False)
    :type verbose: boolean, optional
    :param veryverbose: Whether to print even more status messages (Default: False)
    :type veryverbose: boolean, optional

    :raises: :class:``StatisticsError: An error occurred during the calculation
    '''
    #Setup
    week = 604800
    halfweek = 302400
    currentTime = int(time.time())
    verbose = True if veryverbose else verbose

    #Print status
    if verbose:
        print("Calculating statistics")

    #Get oldest video
    try:
        r = db.execute("SELECT timestamp FROM videos ORDER BY timestamp ASC LIMIT 1;")
        oldest = r.fetchone()["timestamp"]
        del r
    except (sqlite3.Error, AttributeError, IndexError) as e:
        raise StatisticsError("Unable to get oldest video (Error: \"{}\")".format(e)) from e

    #Clear weekly statistics table
    db.execute("DELETE FROM statsWeekly")

    #Initialize
    totalVideos = 0
    totalVideos8k = 0
    totalVideos4k = 0
    totalVideosFullHD = 0
    totalVideosHD = 0
    totalVideosSD = 0
    totalVideosLD = 0
    totalSubtitles = 0
    totalChapters = 0
    totalTotalDuration = 0

    #Loop through all weeks
    for midweek in range(__startMidweek__, currentTime-halfweek, week):
        #Setup
        start = midweek - halfweek
        end = midweek + halfweek - 1
        #If earlier than oldest video, skip
        if end < oldest:
            continue
        #Convert dates
        dtMidweek = datetime.fromtimestamp(midweek, tz=timezone.utc)
        year = int(datetime.strftime(dtMidweek, "%Y"))
        week = int(datetime.strftime(dtMidweek, "%V"))
        monday = datetime.strftime(datetime.fromtimestamp(start, tz=timezone.utc), "%Y-%m-%d")
        sunday = datetime.strftime(datetime.fromtimestamp(end, tz=timezone.utc), "%Y-%m-%d")
        weekid = int(datetime.strftime(dtMidweek, "%Y%V"))

        #Get videos in weeks
        try:
            r = db.execute("SELECT width,height,duration,subtitles,chapters FROM videos WHERE timestamp BETWEEN ? AND ?;", (start, end))
            vids = r.fetchall()
            del r
        except (sqlite3.Error, TypeError) as e:
            raise StatisticsError("Database error reading data in week {}-{} (Error: \"{}\")".format(year, week, e)) from e

        if not vids:
            if veryverbose:
                print("No videos in week {}-{}".format(year, week))
            continue

        if veryverbose:
            print("{} videos in week {}-{}".format(len(vids), year, week))

        #Initialize
        videos = len(vids)
        videos8k = 0
        videos4k = 0
        videosFullHD = 0
        videosHD = 0
        videosSD = 0
        videosLD = 0
        subtitles = 0
        chapters = 0
        totalDuration = 0

        #Loop through videos
        for video in vids:
            #Get video resolution
            larger = video["width"] if video["width"] > video["height"] else video["height"]
            smaller = video["height"] if video["width"] > video["height"] else video["width"]
            if larger < 1200:
                if larger < 700 and smaller < 400:
                    #LD video
                    videosLD += 1
                else:
                    #SD video
                    videosSD += 1
            elif 1200 <= larger < 1900:
                #HD video
                videosHD += 1
            elif 1900 <= larger < 3500:
                #Full HD video
                videosFullHD += 1
            elif 3500 <= larger < 6000:
                #4K video
                videos4k += 1
            else:
                #8K video
                videos8k += 1

            #Get video duration
            if video["duration"]:
                totalDuration += video["duration"]

            #Get subtitles
            if video["subtitles"]:
                subtitles += 1

            #Get chapters
            if video["chapters"]:
                chapters += 1

        #Calculate fractions
        fraction8k = videos8k/videos
        fraction4k = videos4k/videos
        fractionFullHD = videosFullHD/videos
        fractionHD = videosHD/videos
        fractionSD = videosSD/videos
        fractionLD = videosLD/videos
        fractionSub = subtitles/videos
        fractionChap = chapters/videos
        avgDuration = totalDuration/videos

        #Write data
        try:
            cmd = "INSERT INTO statsWeekly(id,timestamp,year,week,mondaydate,sundaydate,videos,v8k,fraction8k,v4k,fraction4k,vFullHD,fractionFullHD,vHD,fractionHD,vSD,fractionSD,vLD,fractionLD,subtitles,fractionSubtitles,chapters,fractionChapters,totalDuration,avgDuration) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            db.execute(cmd, (weekid, midweek, year, week, monday, sunday, videos, videos8k, fraction8k, videos4k, fraction4k, videosFullHD, fractionFullHD, videosHD, fractionHD, videosSD, fractionSD, videosLD, fractionLD, subtitles, fractionSub, chapters, fractionChap, totalDuration, avgDuration))
        except sqlite3.Error:
            try:
                cmd = "UPDATE statsWeekly SET timestamp=?,year=?,week=?,mondaydate=?,sundaydate=?,videos=?,v8k=?,fraction8k=?,v4k=?,fraction4k=?,vFullHD=?,fractionFullHD=?,vHD=?,fractionHD=?,vSD=?,fractionSD=?,vLD=?,fractionLD=?,subtitles=?,fractionSubtitles=?,chapters=?,fractionChapters=?,totalDuration=?,avgDuration=? WHERE id=?"
                db.execute(cmd, (midweek, year, week, monday, sunday, videos, videos8k, fraction8k, videos4k, fraction4k, videosFullHD, fractionFullHD, videosHD, fractionHD, videosSD, fractionSD, videosLD, fractionLD, subtitles, fractionSub, chapters, fractionChap, totalDuration, avgDuration, weekid))
            except sqlite3.Error as e:
                raise StatisticsError("Database error writing data in week {}-{} (Error: \"{}\")".format(year, week, e)) from e

        #Update total statistics
        totalVideos += videos
        totalVideos8k += videos8k
        totalVideos4k += videos4k
        totalVideosFullHD += videosFullHD
        totalVideosHD += videosHD
        totalVideosSD += videosSD
        totalVideosLD += videosLD
        totalSubtitles += subtitles
        totalChapters += chapters
        totalTotalDuration += totalDuration

    if verbose:
        print("Writing overall statistic")

    #Calculate fractions
    totalFraction8k = totalVideos8k/totalVideos
    totalFraction4k = totalVideos4k/totalVideos
    totalFractionFullHD = totalVideosFullHD/totalVideos
    totalFractionHD = totalVideosHD/totalVideos
    totalFractionSD = totalVideosSD/totalVideos
    totalFractionLD = totalVideosLD/totalVideos
    totalFractionSub = totalSubtitles/totalVideos
    totalFractionChap = totalChapters/totalVideos
    totalAvgDuration = totalTotalDuration/totalVideos

    #Write data
    try:
        cmd = "INSERT INTO statsOverall(timestamp,videos,v8k,fraction8k,v4k,fraction4k,vFullHD,fractionFullHD,vHD,fractionHD,vSD,fractionSD,vLD,fractionLD,subtitles,fractionSubtitles,chapters,fractionChapters,totalDuration,avgDuration) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
        db.execute(cmd, (currentTime, totalVideos, totalVideos8k, totalFraction8k, totalVideos4k, totalFraction4k, totalVideosFullHD, totalFractionFullHD, totalVideosHD, totalFractionHD, totalVideosSD, totalFractionSD, totalVideosLD, totalFractionLD, totalSubtitles, totalFractionSub, totalChapters, totalFractionChap, totalTotalDuration, totalAvgDuration))
    except sqlite3.Error as e:
        raise StatisticsError("Database error writing overall data (Error: \"{}\")".format(e)) from e

    #Write status
    try:
        db.execute("UPDATE info SET statisticsupdated=?  WHERE id = 1", (currentTime,))
    except sqlite3.Error as e:
        raise StatisticsError("Database error writing status (Error: \"{}\")".format(e)) from e
# ########################################################################### #

# --------------------------------------------------------------------------- #
def plot(db, verbose=False):
    '''Create plots from statistics

    :param db: Connection to the tube database
    :type db: sqlite3.Cursor
    :param verbose: Whether to print more status messages (Default: False)
    :type verbose: boolean, optional

    :raises: :class:``StatisticsError: An error occurred during plotting
    '''
    #Print status
    if verbose:
        print("Plotting statistics")

    #Get data
    try:
        r = db.execute("SELECT timestamp,videos,fraction8k,fraction4k,fractionFullHD,fractionHD,fractionSD,fractionLD,fractionSubtitles,fractionChapters,avgDuration FROM statsWeekly")
        weeks = r.fetchall()
        del r
    except (sqlite3.Error, AttributeError) as e:
        raise StatisticsError("Database error reading data for plotting (Error: \"{}\")".format(e)) from e

    #Parse data
    dt = []
    videos = []
    fraction8k = []
    fraction4k = []
    fractionFullHD = []
    fractionHD = []
    fractionSD = []
    fractionLD = []
    fractionSub = []
    fractionChap = []
    avgDuration = []
    for week in weeks:
        dt.append(datetime.fromtimestamp(week["timestamp"]))
        videos.append(week["videos"])
        fraction8k.append(week["fraction8k"]*100)
        fraction4k.append(week["fraction4k"]*100)
        fractionFullHD.append(week["fractionFullHD"]*100)
        fractionHD.append(week["fractionHD"]*100)
        fractionSD.append(week["fractionSD"]*100)
        fractionLD.append(week["fractionLD"]*100)
        fractionSub.append(week["fractionSubtitles"]*100)
        fractionChap.append(week["fractionChapters"]*100)
        avgDuration.append(week["avgDuration"]/60)
    dt = md.date2num(dt)
    #Smooth data
    windowLength = 13
    polynomial = 3
    fraction8k = sf(fraction8k, windowLength, polynomial)
    fraction4k = sf(fraction4k, windowLength, polynomial)
    fractionFullHD = sf(fractionFullHD, windowLength, polynomial)
    fractionHD = sf(fractionHD, windowLength, polynomial)
    fractionSD = sf(fractionSD, windowLength, polynomial)
    fractionLD = sf(fractionLD, windowLength, polynomial)
    fractionSub = sf(fractionSub, windowLength, polynomial)
    fractionChap = sf(fractionChap, windowLength, polynomial)

    #General settings
    plt.rcParams.update({'font.size': 7})
    colorLight = "#0b0c0d"
    colorDark = "#eef0f1"
    color1 = "#37702e"
    color2 = "#78994b"
    color3 = "#bac36e"
    color4 = "#f8b768"
    color5 = "#ec7d52"
    color6 = "#d43d51"
    plt.rc("grid", linestyle="--", color="#8f8f8f", alpha=0.5)
    plt.rc("axes", edgecolor=colorLight)
    linewidth = 1.3
    figWidth = 12.45
    figHeight = 5.8
    figDPI = 300
    figRect = (0, 0, 1, 0.95)
    titleY = 0.98
    legendLoc = (0.5, 0.95)

    #Resolution plot
    if verbose:
        print("Plotting resolution over time")
    #Setup plot
    fig, ax = plt.subplots()
    fig.set_size_inches(figWidth, figHeight)
    t = fig.suptitle('Video image resolution over time', y=titleY)
    ax.set_ylabel('Fraction of weekly videos [%]')
    ax.set_xlabel('Time')
    xfmt = md.DateFormatter('%Y')
    ax.xaxis.set_major_formatter(xfmt)
    ax.xaxis.set_major_locator(md.YearLocator())
    ax.xaxis.set_minor_locator(md.MonthLocator())
    ax.set_ylim(ymin=0, ymax=105)
    ax.set_xlim(dt[0], dt[-1])
    #Add data
    if max(fraction8k) > 0:
        ax.plot_date(dt, fraction8k, '-', label="8K", linewidth=linewidth, color=color1)
    if max(fraction4k) > 0:
        ax.plot_date(dt, fraction4k, '-', label="4K", linewidth=linewidth, color=color2)
    if max(fractionFullHD) > 0:
        ax.plot_date(dt, fractionFullHD, '-', label="FullHD", linewidth=linewidth, color=color3)
    if max(fractionHD) > 0:
        ax.plot_date(dt, fractionHD, '-', label="HD", linewidth=linewidth, color=color4)
    if max(fractionSD) > 0:
        ax.plot_date(dt, fractionSD, '-', label="SD", linewidth=linewidth, color=color5)
    if max(fractionLD) > 0:
        ax.plot_date(dt, fractionLD, '-', label="LD", linewidth=linewidth, color=color6)
    #Setup
    l = fig.legend(loc='upper center', bbox_to_anchor=legendLoc, ncol=6, edgecolor=colorLight)
    l.get_frame().set_alpha(None)
    l.get_frame().set_facecolor((0, 0, 0, 0))
    for text in l.get_texts():
        text.set_color(colorLight)
    ax.tick_params(which="both", colors=colorLight, labelcolor=colorLight)
    for spine in ax.spines.values():
        spine.set_edgecolor(colorLight)
    ax.xaxis.label.set_color(colorLight)
    ax.yaxis.label.set_color(colorLight)
    t.set_color(colorLight)
    ax.grid(True)
    fig.tight_layout(rect=figRect)
    png = io.BytesIO()
    svgLight = io.BytesIO()
    svgDark = io.BytesIO()
    #Generate png
    plt.savefig(png, format="png", dpi=figDPI)
    #Generate light svg
    plt.savefig(svgLight, format="svg", dpi=figDPI, transparent=True)
    #Generate dark svg
    ax.tick_params(which="both", colors=colorDark, labelcolor=colorDark)
    for spine in ax.spines.values():
        spine.set_edgecolor(colorDark)
    ax.xaxis.label.set_color(colorDark)
    ax.yaxis.label.set_color(colorDark)
    t.set_color(colorDark)
    l.get_frame().set_edgecolor(colorDark)
    for text in l.get_texts():
        text.set_color(colorDark)
    plt.savefig(svgDark, format="svg", dpi=figDPI, transparent=True)
    #Write to database
    updateOrInsertPlot(db, "resolutions", png, svgLight, svgDark)

    #Features plot
    if verbose:
        print("Plotting features over time")
    #Setup plot
    fig, ax = plt.subplots()
    fig.set_size_inches(figWidth, figHeight)
    t = fig.suptitle('Video features over time', y=titleY)
    ax.set_ylabel('Fraction of weekly videos [%]')
    ax.set_xlabel('Time')
    xfmt = md.DateFormatter('%Y')
    ax.xaxis.set_major_formatter(xfmt)
    ax.xaxis.set_major_locator(md.YearLocator())
    ax.xaxis.set_minor_locator(md.MonthLocator())
    ax.set_ylim(ymin=0, ymax=105)
    ax.set_xlim(dt[0], dt[-1])
    #Add data
    ax.plot_date(dt, fractionSub, '-', label="Subtitles", linewidth=linewidth, color=color1)
    ax.plot_date(dt, fractionChap, '-', label="Chapters", linewidth=linewidth, color=color6)
    #Setup
    l = fig.legend(loc='upper center', bbox_to_anchor=legendLoc, ncol=6, edgecolor=colorLight)
    l.get_frame().set_alpha(None)
    l.get_frame().set_facecolor((0, 0, 0, 0))
    for text in l.get_texts():
        text.set_color(colorLight)
    ax.tick_params(which="both", colors=colorLight, labelcolor=colorLight)
    for spine in ax.spines.values():
        spine.set_edgecolor(colorLight)
    ax.xaxis.label.set_color(colorLight)
    ax.yaxis.label.set_color(colorLight)
    t.set_color(colorLight)
    ax.grid(True)
    fig.tight_layout(rect=figRect)
    png = io.BytesIO()
    svgLight = io.BytesIO()
    svgDark = io.BytesIO()
    #Generate png
    plt.savefig(png, format="png", dpi=figDPI)
    #Generate light svg
    plt.savefig(svgLight, format="svg", dpi=figDPI, transparent=True)
    #Generate dark svg
    ax.tick_params(which="both", colors=colorDark, labelcolor=colorDark)
    for spine in ax.spines.values():
        spine.set_edgecolor(colorDark)
    ax.xaxis.label.set_color(colorDark)
    ax.yaxis.label.set_color(colorDark)
    t.set_color(colorDark)
    l.get_frame().set_edgecolor(colorDark)
    for text in l.get_texts():
        text.set_color(colorDark)
    plt.savefig(svgDark, format="svg", dpi=figDPI, transparent=True)
    #Write to database
    updateOrInsertPlot(db, "features", png, svgLight, svgDark)

    #Content plot
    if verbose:
        print("Plotting content over time")
    #Setup plot
    fig, ax1 = plt.subplots()
    fig.set_size_inches(figWidth, figHeight)
    t = fig.suptitle('Weekly videos and video length over time', y=titleY)
    ax1.set_ylabel('Average weekly videos length [min]')
    ax1.set_xlabel('Time')
    ax2 = ax1.twinx()
    ax2.set_ylabel('Number of weekly videos')
    xfmt = md.DateFormatter('%Y')
    ax1.xaxis.set_major_formatter(xfmt)
    ax1.xaxis.set_major_locator(md.YearLocator())
    ax1.xaxis.set_minor_locator(md.MonthLocator())
    ax1.set_xlim(dt[0], dt[-1])
    ax1.set_ylim(0, max(avgDuration)*1.05)
    ax2.set_ylim(0, max(videos)*1.05)
    #Add data
    ax1.plot_date(dt, avgDuration, '-', label="Avg. duration", linewidth=linewidth, color=color6)
    ax2.bar(dt, videos, width=5, alpha=0.7, label="Weekly videos", color=color1)
    #Setup
    l = fig.legend(loc='upper center', bbox_to_anchor=legendLoc, ncol=6, edgecolor=colorLight)
    l.get_frame().set_alpha(None)
    l.get_frame().set_facecolor((0, 0, 0, 0))
    for text in l.get_texts():
        text.set_color(colorLight)
    ax1.tick_params(which="both", colors=colorLight, labelcolor=colorLight)
    ax2.tick_params(which="both", colors=colorLight, labelcolor=colorLight)
    for spine in ax1.spines.values():
        spine.set_edgecolor(colorLight)
    for spine in ax2.spines.values():
        spine.set_edgecolor(colorLight)
    ax1.xaxis.label.set_color(colorLight)
    ax1.yaxis.label.set_color(colorLight)
    ax2.yaxis.label.set_color(colorLight)
    t.set_color(colorLight)
    ax1.set_zorder(ax2.get_zorder()+1)
    ax1.grid(True)
    ax1.patch.set_visible(False)
    fig.tight_layout(rect=figRect)
    png = io.BytesIO()
    svgLight = io.BytesIO()
    svgDark = io.BytesIO()
    #Generate png
    plt.savefig(png, format="png", dpi=figDPI)
    #Generate light svg
    plt.savefig(svgLight, format="svg", dpi=figDPI, transparent=True)
    #Generate dark svg
    ax1.tick_params(which="both", colors=colorDark, labelcolor=colorDark)
    ax2.tick_params(which="both", colors=colorDark, labelcolor=colorDark)
    for spine in ax1.spines.values():
        spine.set_edgecolor(colorDark)
    for spine in ax2.spines.values():
        spine.set_edgecolor(colorDark)
    ax1.xaxis.label.set_color(colorDark)
    ax1.yaxis.label.set_color(colorDark)
    ax2.yaxis.label.set_color(colorDark)
    t.set_color(colorDark)
    l.get_frame().set_edgecolor(colorDark)
    for text in l.get_texts():
        text.set_color(colorDark)
    plt.savefig(svgDark, format="svg", dpi=figDPI, transparent=True)
    #Write to database
    updateOrInsertPlot(db, "content", png, svgLight, svgDark)
# ########################################################################### #

# --------------------------------------------------------------------------- #
def updateOrInsertPlot(db, name, png, svgLight, svgDark):
    '''Update or insert a plot into the database

    :param db: Connection to the tube database
    :type db: sqlite3.Cursor
    :param name: The name of the plot
    :type name: string
    :param png: The png data
    :type png: binary
    :param svgLight: The svg data for a light color scheme
    :type svgLight: binary
    :param svgDark: The svg data for a dark color scheme
    :type svgDark: binary

    :raises: :class:``StatisticsError: An error occurred during the process
    '''
    timestamp = int(time.time())
    try:
        png.seek(0)
        svgLight.seek(0)
        svgDark.seek(0)
        db.execute("INSERT INTO statsPlots(name,timestamp,png,svgLight,svgDark) VALUES(?,?,?,?,?)", (name,timestamp,png.read(),svgLight.read(),svgDark.read()))
    except sqlite3.Error:
        try:
            png.seek(0)
            svgLight.seek(0)
            svgDark.seek(0)
            db.execute("UPDATE statsPlots SET timestamp=?,png=?,svgLight=?,svgDark=? WHERE name=?", (timestamp,png.read(),svgLight.read(),svgDark.read(),name))
        except sqlite3.Error as e:
            raise StatisticsError("Unable to save plot to database (Error: \"{}\")".format(e)) from e
# ########################################################################### #

# --------------------------------------------------------------------------- #
class StatisticsError(Exception):
    """Exception raised during statistics calculation"""
# ########################################################################### #

# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    main(sys.argv)
# ########################################################################### #
