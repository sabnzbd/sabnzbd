"""SMTP over SSL client.

Public class:	SMTP_SSL
Public errors:	SMTPSSLException
"""

# Author: Matt Butcher <mbutche@luc.edu>, Feb. 2007
# License: MIT License (or, at your option, the GPL, v.2 or later as posted at
# http://gnu.org).
##
## Begin License
#
# Copyright (c) 2007 M Butcher
#
# Permission is hereby granted, free of charge, to any person obtaining a copy 
# of this software and associated documentation files (the "Software"), to deal 
# in the Software without restriction, including without limitation the rights 
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell 
# copies of the Software, and to permit persons to whom the Software is 
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in 
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR 
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, 
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE 
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER 
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, 
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE 
# SOFTWARE.
##
##End License
#
# This is just a minor modification to the smtplib code by Dragon De Monsyn.
import smtplib, socket

__version__ = "1.00"

__all__ = ['SMTPSSLException', 'SMTP_SSL']

SSMTP_PORT = 465

class SMTPSSLException(smtplib.SMTPException):
	"""Base class for exceptions resulting from SSL negotiation."""
	
class SMTP_SSL (smtplib.SMTP):
	"""This class provides SSL access to an SMTP server.
	SMTP over SSL typical listens on port 465. Unlike StartTLS, SMTP over SSL
	makes an SSL connection before doing a helo/ehlo. All transactions, then,
	are done over an encrypted channel.

	This class is a simple subclass of the smtplib.SMTP class that comes with
	Python. It overrides the connect() method to use an SSL socket, and it
	overrides the starttles() function to throw an error (you can't do 
	starttls within an SSL session).
	"""
	certfile = None
	keyfile = None

	def __init__(self, host='', port=0, local_hostname=None, keyfile=None, certfile=None):
		"""Initialize a new SSL SMTP object.

		If specified, `host' is the name of the remote host to which this object
		will connect. If specified, `port' specifies the port (on `host') to
		which this object will connect. `local_hostname' is the name of the
		localhost. By default, the value of socket.getfqdn() is used.

		An SMTPConnectError is raised if the SMTP host does not respond 
		correctly.

		An SMTPSSLError is raised if SSL negotiation fails.

		Warning: This object uses socket.ssl(), which does not do client-side
		verification of the server's cert.
		"""
		self.certfile = certfile
		self.keyfile = keyfile
		smtplib.SMTP.__init__(self, host, port, local_hostname)

	def connect(self, host='localhost', port=0):
		"""Connect to an SMTP server using SSL.

		`host' is localhost by default. Port will be set to 465 (the default
		SSL SMTP port) if no port is specified.

		If the host name ends with a colon (`:') followed by a number, 
		that suffix will be stripped off and the
		number interpreted as the port number to use. This will override the 
		`port' parameter.

		Note: This method is automatically invoked by __init__, if a host is
		specified during instantiation.
		"""
		# MB: Most of this (Except for the socket connection code) is from 
		# the SMTP.connect() method. I changed only the bare minimum for the 
		# sake of compatibility.
		if not port and (host.find(':') == host.rfind(':')):
			i = host.rfind(':')
			if i >= 0:
				host, port = host[:i], host[i+1:]
				try: port = int(port)
				except ValueError:
					raise socket.error, "nonnumeric port"
		if not port: port = SSMTP_PORT
		if self.debuglevel > 0: print>>stderr, 'connect:', (host, port)
		msg = "getaddrinfo returns an empty list"
		self.sock = None
		for res in socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM):
			af, socktype, proto, canonname, sa = res
			try:
				self.sock = socket.socket(af, socktype, proto)
				if self.debuglevel > 0: print>>stderr, 'connect:', (host, port)
				self.sock.connect(sa)
				# MB: Make the SSL connection.
				sslobj = socket.ssl(self.sock, self.keyfile, self.certfile)
			except socket.error, msg:
				if self.debuglevel > 0: 
					print>>stderr, 'connect fail:', (host, port)
				if self.sock:
					self.sock.close()
				self.sock = None
				continue
			break
		if not self.sock:
			raise socket.error, msg

		# MB: Now set up fake socket and fake file classes.
		# Thanks to the design of smtplib, this is all we need to do
		# to get SSL working with all other methods.
		self.sock = smtplib.SSLFakeSocket(self.sock, sslobj)
		self.file = smtplib.SSLFakeFile(sslobj);

		(code, msg) = self.getreply()
		if self.debuglevel > 0: print>>stderr, "connect:", msg
		return (code, msg)

	def setkeyfile(self, keyfile):
		"""Set the absolute path to a file containing a private key.

		This method will only be effective if it is called before connect().

		This key will be used to make the SSL connection."""
		self.keyfile = keyfile

	def setcertfile(self, certfile):
		"""Set the absolute path to a file containing a x.509 certificate.

		This method will only be effective if it is called before connect().

		This certificate will be used to make the SSL connection."""
		self.certfile = certfile

	def starttls(self, keyfile = None, certfile = None):
		"""Raises an exception. 
		You cannot do StartTLS inside of an ssl session. Calling starttls() will
		return an SMTPSSLException"""
		raise SMTPSSLException, "Cannot perform StartTLS within SSL session."

