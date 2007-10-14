# Copyright (c) 2005 Christian Wyglendowski
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.


"""
Authentication providers are used by the non-framework to authenticate a user
and determine what roles the user belongs to.  Being able to authenticate
against a different source (database, text file, etc) is only a matter of
writing another provider.

Providers can be based on BaseAuthProvider.  It really doesn't do much other
than show the interface for a minimal provider.

Providers offered in this release include a simple dictionary provider
(insecure, use *only* for testing and an Active Directory provider.
"""

class BaseAuthProvider(object):
    "Subclasses need to provide an authenticate method that returns a tuple."
    
    def authenticate(self, username, password):
        """Authenticate the user.
        Must return a tuple consisting of:
            True/False depending on auth results
            List of groups that the user is a member of or empty list
        """
        return (False, [])

class DictAuthProvider(BaseAuthProvider):
    def __init__(self, authDict):
        self.users = authDict
    def authenticate(self, username, password):
        if username in self.users:
            realpass, roles = self.users[username]
            if password == realpass:
                roles.append(username)
                return (True, roles)
        return (False, [])
    def add(self, username, password, roles):
        self.users[username] = [password, roles]
        


class LDAPAuthProvider(BaseAuthProvider):
    """
    Do the LDAP dirty work to authenticate a user against and ldap server.
    Will not work as-is.  Needs to be subclassed. Assign correct values for
    attributes uid and groupList in subclasses.
    LDAPAuthProvider is my heavily reworked version of code posted on
    comp.lang.python by Stephan Diehl.
    http://groups-beta.google.com/group/comp.lang.python/msg/a476db5ff9716600
    Other than authenticating against ldap, it includes some other handy
    methods as well.
    """
    
    # uid - the ldap attribute that your users user as a login name
    uid        = ''          # override in subclass!
    
    # groupList - the ldap attribute that contains user's group membership
    groupList  = ''    # override in subclass!
    
    
    def __init__(self, protocol, host, port, path, cert=None):
        """
        Prepares an LDAP connection.

        protocol = either 'ldap' or 'ldaps'
        host     = fqdn of your ldap server
        port     = 389 (non SSL) or 636 (SSL)
        path     = the DN of the base search path
        cert     = None or the path to a PEM encoded SSL certificate
        """

        global ldap        
        import ldap
        
        
        if not (self.uid and self.groupList):
            raise NotImplementedError, \
                  "Subclasses of LDAPAuthSession must define uid and groupList"

        self.protocol  = protocol
        self.host      = host
        self.port      = port
        self.path      = path
        
        self.connected = False

        if cert:
            ldap.set_option(ldap.OPT_X_TLS_CACERTFILE, cert)

    def _connect(self):
        """
        Connects to the ldap server using the arguments to the constructor.
        """
        self.conn = ldap.initialize('%s://%s:%s' % (
            self.protocol, self.host, self.port))
        
        self.conn.protocol_version = ldap.VERSION3
        self.conn.simple_bind_s(self.sUser, self.sPasswd)
        self.connected = True

    def _disconnect(self):
        self.conn.unbind_s()
        self.connected = False

    def _authenticate(self,user, passwd):
        """
        Attempts authentication using uid;.
        Returns a tuple of (True/False) and a list of the groups
        that the user belongs to.
        """
        try:
            l = ldap.initialize('%s://%s:%s' %
                                (self.protocol, self.host, self.port)
                                )
            l.protocol_version = ldap.VERSION3
            l.simple_bind_s(user,passwd)
        except ldap.LDAPError:
            return (False, [])

        #stupid hack to deal with AD auth
        if '\\' in user:
            user = user.split('\\')[1]
        
        query = '%s=%s' % (self.uid, user)

        try:
            groups = l.search_s(self.path,
                                ldap.SCOPE_SUBTREE,
                                query,
                                [self.groupList]
                                )[0][1][self.groupList]
            groups = self.getGroupCNs(groups)
        except KeyError, ldap.LDAPError:
            groups = []

        l.unbind_s()
        return (True, groups)

    def authenticate(self, user, passwd):
        "Override in subclasses"
        result = self._authenticate(user, passwd)
        return result

    def getInfoAbout(self,user):
        """
        Returns all available attributes of a user.
        The return value is a list containing a tuple containing a string of
        the user's dn and a dict of all the attributes.  returnVal[0][0] is
        the dn, and returnVal[0][1] is the dict.
        """
        return self.conn.search_s(self.path,
                                  ldap.SCOPE_SUBTREE,
                                  '%s=%s' % (self.uid, user))
    def getGroupMembership(self, user):
        """
        Returns a list of groups that the user belongs to.
        """
        groups = self.conn.search_s(self.path,
                                  ldap.SCOPE_SUBTREE,
                                  '%s=%s' % (self.uid,user),
                                  [self.groupList])
        try:
            groups = groups[0][1][self.groupList]   #get the list of group DNs
            return getGroupCNs(groups)          #return list of the group CNs
        except KeyError:                        #not a member of any groups
            return []                           #return empty list of groups

    def getGroupCNs(self, groups):
        """Quick and dirty function to return just the CNs of member groups"""
        return [item.split(',')[0].split('=')[1] for item in groups]

class ADAuthProvider(LDAPAuthProvider):
    """
    Authenticate against an Active Directory server.

    You MUST supply a domain for the domain class attribute.    

    NOTE: This class does not work with nested groups in Active Directory. You
    will get only top level group membership.

    NOTE: This class does not detect the "primary group" in Active Directory.
    """
    
    uid       = 'sAMAccountName'    #AD username attribute
    groupList = 'memberOf'          #AD attribute that holds group membership
    domain    = ''                  #set your domain name here!

    def authenticate(self, user, passwd):
        if not self.domain:
            raise Exception, "must set self.domain"
        # this next line is critical for compatibility with Server 2003
        ldap.set_option(ldap.OPT_REFERRALS, 0)
        result = self._authenticate('%s\\%s' % (self.domain, user), passwd)
        return result
        

        
    