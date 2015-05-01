# coding:UTF-8
import os
import re

import mediaitem
import chn_class
from config import Config

from helpers.jsonhelper import JsonHelper
from helpers.encodinghelper import EncodingHelper
# from xbmcwrapper import XbmcWrapper
# from helpers.languagehelper import LanguageHelper
# from addonsettings import AddonSettings
from helpers.htmlentityhelper import HtmlEntityHelper

from logger import Logger
from streams.m3u8 import M3u8
from urihandler import UriHandler


class Channel(chn_class.Channel):

    def __init__(self, channelInfo):
        """Initialisation of the class.

        Arguments:
        channelInfo: ChannelInfo - The channel info object to base this channel on.

        All class variables should be instantiated here and this method should not
        be overridden by any derived classes.

        """

        chn_class.Channel.__init__(self, channelInfo)

        # ============== Actual channel setup STARTS here and should be overwritten from derived classes ===============
        self.noImage = "oppetarkivimage.png"

        # setup the urls
        self.mainListUri = "http://www.oppetarkiv.se/kategori/titel"
        self.baseUrl = "http://www.oppetarkiv.se"
        self.swfUrl = "%s/public/swf/svtplayer-9017918b040e054d1e3c902fc13ceb5d.swf" % (self.baseUrl,)

        # setup the main parsing data
        self.episodeItemRegex = '<li class="svtoa[^>]*>\W*<a[^>]+href="([^"]+)"[^>]*>([^<]+)</a>\W*</li>'
        self.videoItemRegex = '<img[^>]+name="([^"]+)"[^>]+>\W+</figure>\W+<[^>]+>\W+(?:<h1[^>]+>([^<]*)</h1>\W+){0,1}<h\d[^>]+><a[^>]+title="([^"]+)[^>]+href="([^"]+video/(\d+)/[^"]*)"[^>]*>[^>]+</a></h\d>\W+<p class="svt-text-time[^>]+\W+([^>]+)'
        self.pageNavigationRegex = '<a href="(http://www.oppetarkiv.se/[^?]+\?sida=)(\d+)(&amp;sort=[^"]+)'
        self.pageNavigationRegexIndex = 1

        # ====================================== Actual channel setup STOPS here =======================================
        return

    def CreatePageItem(self, resultSet):
        """Creates a MediaItem of type 'page' using the resultSet from the regex.

        Arguments:
        resultSet : tuple(string) - the resultSet of the self.pageNavigationRegex

        Returns:
        A new MediaItem of type 'page'

        This method creates a new MediaItem from the Regular Expression or Json
        results <resultSet>. The method should be implemented by derived classes
        and are specific to the channel.

        """

        item = chn_class.Channel.CreatePageItem(self, resultSet)
        item.url = "%s&embed=true" % (item.url,)
        return item

    def CreateEpisodeItem(self, resultSet):
        """Creates a new MediaItem for an episode

        Arguments:
        resultSet : list[string] - the resultSet of the self.episodeItemRegex

        Returns:
        A new MediaItem of type 'folder'

        This method creates a new MediaItem from the Regular Expression
        results <resultSet>. The method should be implemented by derived classes
        and are specific to the channel.

        """

        Logger.Trace(resultSet)

        url = resultSet[0]
        if "&" in url:
            url = HtmlEntityHelper.ConvertHTMLEntities(url)

        if not url.startswith("http:"):
            url = "%s%s" % (self.baseUrl, url)

        # get the ajax page for less bandwidth
        url = "%s?sida=1&amp;sort=tid_stigande&embed=true" % (url, )

        item = mediaitem.MediaItem(resultSet[1], url)
        item.icon = self.icon
        item.thumb = self.noImage
        item.complete = True
        return item

    def CreateVideoItem(self, resultSet):
        """Creates a MediaItem of type 'video' using the resultSet from the regex.

        Arguments:
        resultSet : tuple (string) - the resultSet of the self.videoItemRegex

        Returns:
        A new MediaItem of type 'video' or 'audio' (despite the method's name)

        This method creates a new MediaItem from the Regular Expression or Json
        results <resultSet>. The method should be implemented by derived classes
        and are specific to the channel.

        If the item is completely processed an no further data needs to be fetched
        the self.complete property should be set to True. If not set to True, the
        self.UpdateVideoItem method is called if the item is focussed or selected
        for playback.

        """

        Logger.Trace(resultSet)

        thumbUrl = resultSet[0]
        if thumbUrl.startswith("//"):
            thumbUrl = "http:%s" % (thumbUrl, )
        elif not thumbUrl.startswith("http"):
            thumbUrl = "%s%s" % (self.baseUrl, thumbUrl)
        Logger.Trace(thumbUrl)

        season = resultSet[1]
        if season:
            name = "%s - %s" % (season, resultSet[2])
        else:
            name = resultSet[2]

        videoId = resultSet[4]
        url = "http://www.oppetarkiv.se/video/%s?output=json" % (videoId,)
        item = mediaitem.MediaItem(name, url)
        item.type = 'video'
        item.icon = self.icon
        item.thumb = thumbUrl

        date = resultSet[5]
        dateKey = 'datetime="'
        if dateKey in date:
            date = date[date.index(dateKey) + len(dateKey):date.index("T")]
            date = date.split("-")
            year = date[0]
            month = date[1]
            day = date[2]
            Logger.Trace("%s - %s-%s-%s", date, year, month, day)
            item.SetDate(year, month, day)
        else:
            Logger.Debug("No date found")

        item.complete = False
        return item

    def UpdateVideoItem(self, item):
        """Updates an existing MediaItem with more data.

        Arguments:
        item : MediaItem - the MediaItem that needs to be updated

        Returns:
        The original item with more data added to it's properties.

        Used to update none complete MediaItems (self.complete = False). This
        could include opening the item's URL to fetch more data and then process that
        data or retrieve it's real media-URL.

        The method should at least:
        * cache the thumbnail to disk (use self.noImage if no thumb is available).
        * set at least one MediaItemPart with a single MediaStream.
        * set self.complete = True.

        if the returned item does not have a MediaItemPart then the self.complete flag
        will automatically be set back to False.

        """

        Logger.Debug('Starting UpdateVideoItem for %s (%s)', item.name, self.channelName)

        data = UriHandler.Open(item.url, proxy=self.proxy)
        json = JsonHelper(data, Logger.Instance())
        videoData = json.GetValue("video")
        if videoData:
            part = item.CreateNewEmptyMediaPart()
            spoofIp = self._GetSetting("spoof_ip", valueForNone="0.0.0.0")
            if spoofIp:
                part.HttpHeaders["X-Forwarded-For"] = spoofIp

            # get the videos
            videoUrls = videoData.get("videoReferences")
            for videoUrl in videoUrls:
                # Logger.Trace(videoUrl)
                streamInfo = videoUrl['url']
                if "manifest.f4m" in streamInfo:
                    continue
                elif "master.m3u8" in streamInfo:
                    for s, b in M3u8.GetStreamsFromM3u8(streamInfo, self.proxy, headers=part.HttpHeaders):
                        item.complete = True
                        part.AppendMediaStream(s, b)

                    #m3u8Data = UriHandler.Open(streamInfo, proxy=self.proxy)

                    #urls = Regexer.DoRegex(self.mediaUrlRegex, m3u8Data)
                    #Logger.Trace(urls)
                    #for url in urls:
                        #part.AppendMediaStream(url[1].strip(), url[0])

            # subtitles
            subtitles = videoData.get("subtitleReferences")
            if subtitles:
                Logger.Trace(subtitles)
                subUrl = subtitles[0]["url"]
                fileName = "%s.srt" % (EncodingHelper.EncodeMD5(subUrl),)
                subData = UriHandler.Open(subUrl, proxy=self.proxy)

                # correct the subs
                regex = re.compile("^1(\d:)", re.MULTILINE)
                subData = re.sub(regex, "0\g<1>", subData)
                subData = re.sub("--> 1(\d):", "--> 0\g<1>:", subData)

                localCompletePath = os.path.join(Config.cacheDir, fileName)
                Logger.Debug("Saving subtitle to: %s", localCompletePath)
                f = open(localCompletePath, 'w')
                f.write(subData)
                f.close()
                part.Subtitle = localCompletePath

            item.complete = True

        return item
