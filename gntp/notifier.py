"""
The gntp.notifier module is provided as a simple way to send notifications
using GNTP

.. note::
	This class is intended to mostly mirror the older Python bindings such
	that you should be able to replace instances of the old bindings with
	this class.
	`Original Python bindings <http://code.google.com/p/growl/source/browse/Bindings/python/Growl.py>`_

"""
import gntp
import socket
import logging

logger = logging.getLogger(__name__)


class GrowlNotifier(object):
	"""Helper class to simplfy sending Growl messages

	:param string applicationName: Sending application name
	:param list notification: List of valid notifications
	:param list defaultNotifications: List of notifications that should be enabled
		by default
	:param string applicationIcon: Icon URL
	:param string hostname: Remote host
	:param integer port: Remote port
	"""
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
		assert isinstance(self.port, int), 'Requires valid port'

	def _checkIcon(self, data):
		'''
		Check the icon to see if it's valid
		@param data:
		@todo Consider checking for a valid URL
		'''
		return data

	def register(self):
		"""Send GNTP Registration

		.. warning::
			Before sending notifications to Growl, you need to have
			sent a registration message at least once
		"""
		logger.info('Sending registration to %s:%s', self.hostname, self.port)
		register = gntp.GNTPRegister()
		register.add_header('Application-Name', self.applicationName)
		for notification in self.notifications:
			enabled = notification in self.defaultNotifications
			register.add_notification(notification, enabled)
		if self.applicationIcon:
			register.add_header('Application-Icon', self.applicationIcon)
		if self.password:
			register.set_password(self.password, self.passwordHash)
		response = self._send('register', register.encode())
		if isinstance(response, gntp.GNTPOK):
			return True
		logger.error('Invalid response %s', response.error())
		return response.error()

	def notify(self, noteType, title, description, icon=None, sticky=False, priority=None):
		"""Send a GNTP notifications

		.. warning::
			Must have registered with growl beforehand or messages will be ignored

		:param string noteType: One of the notification names registered earlier
		:param string title: Notification title (usually displayed on the notification)
		:param string description: The main content of the notification
		:param string icon: Icon URL path
		:param boolean sticky: Sticky notification
		:param integer priority: Message priority level from -2 to 2
		"""
		logger.info('Sending notification [%s] to %s:%s', noteType, self.hostname, self.port)
		assert noteType in self.notifications
		notice = gntp.GNTPNotice()
		notice.add_header('Application-Name', self.applicationName)
		notice.add_header('Notification-Name', noteType)
		notice.add_header('Notification-Title', title)
		if self.password:
			notice.set_password(self.password, self.passwordHash)
		if sticky:
			notice.add_header('Notification-Sticky', sticky)
		if priority:
			notice.add_header('Notification-Priority', priority)
		if icon:
			notice.add_header('Notification-Icon', self._checkIcon(icon))
		if description:
			notice.add_header('Notification-Text', description)
		response = self._send('notify', notice.encode())
		if isinstance(response, gntp.GNTPOK):
			return True
		logger.error('Invalid response %s', response.error())
		return response.error()

	def subscribe(self, id, name, port):
		"""Send a Subscribe request to a remote machine"""
		sub = gntp.GNTPSubscribe()
		sub.add_header('Subscriber-ID', id)
		sub.add_header('Subscriber-Name', name)
		sub.add_header('Subscriber-Port', port)
		if self.password:
			sub.set_password(self.password, self.passwordHash)
		response = self._send('subscribe', sub.encode())
		if isinstance(response, gntp.GNTPOK):
			return True
		logger.error('Invalid response %s', response.error())
		return response.error()

	def _send(self, type, data):
		"""Send the GNTP Packet"""
		logger.debug('To : %s:%s <%s>\n%s', self.hostname, self.port, type, data)

		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		s.connect((self.hostname, self.port))
		s.send(data.encode('utf8', 'replace'))
		response = gntp.parse_gntp(s.recv(1024))
		s.close()

		logger.debug('From : %s:%s <%s>\n%s', self.hostname, self.port, response.__class__, response)
		return response
