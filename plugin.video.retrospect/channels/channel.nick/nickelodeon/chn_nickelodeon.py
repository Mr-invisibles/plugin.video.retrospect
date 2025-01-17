# coding=utf-8  # NOSONAR
# SPDX-License-Identifier: CC-BY-NC-SA-4.0

import chn_class

from regexer import Regexer
from parserdata import ParserData
from logger import Logger
from urihandler import UriHandler


class Channel(chn_class.Channel):
    """
    main class from which all channels inherit
    """

    def __init__(self, channel_info):
        """ Initialisation of the class.

        All class variables should be instantiated here and this method should not
        be overridden by any derived classes.

        :param ChannelInfo channel_info: The channel info object to base this channel on.

        """

        chn_class.Channel.__init__(self, channel_info)

        # ============== Actual channel setup STARTS here and should be overwritten from derived classes ===============
        # setup the main parsing data
        if self.channelCode == 'nickelodeon':
            self.noImage = "nickelodeonimage.png"
            self.mainListUri = "http://www.nickelodeon.nl/shows"
            self.baseUrl = "http://www.nickelodeon.nl"

        elif self.channelCode == "nickno":
            self.noImage = "nickelodeonimage.png"
            self.mainListUri = "http://www.nickelodeon.no/program/"
            self.baseUrl = "http://www.nickelodeon.no"

        else:
            raise NotImplementedError("Unknown channel code")

        episode_item_regex = r"""<a[^>]+href="(?<url>/[^"]+)"[^>]*>\W*<img[^>]+src='(?<thumburl>[^']+)'[^>]*>\W*<div class='info'>\W+<h2 class='title'>(?<title>[^<]+)</h2>\W+<p class='sub_title'>(?<description>[^<]+)</p>"""
        episode_item_regex = Regexer.from_expresso(episode_item_regex)
        self._add_data_parser(self.mainListUri, match_type=ParserData.MatchExact,
                              preprocessor=self.no_nick_jr,
                              parser=episode_item_regex, creator=self.create_episode_item)
        # <h2 class='row-title'>Nick Jr

        video_item_regex = r"""<li[^>]+data-item-id='\d+'>\W+<a href='(?<url>[^']+)'>\W+<img[^>]+src="(?<thumburl>[^"]+)"[^>]*>\W+<p class='title'>(?<title>[^<]+)</p>\W+<p[^>]+class='subtitle'[^>]*>(?<subtitle>[^>]+)</p>"""
        video_item_regex = Regexer.from_expresso(video_item_regex)
        self._add_data_parser("*",
                              preprocessor=self.pre_process_folder_list,
                              parser=video_item_regex, creator=self.create_video_item,
                              updater=self.update_video_item)

        self.pageNavigationRegex = r'href="(/video[^?"]+\?page_\d*=)(\d+)"'
        self.pageNavigationRegexIndex = 1
        self._add_data_parser("*", parser=self.pageNavigationRegex, creator=self.create_page_item)

        self.mediaUrlRegex = '<param name="src" value="([^"]+)" />'    # used for the update_video_item
        self.swfUrl = "http://origin-player.mtvnn.com/g2/g2player_2.1.7.swf"

        #===============================================================================================================
        # Test cases:
        #  NO: Avator -> Other items
        #  SE: Hotel 13 -> Other items
        #  NL: Sam & Cat -> Other items

        # ====================================== Actual channel setup STOPS here =======================================
        return

    def no_nick_jr(self, data):
        """ Performs pre-process actions for data processing.

        Accepts an data from the process_folder_list method, BEFORE the items are
        processed. Allows setting of parameters (like title etc) for the channel.
        Inside this method the <data> could be changed and additional items can
        be created.

        The return values should always be instantiated in at least ("", []).

        :param str data: The retrieve data that was loaded for the current item and URL.

        :return: A tuple of the data and a list of MediaItems that were generated.
        :rtype: tuple[str|JsonHelper,list[MediaItem]]

        """

        Logger.info("Performing Pre-Processing")
        items = []

        end = data.find("<h2 class='row-title'>Nick Jr")

        Logger.debug("Pre-Processing finished")
        if end > 0:
            Logger.debug("Nick Jr content found starting at %d", end)
            return data[:end], items
        return data, items

    def pre_process_folder_list(self, data):
        """ Performs pre-process actions for data processing.

        Accepts an data from the process_folder_list method, BEFORE the items are
        processed. Allows setting of parameters (like title etc) for the channel.
        Inside this method the <data> could be changed and additional items can
        be created.

        The return values should always be instantiated in at least ("", []).

        :param str data: The retrieve data that was loaded for the current item and URL.

        :return: A tuple of the data and a list of MediaItems that were generated.
        :rtype: tuple[str|JsonHelper,list[MediaItem]]

        """

        Logger.info("Performing Pre-Processing")
        items = []

        end = data.find('<li class="divider playlist-item">')
        if end < 0:
            end = data.find("<p>Liknande videos</p>")
        if end < 0:
            end = data.find("<p>Lignende videoer</p>")
        if end < 0:
            end = data.find("<p>Andere leuke video’s</p>")

        Logger.debug("Pre-Processing finished")
        if end > 0:
            return data[:end], items

        return data, items

    def update_video_item(self, item):
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

        Logger.debug('Starting update_video_item for %s (%s)', item.name, self.channelName)

        data = UriHandler.open(item.url, proxy=self.proxy)

        # get the playlist GUID
        playlist_guids = Regexer.do_regex("<div[^>]+data-playlist-id='([^']+)'[^>]+></div>", data)
        if not playlist_guids:
            # let's try the alternative then (for the new channels)
            playlist_guids = Regexer.do_regex('local_playlist[", -]+([a-f0-9]{20})"', data)
        playlist_guid = playlist_guids[0]
        # Logger.Trace(playlist_guid)

        # now we can get the playlist meta data
        # http://api.mtvnn.com/v2/mrss.xml?uri=mgid%3Asensei%3Avideo%3Amtvnn.com%3Alocal_playlist-39ce0652b0b3c09258d9-SE-uma_site--ad_site-nickelodeon.se-ad_site_referer-video/9764-barjakt&adSite=nickelodeon.se&umaSite={umaSite}&show_images=true&url=http%3A//www.nickelodeon.se/video/9764-barjakt
        # but this seems to work.
        # http://api.mtvnn.com/v2/mrss.xml?uri=mgid%3Asensei%3Avideo%3Amtvnn.com%3Alocal_playlist-39ce0652b0b3c09258d9
        play_list_url = "http://api.mtvnn.com/v2/mrss.xml?uri=mgid%3Asensei%3Avideo%3Amtvnn.com%3Alocal_playlist-" + playlist_guid
        play_list_data = UriHandler.open(play_list_url, proxy=self.proxy)

        # now get the real RTMP data
        rtmp_meta_data = Regexer.do_regex(
            '<media:content[^>]+[^>]+url="([^"]+)&amp;force_country=', play_list_data)[0]
        rtmp_data = UriHandler.open(rtmp_meta_data, proxy=self.proxy)

        rtmp_urls = Regexer.do_regex(
            r'<rendition[^>]+bitrate="(\d+)"[^>]*>\W+<src>([^<]+ondemand)/([^<]+)</src>', rtmp_data)

        part = item.create_new_empty_media_part()
        for rtmp_url in rtmp_urls:
            url = "%s/%s" % (rtmp_url[1], rtmp_url[2])
            bitrate = rtmp_url[0]
            converted_url = self.get_verifiable_video_url(url)
            part.append_media_stream(converted_url, bitrate)

        item.complete = True
        Logger.trace("Media url: %s", item)
        return item
