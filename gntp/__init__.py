import re
import hashlib
import time
import platform

__version__ = '0.4'

class BaseError(Exception):
	pass

class ParseError(BaseError):
	def gntp_error(self):
		error = GNTPError(errorcode=500,errordesc='Error parsing the message')
		return error.encode()

class AuthError(BaseError):
	def gntp_error(self):
		error = GNTPError(errorcode=400,errordesc='Error with authorization')
		return error.encode()

class UnsupportedError(BaseError):
	def gntp_error(self):
		error = GNTPError(errorcode=500,errordesc='Currently unsupported by gntp.py')
		return error.encode()

class _GNTPBase(object):
	info = {
		'version':'1.0',
		'messagetype':None,
		'encryptionAlgorithmID':None
	}
	_requiredHeaders = []
	headers = {}
	resources = {}
	def add_origin_info(self):
		self.add_header('Origin-Machine-Name',platform.node())
		self.add_header('Origin-Software-Name','gntp.py')
		self.add_header('Origin-Software-Version',__version__)
		self.add_header('Origin-Platform-Name',platform.system())
		self.add_header('Origin-Platform-Version',platform.platform())
	def __str__(self):
		return self.encode()
	def _parse_info(self,data):
		'''
		Parse the first line of a GNTP message to get security and other info values
		@param data: GNTP Message
		@return: GNTP Message information in a dictionary
		'''
		#GNTP/<version> <messagetype> <encryptionAlgorithmID>[:<ivValue>][ <keyHashAlgorithmID>:<keyHash>.<salt>]
		match = re.match('GNTP/(?P<version>\d+\.\d+) (?P<messagetype>REGISTER|NOTIFY|SUBSCRIBE|\-OK|\-ERROR)'+
						' (?P<encryptionAlgorithmID>[A-Z0-9]+(:(?P<ivValue>[A-F0-9]+))?) ?'+
						'((?P<keyHashAlgorithmID>[A-Z0-9]+):(?P<keyHash>[A-F0-9]+).(?P<salt>[A-F0-9]+))?\r\n', data,re.IGNORECASE)
		
		if not match:
			raise ParseError('ERROR_PARSING_INFO_LINE')
		
		info = match.groupdict()
		if info['encryptionAlgorithmID'] == 'NONE':
			info['encryptionAlgorithmID'] = None
		
		return info
	def set_password(self,password,encryptAlgo='MD5'):
		'''
		Set a password for a GNTP Message
		@param password:  Null to clear password
		@param encryptAlgo: Supports MD5,SHA1,SHA256,SHA512
		@todo: Support other hash functions
		'''
		hash = {
			'MD5': hashlib.md5,
			'SHA1': hashlib.sha1,
			'SHA256': hashlib.sha256,
			'SHA512': hashlib.sha512,
		}
		
		self.password = password
		self.encryptAlgo = encryptAlgo.upper()
		if not password:
			self.info['encryptionAlgorithmID'] = None
			self.info['keyHashAlgorithm'] = None;
			return
		if not self.encryptAlgo in hash.keys():
			raise UnsupportedError('INVALID HASH "%s"'%self.encryptAlgo) 
		
		hashfunction = hash.get(self.encryptAlgo)
		
		password = password.encode('utf8')
		seed = time.ctime()
		salt = hashfunction(seed).hexdigest()
		saltHash = hashfunction(seed).digest()
		keyBasis = password+saltHash
		key = hashfunction(keyBasis).digest()
		keyHash = hashfunction(key).hexdigest()
				
		self.info['keyHashAlgorithmID'] = self.encryptAlgo
		self.info['keyHash'] = keyHash.upper()
		self.info['salt'] = salt.upper()
	def _decode_hex(self,value):
		'''
		Helper function to decode hex string to `proper` hex string
		@param value: Value to decode
		@return: Hex string
		'''
		result = ''
		for i in range(0,len(value),2):
			tmp = int(value[i:i+2],16)
			result += chr(tmp)
		return result
	def _decode_binary(self,rawIdentifier,identifier):
		rawIdentifier += '\r\n\r\n'
		dataLength = int(identifier['Length'])
		pointerStart = self.raw.find(rawIdentifier)+len(rawIdentifier)
		pointerEnd = pointerStart + dataLength
		data = self.raw[pointerStart:pointerEnd]
		if not len(data) == dataLength:
			raise ParseError('INVALID_DATA_LENGTH Expected: %s Recieved %s'%(dataLength,len(data)))
		return data
	def _validate_password(self,password):
		'''
		Validate GNTP Message against stored password
		'''
		self.password = password
		if password == None: raise Exception()
		keyHash = self.info.get('keyHash',None)
		if keyHash is None and self.password is None:
			return True
		if keyHash is None:
			raise AuthError('Invalid keyHash')
		if self.password is None:
			raise AuthError('Missing password')
		
		password = self.password.encode('utf8')
		saltHash = self._decode_hex(self.info['salt'])
		
		keyBasis = password+saltHash
		key = hashlib.md5(keyBasis).digest()
		keyHash = hashlib.md5(key).hexdigest()
		
		if not keyHash.upper() == self.info['keyHash'].upper():
			raise AuthError('Invalid Hash')
		return True
	def validate(self):
		'''
		Verify required headers
		'''
		for header in self._requiredHeaders:
			if not self.headers.get(header,False):
				raise ParseError('Missing Notification Header: '+header)
		
	def _format_info(self):
		'''
		Generate info line for GNTP Message
		@return: Info line string
		'''
		info = u'GNTP/%s %s'%(
			self.info.get('version'),
			self.info.get('messagetype'),
		)
		if self.info.get('encryptionAlgorithmID',None):
			info += ' %s:%s'%(
				self.info.get('encryptionAlgorithmID'),
				self.info.get('ivValue'),
			)
		else:
			info+=' NONE'
		
		if self.info.get('keyHashAlgorithmID',None):
			info += ' %s:%s.%s'%(
				self.info.get('keyHashAlgorithmID'),
				self.info.get('keyHash'),
				self.info.get('salt')
			)			
		
		return info	
	def _parse_dict(self,data):
		'''
		Helper function to parse blocks of GNTP headers into a dictionary
		@param data:
		@return: Dictionary of headers
		'''
		dict = {}
		for line in data.split('\r\n'):
			match = re.match('([\w-]+):(.+)', line)
			if not match: continue
			
			key = match.group(1).strip()
			val = match.group(2).strip()
			dict[key] = val
		return dict
	def add_header(self,key,value):
		if isinstance(value, unicode):
			self.headers[key] = value
		else:
			self.headers[key] = unicode('%s'%value,'utf8','replace')
	def decode(self,data,password=None):
		'''
		Decode GNTP Message
		@param data:
		'''
		self.password = password
		self.raw = data
		parts = self.raw.split('\r\n\r\n')
		self.info = self._parse_info(data)
		self.headers = self._parse_dict(parts[0])
	def encode(self):
		'''
		Encode a GNTP Message
		@return: GNTP Message ready to be sent
		'''
		self.validate()
		EOL = u'\r\n'
		
		message = self._format_info() + EOL
		#Headers
		for k,v in self.headers.iteritems():
			message += u'%s: %s%s'%(k,v,EOL)
		
		message += EOL
		return message.encode('utf8')
class GNTPRegister(_GNTPBase):
	'''
	GNTP Registration Message
	'''
	notifications = []
	_requiredHeaders = [
		'Application-Name',
		'Notifications-Count'
	]
	_requiredNotificationHeaders = ['Notification-Name']
	def __init__(self,data=None,password=None):
		'''
		@param data: (Optional) See decode()
		@param password: (Optional) Password to use while encoding/decoding messages
		'''
		self.info['messagetype'] = 'REGISTER'
		
		if data:
			self.decode(data,password)
		else:
			self.set_password(password)
			self.add_header('Application-Name', 'pygntp')
			self.add_header('Notifications-Count', 0)
			self.add_origin_info()
	def validate(self):
		'''
		Validate required headers and validate notification headers
		'''
		for header in self._requiredHeaders:
			if not self.headers.get(header,False):
				raise ParseError('Missing Registration Header: '+header)
		for notice in self.notifications:
			for header in self._requiredNotificationHeaders:
				if not notice.get(header,False):
					raise ParseError('Missing Notification Header: '+header)		
	def decode(self,data,password):
		'''
		Decode existing GNTP Registration message
		@param data: Message to decode.
		'''
		self.raw = data
		parts = self.raw.split('\r\n\r\n')
		self.info = self._parse_info(data)
		self._validate_password(password)
		self.headers = self._parse_dict(parts[0])
		
		for i,part in enumerate(parts):
			if i==0: continue  #Skip Header
			if part.strip()=='': continue
			notice = self._parse_dict(part)
			if notice.get('Notification-Name',False):
				self.notifications.append(notice)
			elif notice.get('Identifier',False):
				notice['Data'] = self._decode_binary(part,notice)
				#open('register.png','wblol').write(notice['Data'])
				self.resources[ notice.get('Identifier') ] = notice
		
	def add_notification(self,name,enabled=True):
		'''
		Add new Notification to Registration message
		@param name: Notification Name
		@param enabled: Default Notification to Enabled
		'''
		notice = {}
		notice['Notification-Name'] = u'%s'%name
		notice['Notification-Enabled'] = u'%s'%enabled
			
		self.notifications.append(notice)
		self.add_header('Notifications-Count', len(self.notifications))
	def encode(self):
		'''
		Encode a GNTP Registration Message
		@return: GNTP Registration Message ready to be sent
		'''
		self.validate()
		EOL = u'\r\n'
		
		message = self._format_info() + EOL
		#Headers
		for k,v in self.headers.iteritems():
			message += u'%s: %s%s'%(k,v,EOL)
		
		#Notifications
		if len(self.notifications)>0:
			for notice in self.notifications:
				message += EOL
				for k,v in notice.iteritems():
					message += u'%s: %s%s'%(k,v,EOL)
		
		message += EOL
		return message

class GNTPNotice(_GNTPBase):
	'''
	GNTP Notification Message
	'''
	_requiredHeaders = [
		'Application-Name',
		'Notification-Name',
		'Notification-Title'
	]
	def __init__(self,data=None,app=None,name=None,title=None,password=None):
		'''
		
		@param data: (Optional) See decode()
		@param app: (Optional) Set Application-Name
		@param name: (Optional) Set Notification-Name
		@param title: (Optional) Set Notification Title
		@param password: (Optional) Password to use while encoding/decoding messages
		'''
		self.info['messagetype'] = 'NOTIFY'
		
		if data:
			self.decode(data,password)
		else:
			self.set_password(password)
			if app:
				self.add_header('Application-Name', app)
			if name:
				self.add_header('Notification-Name', name)
			if title:
				self.add_header('Notification-Title', title)
			self.add_origin_info()
	def decode(self,data,password):
		'''
		Decode existing GNTP Notification message
		@param data: Message to decode.
		'''
		self.raw = data
		parts = self.raw.split('\r\n\r\n')
		self.info = self._parse_info(data)
		self._validate_password(password)
		self.headers = self._parse_dict(parts[0])
		
		for i,part in enumerate(parts):
			if i==0: continue  #Skip Header
			if part.strip()=='': continue
			notice = self._parse_dict(part)
			if notice.get('Identifier',False):
				notice['Data'] = self._decode_binary(part,notice)
				#open('notice.png','wblol').write(notice['Data'])
				self.resources[ notice.get('Identifier') ] = notice
	def encode(self):
		'''
		Encode a GNTP Notification Message
		@return: GNTP Notification Message ready to be sent
		'''
		self.validate()
		EOL = u'\r\n'
		
		message = self._format_info() + EOL
		#Headers
		for k,v in self.headers.iteritems():
			message += u'%s: %s%s'%(k,v,EOL)
		
		message += EOL
		return message.encode('utf8')

class GNTPSubscribe(_GNTPBase):
	def __init__(self,data=None,password=None):
		self.info['messagetype'] = 'SUBSCRIBE'
		self._requiredHeaders = [
			'Subscriber-ID',
			'Subscriber-Name',
		]
		if data:
			self.decode(data,password)
		else:
			self.set_password(password)
			self.add_origin_info()

class GNTPOK(_GNTPBase):
	_requiredHeaders = ['Response-Action']
	def __init__(self,data=None,action=None):
		'''
		@param data: (Optional) See _GNTPResponse.decode()
		@param action: (Optional) Set type of action the OK Response is for
		'''
		self.info['messagetype'] = '-OK'
		if data:
			self.decode(data)
		if action:
			self.add_header('Response-Action', action)
			self.add_origin_info()

class GNTPError(_GNTPBase):
	_requiredHeaders = ['Error-Code','Error-Description']
	def __init__(self,data=None,errorcode=None,errordesc=None):
		'''
		@param data: (Optional) See _GNTPResponse.decode()
		@param errorcode: (Optional) Error code
		@param errordesc: (Optional) Error Description
		'''
		self.info['messagetype'] = '-ERROR'
		if data:
			self.decode(data)
		if errorcode:
			self.add_header('Error-Code', errorcode)
			self.add_header('Error-Description', errordesc)
			self.add_origin_info()
	def error(self):
		return self.headers['Error-Code'],self.headers['Error-Description']

def parse_gntp(data,password=None):
	'''
	Attempt to parse a message as a GNTP message
	@param data: Message to be parsed
	@param password: Optional password to be used to verify the message
	'''
	match = re.match('GNTP/(?P<version>\d+\.\d+) (?P<messagetype>REGISTER|NOTIFY|SUBSCRIBE|\-OK|\-ERROR)',data,re.IGNORECASE)
	if not match:
		raise ParseError('INVALID_GNTP_INFO')
	info = match.groupdict()
	if info['messagetype'] == 'REGISTER':
		return GNTPRegister(data,password=password)
	elif info['messagetype'] == 'NOTIFY':
		return GNTPNotice(data,password=password)
	elif info['messagetype'] == 'SUBSCRIBE':
		return GNTPSubscribe(data,password=password)
	elif info['messagetype'] == '-OK':
		return GNTPOK(data)
	elif info['messagetype'] == '-ERROR':
		return GNTPError(data)
	raise ParseError('INVALID_GNTP_MESSAGE')
