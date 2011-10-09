"""
A Python module that uses GNTP to post messages
Mostly mirrors the Growl.py file that comes with Mac Growl
http://code.google.com/p/growl/source/browse/Bindings/python/Growl.py
"""
import gntp
import socket
import logging

logger = logging.getLogger(__name__)

class GrowlNotifier(object):
	applicationName = 'Python GNTP'
	notifications = []
	defaultNotifications = []
	applicationIcon = None
	passwordHash = 'MD5'

	#GNTP Specific
	password = None
	hostname = 'localhost'
	port = 23053

	def __init__(self, applicationName=None, notifications=None, defaultNotifications=None, applicationIcon=None, hostname=None, password=None, port=None):
		if applicationName:
			self.applicationName = applicationName
		assert self.applicationName, 'An application name is required.'

		if notifications:
			self.notifications = list(notifications)
		assert self.notifications, 'A sequence of one or more notification names is required.'

		if defaultNotifications is not None:
			self.defaultNotifications = list(defaultNotifications)
		elif not self.defaultNotifications:
			self.defaultNotifications = list(self.notifications)

		if applicationIcon is not None:
			self.applicationIcon = self._checkIcon(applicationIcon)
		elif self.applicationIcon is not None:
			self.applicationIcon = self._checkIcon(self.applicationIcon)

		#GNTP Specific
		if password:
			self.password = password

		if hostname:
			self.hostname = hostname
		assert self.hostname, 'Requires valid hostname'

		if port:
			self.port = int(port)
		assert isinstance(self.port,int), 'Requires valid port'

	def _checkIcon(self, data):
		'''
		Check the icon to see if it's valid
		@param data:
		@todo Consider checking for a valid URL
		'''
		return data

	def register(self):
		'''
		Send GNTP Registration
		'''
		logger.info('Sending registration to %s:%s',self.hostname,self.port)
		register = gntp.GNTPRegister()
		register.add_header('Application-Name',self.applicationName)
		for notification in self.notifications:
			enabled = notification in self.defaultNotifications
			register.add_notification(notification,enabled)
		if self.applicationIcon:
			register.add_header('Application-Icon',self.applicationIcon)
		if self.password:
			register.set_password(self.password,self.passwordHash)
		response = self.send('register',register.encode())
		if isinstance(response,gntp.GNTPOK): return True
		logger.debug('Invalid response %s',response.error())
		return response.error()

	def notify(self, noteType, title, description, icon=None, sticky=False, priority=None):
		'''
		Send a GNTP notifications
		'''
		logger.info('Sending notification [%s] to %s:%s',noteType,self.hostname,self.port)
		assert noteType in self.notifications
		notice = gntp.GNTPNotice()
		notice.add_header('Application-Name',self.applicationName)
		notice.add_header('Notification-Name',noteType)
		notice.add_header('Notification-Title',title)
		if self.password:
			notice.set_password(self.password,self.passwordHash)
		if sticky:
			notice.add_header('Notification-Sticky',sticky)
		if priority:
			notice.add_header('Notification-Priority',priority)
		if icon:
			notice.add_header('Notification-Icon',self._checkIcon(icon))
		if description:
			notice.add_header('Notification-Text',description)
		response = self.send('notify',notice.encode())
		if isinstance(response,gntp.GNTPOK): return True
		logger.debug('Invalid response %s',response.error())
		return response.error()
	def subscribe(self,id,name,port):
		sub = gntp.GNTPSubscribe()
		sub.add_header('Subscriber-ID',id)
		sub.add_header('Subscriber-Name',name)
		sub.add_header('Subscriber-Port',port)
		if self.password:
			sub.set_password(self.password,self.passwordHash)
		response = self.send('subscribe',sub.encode())
		if isinstance(response,gntp.GNTPOK): return True
		logger.debug('Invalid response %s',response.error())
		return response.error()
	def send(self,type,data):
		'''
		Send the GNTP Packet
		'''
		#logger.debug('To : %s:%s <%s>\n%s',self.hostname,self.port,type,data)
		#Less verbose please
		logger.debug('To : %s:%s <%s>',self.hostname,self.port,type)

		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		s.settimeout(1)
		s.connect((self.hostname,self.port))
		s.send(data.encode('utf-8', 'replace'))
		response = gntp.parse_gntp(s.recv(1024))
		s.close()

		#logger.debug('From : %s:%s <%s>\n%s',self.hostname,self.port,response.__class__,response)
		#Less verbose please
		logger.debug('From : %s:%s <%s>',self.hostname,self.port,response.__class__)
		return response
