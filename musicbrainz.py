import urlparse
import urllib2
import urllib
import mbxml
import re

_useragent = "pythonmusicbrainzngs-0.1"

# Constants for validation.
VALID_INCLUDES = {
	'artist': [
		"recordings", "releases", "release-groups", "works", # Subqueries
		"various-artists", "discids", "media",
		"aliases", "tags", "user-tags", "ratings", "user-ratings", # misc
		"artist-rels", "label-rels", "recording-rels", "release-rels", "release-group-rels",
		"url-rels", "work-rels"
	], 
	'label': [
		"releases", # Subqueries
	    "discids", "media",
	    "aliases", "tags", "user-tags", "ratings", "user-ratings", # misc
		"artist-rels", "label-rels", "recording-rels", "release-rels", "release-group-rels",
		"url-rels", "work-rels"
	],
	'recording': [
		"artists", "releases", # Subqueries
	    "discids", "media", "artist-credits",
	    "tags", "user-tags", "ratings", "user-ratings", # misc
		"artist-rels", "label-rels", "recording-rels", "release-rels", "release-group-rels",
		"url-rels", "work-rels"
	],
	'release': [
		"artists", "labels", "recordings", "release-groups", "media",
		"artist-credits", "discids", "puids", "echoprints", "isrcs",
		"artist-rels", "label-rels", "recording-rels", "release-rels", "release-group-rels",
		"url-rels", "work-rels", "recording-level-rels", "work-level-rels"
	],
	'release-group': [
		"artists", "releases", "discids", "media",
		"artist-credits", "tags", "user-tags", "ratings", "user-ratings", # misc
		"artist-rels", "label-rels", "recording-rels", "release-rels", "release-group-rels",
		"url-rels", "work-rels"
	],
	'work': [
		"artists", # Subqueries
	    "aliases", "tags", "user-tags", "ratings", "user-ratings", # misc
		"artist-rels", "label-rels", "recording-rels", "release-rels", "release-group-rels",
		"url-rels", "work-rels"
	],
	'discid': [
		"artists", "labels", "recordings", "release-groups", "puids",
		"echoprints", "isrcs"
	],
	'echoprint': ["artists", "releases"],
	'puid': ["artists", "releases", "puids", "echoprints", "isrcs"],
	'isrc': ["artists", "releases", "puids", "echoprints", "isrcs"],
	'iswc': ["artists"],
}
VALID_RELEASE_TYPES = ["nat", "album", "single", "ep", "compilation", "soundtrack",
                       "spokenword", "interview", "audiobook", "live", "remix", "other"]
VALID_RELEASE_STATUSES = ["official", "promotion", "bootleg", "pseudo-release"]
VALID_SEARCH_FIELDS = {
	'artist': [
		'arid', 'artist', 'sortname', 'type', 'begin', 'end', 'comment',
		'alias', 'country', 'gender', 'tag'
	],
	'release-group': [
		'rgid', 'releasegroup', 'reid', 'release', 'arid', 'artist',
		'artistname', 'creditname', 'type', 'tag'
	],
	'release': [
		'reid', 'release', 'arid', 'artist', 'artistname', 'creditname',
		'type', 'status', 'tracks', 'tracksmedium', 'discids',
		'discidsmedium', 'mediums', 'date', 'asin', 'lang', 'script',
		'country', 'date', 'label', 'catno', 'barcode', 'puid'
	],
	'recording': [
		'rid', 'recording', 'isrc', 'arid', 'artist', 'artistname',
		'creditname', 'reid', 'release', 'type', 'status', 'tracks',
		'tracksrelease', 'dur', 'qdur', 'tnum', 'position', 'tag'
	],
	'label': [
		'laid', 'label', 'sortname', 'type', 'code', 'country', 'begin',
		'end', 'comment', 'alias', 'tag'
	],
	'work': [
		'wid', 'work', 'iswc', 'type', 'arid', 'artist', 'alias', 'tag'
	],
}

def _check_includes_impl(includes, valid_includes):
    for i in includes:
        if i not in valid_includes:
            raise InvalidIncludeError("Bad includes", "%s is not a valid include" % i)
def _check_includes(entity, inc):
    _check_includes_impl(inc, VALID_INCLUDES[entity])

# Invalid-argument exceptions.

class InvalidSearchFieldError(Exception):
	pass

class InvalidIncludeError(Exception):
	def __init__(self, msg='Invalid Includes', reason=None):
		Exception.__init__(self)
		self.msg = msg
		self.reason = reason

	def __str__(self):
		return self.msg

class InvalidFilterError(Exception):
	def __init__(self, msg='Invalid Includes', reason=None):
		Exception.__init__(self)
		self.msg = msg
		self.reason = reason

	def __str__(self):
		return self.msg

# Global authentication and endpoint details.

user = password = ""
hostname = "musicbrainz.org"
_client = ""

def auth(u, p):
	"""Set the username and password to be used in subsequent queries to
	the MusicBrainz XML API that require authentication.
	"""
	global user, password
	user = u
	password = p

def set_client(c):
	""" Set the client to be used in requests. This must be set before any
	data submissions are made.
	"""
	global _client
	_client = c

# Core functions for calling the MB API.

def _is_auth_required(entity, includes):
	""" Some calls require authentication. This returns
	True if a call does, False otherwise
	"""
	if "user-tags" in includes or "user-ratings" in includes:
		return True
	elif entity.startswith("collection"):
		return True
	else:
		return False

def _do_mb_query(entity, id, includes=[], params={}):
	"""Make a single GET call to the MusicBrainz XML API. `entity` is a
	string indicated the type of object to be retrieved. The id may be
	empty, in which case the query is a search. `includes` is a list
	of strings that must be valid includes for the entity type. `params`
	is a dictionary of additional parameters for the API call. The
	response is parsed and returned.
	"""
	# Build arguments.
	_check_includes(entity, includes)
	auth_required = _is_auth_required(entity, includes)
	args = dict(params)
	if len(includes) > 0:
		inc = " ".join(includes)
		args["inc"] = inc

	# Build the endpoint URL.
	url = urlparse.urlunparse(('http',
		hostname,
		'/ws/2/%s/%s' % (entity, id),
		'',
		urllib.urlencode(args),
		''))
	#print url
	# Make the request and parse the response.

	f = _make_http_request(url, auth_required, None, None, 'GET')
	return mbxml.parse_message(f)

def _do_mb_search(entity, query='', fields={}, limit=None, offset=None):
	"""Perform a full-text search on the MusicBrainz search server.
	`query` is a free-form query string and `fields` is a dictionary
	of key/value query parameters. They keys in `fields` must be valid
	for the given entity type.
	"""
	# Encode the query terms as a Lucene query string.
	query_parts = [query.replace('\x00', '').strip()]
	for key, value in fields.iteritems():
		# Ensure this is a valid search field.
		if key not in VALID_SEARCH_FIELDS[entity]:
			raise InvalidSearchFieldError(
				'%s is not a valid search field for %s' % (key, entity)
			)

		# Escape Lucene's special characters.
		value = re.sub(r'([+\-&|!(){}\[\]\^"~*?:\\])', r'\\\1', value)
		value = value.replace('\x00', '').strip()
		if value:
			query_parts.append(u'%s:(%s)' % (key, value))
	full_query = u' '.join(query_parts).strip()
	if not full_query:
		raise ValueError('at least one query term is required')

	# Additional parameters to the search.
	params = {'query': full_query}
	if limit:
		params['limit'] = str(limit)
	if offset:
		params['offset'] = str(offset)

	return _do_mb_query(entity, '', [], params)

# From pymb2
class _RedirectPasswordMgr(urllib2.HTTPPasswordMgr):
	def __init__(self):
		self._realms = { }

	def find_user_password(self, realm, uri):
		# ignoring the uri parameter intentionally
		try:
			return self._realms[realm]
		except KeyError:
			return (None, None)

	def add_password(self, realm, uri, username, password):
		# ignoring the uri parameter intentionally
		self._realms[realm] = (username, password)

class DigestAuthHandler(urllib2.HTTPDigestAuthHandler):
	def get_authorization (self, req, chal):
		qop = chal.get ('qop', None)
		if qop and ',' in qop and 'auth' in qop.split (','):
			chal['qop'] = 'auth'

		return urllib2.HTTPDigestAuthHandler.get_authorization (self, req, chal)

class MusicbrainzHttpRequest(urllib2.Request):
	""" A custom request handler that allows DELETE and PUT"""
	def __init__(self, method, url, data=None):
		urllib2.Request.__init__(self, url, data)
		allowed_m = ["GET", "POST", "DELETE", "PUT"]
		if method not in allowed_m:
			raise Exception("invalid method: %s" % method)
		self.method = method

	def get_method(self):
		return self.method

def _make_http_request(url, auth_req, data, body, method):
	# Set this to 1 to debug the http transaction
	httpHandler = urllib2.HTTPHandler(debuglevel=0)
	handlers = [httpHandler]
	# if user contributed entities are requested, we need to authenticate
	# This test should maybe be up a level, and this just tests "if auth_needed:"
	if auth_req:
		if user == "":
			raise Exception("use musicbrainz.auth(u, p) first")
		passwordMgr = _RedirectPasswordMgr()
		authHandler = DigestAuthHandler(passwordMgr)
		authHandler.add_password("musicbrainz.org", (), user, password)
		handlers.append(authHandler)

	opener = urllib2.build_opener(*handlers)

	req = MusicbrainzHttpRequest(method, url, data)
	req.add_header('User-Agent', _useragent)
	if body:
		req.add_header('Content-Type', 'application/xml; charset=UTF-8')
	try:
	    if body:
		    f = opener.open(req, body)
	    else:
	        f = opener.open(req)
	except urllib2.URLError, e:
		if e.fp:
			print e.fp.read()
		raise
	return f

def _do_mb_delete(entity):
	"""Perform a single POST call to the MusicBrainz XML API.
	"""
	if _client == "":
		raise Exception("set a client name with musicbrainz.set_client(\"client-version\")")
	args = {"client": _client}
	url = urlparse.urlunparse(('http',
		hostname,
		'/ws/2/%s' % (entity,),
		'',
		urllib.urlencode(args),
		''))
	#print url
	
	f = _make_http_request(url, auth_req=True, data=None, body=None, method="DELETE")
	return mbxml.parse_message(f)

def _do_mb_put(entity):
	"""Perform a single POST call to the MusicBrainz XML API.
	"""
	if _client == "":
		raise Exception("set a client name with musicbrainz.set_client(\"client-version\")")
	args = {"client": _client}
	url = urlparse.urlunparse(('http',
		hostname,
		'/ws/2/%s' % (entity,),
		'',
		urllib.urlencode(args),
		''))
	#print url
	
	f = _make_http_request(url, auth_req=True, data="", body=None, method="PUT")
	return mbxml.parse_message(f)

def _do_mb_post(entity, body):
	"""Perform a single POST call to the MusicBrainz XML API.
	"""
	if _client == "":
		raise Exception("set a client name with musicbrainz.set_client(\"client-version\")")
	args = {"client": _client}
	url = urlparse.urlunparse(('http',
		hostname,
		'/ws/2/%s' % (entity,),
		'',
		urllib.urlencode(args),
		''))
	#print url
	
	f = _make_http_request(url, auth_req=True, data=None, body=body, method="POST")
	return mbxml.parse_message(f)

def _check_filter(values, valid):
	for v in values:
		if v not in valid:
			raise InvalidFilterError(v)

def _check_filter_and_make_params(includes, release_status=[], release_type=[]):
	"""Check that the status or type values are valid. Then, check that
	the filters can be used with the given includes. Return a params
	dict that can be passed to _do_mb_query """
	if isinstance(release_status, str):
		release_status = [release_status]
	if isinstance(release_type, str):
		release_type = [release_type]
	_check_filter(release_status, VALID_RELEASE_STATUSES)
	_check_filter(release_type, VALID_RELEASE_TYPES)
	if len(release_status) and "releases" not in includes:
		raise InvalidFilterError("Can't have a status with no release include")
	if len(release_type) and ("release-groups" not in includes and "releases" not in includes):
		raise InvalidFilterError("Can't have a release type with no release-group include")
	params = {}
	if len(release_status):
		params["status"] = "|".join(release_status)
	if len(release_type):
		params["type"] = "|".join(release_type)
	return params

# Single entity by ID
def get_artist_by_id(id, includes=[], release_status=[], release_type=[]):
	params = _check_filter_and_make_params(includes, release_status, release_type)
	return _do_mb_query("artist", id, includes, params)

def get_label_by_id(id, includes=[], release_status=[], release_type=[]):
	params = _check_filter_and_make_params(includes, release_status, release_type)
	return _do_mb_query("label", id, includes, params)

def get_recording_by_id(id, includes=[], release_status=[], release_type=[]):
	params = _check_filter_and_make_params(includes, release_status, release_type)
	return _do_mb_query("recording", id, includes, params)

def get_release_by_id(id, includes=[], release_status=[], release_type=[]):
	params = _check_filter_and_make_params(includes, release_status, release_type)
	return _do_mb_query("release", id, includes, params)

def get_release_group_by_id(id, includes=[], release_status=[], release_type=[]):
	params = _check_filter_and_make_params(includes, release_status, release_type)
	return _do_mb_query("release-group", id, includes, params)

def get_work_by_id(id, includes=[]):
	return _do_mb_query("work", id, includes)


# Searching

def artist_search(query='', limit=None, offset=None, **fields):
	"""Search for artists by a free-form `query` string and/or any of
	the following keyword arguments specifying field queries:
	arid, artist, sortname, type, begin, end, comment, alias, country,
	gender, tag
	"""
	return _do_mb_search('artist', query, fields, limit, offset)

def label_search(query='', limit=None, offset=None, **fields):
	"""Search for labels by a free-form `query` string and/or any of
	the following keyword arguments specifying field queries:
	laid, label, sortname, type, code, country, begin, end, comment,
	alias, tag
	"""
	return _do_mb_search('label', query, fields, limit, offset)

def recording_search(query='', limit=None, offset=None, **fields):
	"""Search for recordings by a free-form `query` string and/or any of
	the following keyword arguments specifying field queries:
	rid, recording, isrc, arid, artist, artistname, creditname, reid,
	release, type, status, tracks, tracksrelease, dur, qdur, tnum,
	position, tag
	"""
	return _do_mb_search('recording', query, fields, limit, offset)

def release_search(query='', limit=None, offset=None, **fields):
	"""Search for releases by a free-form `query` string and/or any of
	the following keyword arguments specifying field queries:
	reid, release, arid, artist, artistname, creditname, type, status,
	tracks, tracksmedium, discids, discidsmedium, mediums, date, asin,
	lang, script, country, date, label, catno, barcode, puid
	"""
	return _do_mb_search('release', query, fields, limit, offset)

def release_group_search(query='', limit=None, offset=None, **fields):
	"""Search for release groups by a free-form `query` string and/or
	any of the following keyword arguments specifying field queries:
	rgid, releasegroup, reid, release, arid, artist, artistname,
	creditname, type, tag
	"""
	return _do_mb_search('release-group', query, fields, limit, offset)

def work_search(query='', limit=None, offset=None, **fields):
	"""Search for works by a free-form `query` string and/or any of
	the following keyword arguments specifying field queries:
	wid, work, iswc, type, arid, artist, alias, tag
	"""
	return _do_mb_search('work', query, fields, limit, offset)


# Lists of entities
def get_releases_by_discid(id, includes=[], release_type=[]):
	params = _check_filter_and_make_params(includes, release_type=release_type)
	return _do_mb_query("discid", id, includes, params)

def get_recordings_by_echoprint(echoprint, includes=[], release_status=[], release_type=[]):
	params = _check_filter_and_make_params(includes, release_status, release_type)
	return _do_mb_query("echoprint", echoprint, includes, params)

def get_recordings_by_puid(puid, includes=[], release_status=[], release_type=[]):
	params = _check_filter_and_make_params(includes, release_status, release_type)
	return _do_mb_query("puid", puid, includes, params)

def get_recordings_by_isrc(isrc, includes=[], release_status=[], release_type=[]):
	params = _check_filter_and_make_params(includes, release_status, release_type)
	return _do_mb_query("isrc", isrc, includes, params)

def get_works_by_iswc(iswc, includes=[]):
	return _do_mb_query("iswc", iswc, includes)

# Browse methods
# Browse include are a subset of regular get includes, so we check them here
# and the test in _do_mb_query will pass anyway.
def browse_artist(recording=None, release=None, release_group=None, includes=[], limit=None, offset=None):
    # optional parameter work?
    _check_includes_impl(includes, ["aliases", "tags", "ratings", "user-tags", "user-ratings"])
    p = {}
    if recording: p["recording"] = recording
    if release: p["release"] = release
    if release_group: p["release-group"] = release_group
    #if work: p["work"] = work
    if len(p) > 1:
        raise Exception("Can't have more than one of recording, release, release_group, work")
    if limit: p["limit"] = limit
    if offset: p["offset"] = offset
    return _do_mb_query("artist", "", includes, p)

def browse_label(release=None, includes=[], limit=None, offset=None):
    _check_includes_impl(includes, ["aliases", "tags", "ratings", "user-tags", "user-ratings"])
    p = {"release": release}
    if limit: p["limit"] = limit
    if offset: p["offset"] = offset
    return _do_mb_query("label", "", includes, p)

def browse_recording(artist=None, release=None, includes=[], limit=None, offset=None):
    _check_includes_impl(includes, ["artist-credits", "tags", "ratings", "user-tags", "user-ratings"])
    p = {}
    if artist: p["artist"] = artist
    if release: p["release"] = release
    if len(p) > 1:
        raise Exception("Can't have more than one of artist, release")
    if limit: p["limit"] = limit
    if offset: p["offset"] = offset
    return _do_mb_query("recording", "", includes, p)

def browse_release(artist=None, label=None, recording=None, release_group=None, release_status=[], release_type=[], includes=[], limit=None, offset=None):
    # track_artist param doesn't work yet
    _check_includes_impl(includes, ["artist-credits", "labels", "recordings"])
    p = {}
    if artist: p["artist"] = artist
    #if track_artist: p["track_artist"] = track_artist
    if label: p["label"] = label
    if recording: p["recording"] = recording
    if release_group: p["release-group"] = release_group
    if len(p) > 1:
        raise Exception("Can't have more than one of artist, label, recording, release_group")
    if limit: p["limit"] = limit
    if offset: p["offset"] = offset
    filterp = _check_filter_and_make_params("releases", release_status, release_type)
    p.update(filterp)
    if len(release_status) == 0 and len(release_type) == 0:
        raise InvalidFilterError("Need at least one release status or type")
    return _do_mb_query("release", "", includes, p)

def browse_release_group(artist=None, release=None, release_type=[], includes=[], limit=None, offset=None):
    _check_includes_impl(includes, ["artist-credits", "tags", "ratings", "user-tags", "user-ratings"])
    p = {}
    if artist: p["artist"] = artist
    if release: p["release"] = release
    if len(p) > 1:
        raise Exception("Can't have more than one of artist, release")
    if limit: p["limit"] = limit
    if offset: p["offset"] = offset
    filterp = _check_filter_and_make_params("release-groups", [], release_type)
    p.update(filterp)
    if len(release_type) == 0:
        raise InvalidFilterError("Need at least one release type")
    return _do_mb_query("release-group", "", includes, p)

# browse_work is defined in the docs but has no browse criteria

# Collections
def get_all_collections():
	# Missing <release-list count="n"> the count in the reply
	return _do_mb_query("collection", '')

def get_releases_in_collection(collection):
	return _do_mb_query("collection", "%s/releases" % collection)

# Submission methods

def submit_barcodes(barcodes):
	"""
	Submits a set of {release1: barcode1, release2:barcode2}
	Must call auth(user, pass) first
	"""
	query = mbxml.make_barcode_request(barcodes)
	return _do_mb_post("release", query)

def submit_puids(puids):
	query = mbxml.make_puid_request(puids)
	return _do_mb_post("recording", query)

def submit_echoprints(echoprints):
	query = mbxml.make_echoprint_request(echoprints)
	return _do_mb_post("recording", query)

def submit_isrcs(isrcs):
	raise NotImplementedError

def submit_tags(artist_tags={}, recording_tags={}):
	""" Submit user tags.
	    Artist or recording parameters are of the form:
	    {'entityid': [taglist]}
	"""
	query = mbxml.make_tag_request(artist_tags, recording_tags)
	return _do_mb_post("tag", query)

def submit_ratings(artist_ratings={}, recording_ratings={}):
	""" Submit user ratings.
	    Artist or recording parameters are of the form:
	    {'entityid': rating}
	"""
	query = mbxml.make_rating_request(artist_ratings, recording_ratings)
	return _do_mb_post("rating", query)

def add_releases_to_collection(collection, releases=[]):
	# XXX: Maximum URI length of 16kb means we should only allow ~400 releases
	releaselist = ";".join(releases)
   	_do_mb_put("collection/%s/releases/%s" % (collection, releaselist))

def remove_releases_from_collection(collection, releases=[]):
	releaselist = ";".join(releases)
   	_do_mb_delete("collection/%s/releases/%s" % (collection, releaselist))
