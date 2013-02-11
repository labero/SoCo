# -*- coding: utf-8 -*-

import socket
import requests
import logging, traceback
import threading

import gevent
import gevent.pywsgi
import gevent.monkey

gevent.monkey.patch_all()

logger = logging.getLogger(__name__)

class Events(threading.Thread):
    AVTRANSPORT_ENDPOINT = 'http://{0}:1400/MediaRenderer/AVTransport/Event'

    def __init__(self, speaker_ip):
        threading.Thread.__init__(self)
        self.server = None
        self.speaker_ip = speaker_ip
        self.host = ''
        self.port = 8080

        self.__greenlet = None
        self.__listeners = {}
        self.__listeners_lock = threading.RLock()

        self._valid_event_types = frozenset([
            'ALL',
            'TRACK_CHANGED'
        ])

    def __del__(self):
        if self.__greenlet:
            logging.debug('Killing greenlet')
            self.__greenlet.kill()
            del self.__greenlet
            self.__greenlet = None

        with self.__listeners_lock:
            if self.__listeners:
                logger.debug('Unsubscribing')
                for event_type in self.__listeners.keys()[:]:
                    for callback in self.__listeners[event_type][:]:
                        unsubscribe(callback, event_type = event_type)

    def subscribe(self, callback, event_type = 'all'):
        if not isinstance(event_type, str):
            raise TypeError('Event type must be one of the following strings: '\
                            '%s' % ', '.join(self._valid_event_types))

        if event_type.upper() not in self._valid_event_types:
            raise AttributeError(   'Invalid event type: "%s". '\
                                    'Event type must be one of the following: '\
                                    '%s' % (subscription, ', '.join(self._valid_event_types)))

        with self.__listeners_lock:
            if event_type not in self.__listeners:
                self.__listeners[event_type] = set()
                
            self.__listeners[event_type].add(callback)

        if self.server is None:
            self.start()

    def unsubscribe(self, callback, event_type = 'all'):
        if not isinstance(event_type, str):
            raise TypeError('Event type must be one of the following strings: '\
                            '%s' % ', '.join(self._valid_event_types))

        if event_type.upper() not in self._valid_event_types:
            raise AttributeError(   'Invalid event type: "%s". '\
                                    'Event type must be one of the following: '\
                                    '%s' % (subscription, ', '.join(self._valid_event_types)))

        with self.__listeners_lock:
            if event_type not in self.__listeners:
                logger.info('Event type "%s" has no callbacks, returning...' % event_type)
                return
        
            self.__listeners[event_type].remove(callback)

            if len(self.__listeners[event_type]) == 0:
                del self.__listeners[event_type]

    def run(self):
        server = None
        try:
            logger.debug('Starting WSGIServer')
            server = gevent.pywsgi.WSGIServer((self.host, self.port),
                                              self.__event_server)
            
            self.server = server
            self.server.start()

            ip = self.__get_local_ip()

            headers = {
                'Callback': '<http://{0}:{1}>'.format(ip, self.port),
                'NT': 'upnp:event'
            }

            endpoint = self.AVTRANSPORT_ENDPOINT.format(self.speaker_ip)

            # `SUBSCRIBE` is a custom HTTP/1.1 verb used by Sonos devices.
            r = requests.request('SUBSCRIBE', endpoint, headers=headers)

            # Raise an exception if we get back a non-200 from the speaker.
            r.raise_for_status()

            while True:
                logger.debug('Sleeping gevent for 1 seconds')
                gevent.sleep(1)

                with self.__listeners_lock:
                    if not self.__listeners:
                        break

            logging.debug('Closing server')
            self.server.stop()
        except:
            logger.error(traceback.format_exc())
            
            if server:
                server.kill()
                del server

            raise

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

            bad_callbacks = []
            with self.__listeners_lock:
                # Check if a callback has been subscribed
                # for this specific type of event.
                if eventType in self.__listeners:
                    for callback in self.__listeners[eventType]:
                        try:
                            callback(body)
                        except:
                            logger.error('Callback raised error, unsubscribing...')
                            logger.error(traceback.format_exc())
                            bad_callbacks.append((callback, eventType))

                if 'ALL' in self.__listeners:    
                    for callback in self.__listeners['ALL']:
                        try:
                            callback(body)
                        except:
                            logger.error('Callback raised error, unsubscribing...')
                            logger.error(traceback.format_exc())
                            bad_callbacks.append((callback, 'ALL'))

            if bad_callbacks:
                logger.debug('Unsubscribing bad callbacks')
                for callback, event_type in bad_callbacks:
                    self.unsubscribe(callback, event_type)

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
