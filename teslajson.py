""" Simple Python class to access the Tesla JSON API
https://github.com/gglockner/teslajson

The Tesla JSON API is described at:
http://docs.timdorr.apiary.io/

Example:

import teslajson
c = teslajson.Connection('youremail', 'yourpassword')
v = c.vehicles[0]
v.wake_up()
v.data_request('charge_state')
v.command('charge_start')
"""

try: # Python 3
    from urllib.parse import urlencode
    from urllib.request import Request, build_opener
    from urllib.request import ProxyHandler, HTTPBasicAuthHandler, HTTPHandler
except: # Python 2
    from urllib import urlencode
    from urllib2 import Request, build_opener
    from urllib2 import ProxyHandler, HTTPBasicAuthHandler, HTTPHandler
import json
import datetime
import calendar
import warnings

class Connection(object):
    """Connection to Tesla Motors API"""
    __version__ = "1.7.1"

    def __init__(self,
            email='',
            password='',
            access_token='',
            tokens_file='',
            tesla_client='{"v1": {"id": "e4a9949fcfa04068f59abb5a658f2bac0a3428e4652315490b659d5ab3f35a9e", "secret": "c75f14bbadc8bee3a7594412c31416f8300256d7668ea7e6e7f06727bfb9d220", "baseurl": "https://owner-api.teslamotors.com", "api": "/api/1/"}}',
            proxy_url = '',
            proxy_user = '',
            proxy_password = ''):
        """Initialize connection object
        
        Sets the vehicles field, a list of Vehicle objects
        associated with your account

        Required parameters:
          Option 1: (will log in and get tokens using credentials)
            email: your login for teslamotors.com
            password: your password for teslamotors.com
          Option 2: (will use tokens directly and refresh tokens as needed)
            tokens_file: File containing json tokens data, will update after refresh
          Option 3: (use use specified token until it is invalid>
            access_token
          If you combine option 1&2, it will populate the tokens file
        
        Optional parameters:
        access_token: API access token
        proxy_url: URL for proxy server
        proxy_user: username for proxy server
        proxy_password: password for proxy server
        """
        self.proxy_url = proxy_url
        self.proxy_user = proxy_user
        self.proxy_password = proxy_password
        tesla_client = json.loads(tesla_client)
        self.current_client = tesla_client['v1']
        self.baseurl = self.current_client['baseurl']
        self.api = self.current_client['api']
        self.head = {}
        self.tokens_file = tokens_file
        self.access_token = access_token
        self.refresh_token = None

        if access_token:
            self._sethead(access_token)
        else:
            self.oauth = {
                "grant_type" : "password",
                "client_id" : self.current_client['id'],
                "client_secret" : self.current_client['secret'],
                "email" : email,
                "password" : password }
            self.expiration = 0 # force refresh
            if self.tokens_file:
                try:
                    with open(self.tokens_file, "r") as R:
                        self._update_tokens(stream=R)
                except IOError as e:
                    warnings.warn("Could not open file %s: %s (pressing on in hopes of alternate authentication)" % (
                    self.tokens_file, str(e)))

        self.vehicles = [Vehicle(v, self) for v in self.get('vehicles')['response']]
    
    def get(self, command):
        """Utility command to get data from API"""
        return self.post(command, None)
    
    def post(self, command, data={}):
        """Utility command to post data to API"""
        now = calendar.timegm(datetime.datetime.now().timetuple())
        if now > self.expiration:
            auth = self.__open("/oauth/token", data=self.oauth)
            self._sethead(auth['access_token'],
                           auth['created_at'] + auth['expires_in'] - 86400)
        return self.__open("%s%s" % (self.api, command), headers=self.head, data=data)

    def _user_agent(self):
        """Set the user agent"""
        if not "User-Agent" in self.head:
            self.head["User-Agent"] = 'teslajson.py ' + self.__version__

    def _sethead(self, access_token, expiration=float('inf')):
        """Set HTTP header"""
        self.access_token = access_token
        self.expiration = expiration
        self.head = {"Authorization": "Bearer %s" % access_token}

    def _update_tokens(self, tokens=None, stream=None):
        """Update tokens from dict or json stream"""

        if stream:
            tokens = json.load(stream)

        self.access_token = tokens['access_token']
        self.refresh_token = tokens['refresh_token']
        self.expiration = tokens["created_at"] + tokens["expires_in"] - 86400

        self._sethead(self.access_token, expiration=self.expiration)

    def _refresh_token(self):
        """Refresh tokens using either (preset) email/password or refresh_token"""

        if self.refresh_token:
            self.oauth = {
                "grant_type": "refresh_token",
                "client_id": self.current_client['id'],
                "client_secret": self.current_client['secret'],
                "refresh_token": self.refresh_token }

        self.head = {}
        tokens = self.__open("/oauth/token", data=self.oauth)
        self._update_tokens(tokens=tokens)
        if self.tokens_file:
            with open(self.tokens_file, "w") as W:
                W.write(json.dumps(tokens))

    def __open(self, url, headers={}, data=None, baseurl=""):
        """Raw urlopen command"""
        if not baseurl:
            baseurl = self.baseurl
        self._user_agent()
        req = Request("%s%s" % (baseurl, url), headers=headers)
        try:
            req.data = urlencode(data).encode('utf-8') # Python 3
        except:
            try:
                req.add_data(urlencode(data)) # Python 2
            except:
                pass

        # Proxy support
        if self.proxy_url:
            if self.proxy_user:
                proxy = ProxyHandler({'https': 'https://%s:%s@%s' % (self.proxy_user,
                                                                     self.proxy_password,
                                                                     self.proxy_url)})
                auth = HTTPBasicAuthHandler()
                opener = build_opener(proxy, auth, HTTPHandler)
            else:
                handler = ProxyHandler({'https': self.proxy_url})
                opener = build_opener(handler)
        else:
            opener = build_opener()
        resp = opener.open(req)
        charset = resp.info().get('charset', 'utf-8')
        return json.loads(resp.read().decode(charset))
        

class Vehicle(dict):
    """Vehicle class, subclassed from dictionary.
    
    There are 3 primary methods: wake_up, data_request and command.
    data_request and command both require a name to specify the data
    or command, respectively. These names can be found in the
    Tesla JSON API."""
    def __init__(self, data, connection):
        """Initialize vehicle class
        
        Called automatically by the Connection class
        """
        super(Vehicle, self).__init__(data)
        self.connection = connection

    def data(self, name='data'):
        """Get vehicle data"""
        result = self.get('%s' % name)
        return result['response']

    def data_request(self, name):
        """Get vehicle data_request"""
        return self.data('data_request/%s' % name)
    
    def wake_up(self):
        """Wake the vehicle"""
        return self.post('wake_up')
    
    def command(self, name, data={}):
        """Run the command for the vehicle"""
        return self.post('command/%s' % name, data)
    
    def get(self, command):
        """Utility command to get data from API"""
        return self.connection.get('vehicles/%i/%s' % (self['id'], command))
    
    def post(self, command, data={}):
        """Utility command to post data to API"""
        return self.connection.post('vehicles/%i/%s' % (self['id'], command), data)
