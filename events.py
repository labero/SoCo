# -*- coding: utf-8 -*-

import socket
import requests
import logging, traceback
from gevent import pywsgi

logger = logging.getLogger(__name__)

class Events(object):
    AVTRANSPORT_ENDPOINT = 'http://{0}:1400/MediaRenderer/AVTransport/Event'

    __VALID_EVENT_TYPES = frozenset([
        'ALL',
        'TRACK_CHANGED'
        ])

    def __init__(self, speaker_ip):
        self.__listeners = {}
        self.server = None
        self.speaker_ip = speaker_ip

    def subscribe(self, callback, event_type = 'all'):
        if not isinstance(event_type, str):
            raise TypeError('Event type must be one of the following strings: '\
                            '%s' % ', '.join(__VALID_EVENT_TYPES))

        if event_type.upper() not in __VALID_EVENT_TYPES:
            raise AttributeError(   'Invalid event type: "%s". '\
                                    'Event type must be one of the following: '\
                                    '%s' % (subscription, ', '.join(__VALID_EVENT_TYPES)))

        if event_type not in self.__listeners:
            self.__listeners[event_type] = set()

        # TODO: if server not started start it now
        
        self.__listeners[event_type].add(callback)

    def unsubscribe(self, callback, event_type = 'all'):
        if not isinstance(event_type, str):
            raise TypeError('Event type must be one of the following strings: '\
                            '%s' % ', '.join(__VALID_EVENT_TYPES))

        if event_type.upper() not in __VALID_EVENT_TYPES:
            raise AttributeError(   'Invalid event type: "%s". '\
                                    'Event type must be one of the following: '\
                                    '%s' % (subscription, ', '.join(__VALID_EVENT_TYPES)))

        if event_type not in self.__listeners:
            logger.info('Event type "%s" has no callbacks, returning...' % event_type)
            return

    
        self.__listeners[event_type].remove(callback)

        if len(self.__listeners[event_type]) == 0:
            del self.__listeners[event_type]

        if not self.__listeners:
            # TODO: no callbacks are listening, stop server...
            pass

    def start(self, host='', port=8080):
        self.server = pywsgi.WSGIServer((host, port), self.__event_server)
        self.server.start()

        ip = self.__get_local_ip()

        headers = {
            'Callback': '<http://{0}:{1}>'.format(ip, port),
            'NT': 'upnp:event'
        }

        endpoint = self.AVTRANSPORT_ENDPOINT.format(self.speaker_ip)

        # `SUBSCRIBE` is a custom HTTP/1.1 verb used by Sonos devices.
        r = requests.request('SUBSCRIBE', endpoint, headers=headers)

        # Raise an exception if we get back a non-200 from the speaker.
        r.raise_for_status()

    def stop(self):
        if self.server is None:
            logger.warning('Server not initiated, returning...')
            return
        
        # TODO: Investigate if there is an `UNSUBSCRIBE` verb.
        self.server.stop()

    def __event_server(self, environ, start_response):
        status = '405 Method Not Allowed'

        # `NOTIFY` is a custom HTTP/1.1 verb used by Sonos devices
        headers = [
            ('Allow', 'NOTIFY'),
            ('Content-Type', 'text/plain')
        ]

        response = "Sorry, I only support the HTTP/1.1 NOTIFY verb.\n"

        if environ['REQUEST_METHOD'].lower() == 'notify':
            body = environ['wsgi.input'].readline()

            eventType = None
            # TODO: Parse the raw XML into something sensible and determine
            # a event type.

            # Right now, subscribed listeners will just get the raw XML
            # sent from the Sonos device.

            # Check if a callback has been subscribed
            # for this specific type of event.
            if eventType in self.__listeners:
                for callback in self.__listeners[eventType]:
                    callback(body)

            if 'ALL' in self.__listeners:    
                for callback in self.__listeners['ALL']:
                    callback(body)

            status = '200 OK'
            headers = []
            response = ''

        start_response(status, headers)
        return [response]

    def __get_local_ip(self):
        # Not a fan of this, but there isn't a good cross-platform way of
        # determining the local IP.
        # From http://stackoverflow.com/a/7335145
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        try:
            s.connect(('8.8.8.8', 9))
            ip = s.getsockname()[0]
        except socket.error:
            raise
        finally:
            del s

        return ip
