#"""RSS 2.0 Generator
#
#This library encapsulates the generation of an RSS (2.0) feed
#
#
#You may freely use this code in any way you can think of.
#"""
import xml.sax.saxutils

#------------------------------------------------------------------------------
def encode_for_xml(unicode_data, encoding='ascii'):
    """
    Encode unicode_data for use as XML or HTML, with characters outside
    of the encoding converted to XML numeric character references.
    """
    try:
        return unicode_data.encode(encoding, 'xmlcharrefreplace')
    except ValueError:
        # ValueError is raised if there are unencodable chars in the
        # data and the 'xmlcharrefreplace' error handler is not found.
        # Pre-2.3 Python doesn't support the 'xmlcharrefreplace' error
        # handler, so we'll emulate it.
        return _xmlcharref_encode(unicode_data, encoding)

def _xmlcharref_encode(unicode_data, encoding):
    """Emulate Python 2.3's 'xmlcharrefreplace' encoding error handler."""
    chars = []
    # Step through the unicode_data string one character at a time in
    # order to catch unencodable characters:
    for char in unicode_data:
        try:
            chars.append(char.encode(encoding, 'strict'))
        except UnicodeError:
            chars.append('&#%i;' % ord(char))
    return ''.join(chars)



class RSS:
#    """ 
#    RSS
#    
#    This class encapsulates the creation of an RSS 2.0 feed
#    
#    The RSS2.0 spec can be found here: 
#    http://blogs.law.harvard.edu/tech/rss
#    
#    
#    RSS validator :  http://rss.scripting.com
#
#
#    The generation of an RSS feed is simple, the following is a
#    sample:
#        from rsslib import RSS, Item, Namespace
#        rss = RSS()
#        rss.channel.link = "http://channel.com"
#        rss.channel.title = "my channel title"
#        rss.channel.description = "my channel description"
#        
#        ns = Namespace( "foobar", "http://foobar.baz" )
#        rss.channel.namespaces.append( ns )
#        
#        item = Item()
#        item.link = "http://link.com"
#        item.description = "my link description"
#        item.title ="my item title"
#        item.nsItems[ns.name + ":foo"] = "bar"
#        rss.channel.items.append( item )
#        
#        item = Item()
#        item.link = "http://link2.com"
#        item.description = "my link2 description"
#        item.title ="my item2 title"
#        item.nsItems[ns.name +":foo"] = "foo bar baz"
#        rss.channel.items.append( item )
#        
#        print rss.write()
#  
#    output:
#        <?xml version="1.0" encoding="UTF-8"?>
#        <rss version="2.0" xmlns:foobar=http://foobar.baz >
#        <channel>
#        <title>my channel title</title>
#        <link>http://channel.com</link>
#        <description>my channel description</description>
#        
#        <item><title>my item title</title>
#        <link>http://link.com</link>
#        <description>my link description</description>
#        <foobar:foo>bar</foobar:foo>
#        </item>
#        
#        <item><title>my item2 title</title>
#        <link>http://link2.com</link>
#        <description>my link2 description</description>
#        <foobar:foo>foo bar baz</foobar:foo>
#        </item>
#        
#        </channel>
#        </rss>
#     
#    author: cmallory /a t/ berserk /dot/ o r g
#    """ 
    def __init__(self):
        self.channel = Channel()
        self.version = "2.0"
        self.contents = None
                
#    if __name__ == "__main__" :
#        from rsslib import RSS, Item, Namespace
#        rss = RSS()
#        rss.channel.link = "http://channel.com"
#        rss.channel.title = "my channel title"
#        rss.channel.description = "my channel description"
#        
#        ns = Namespace( "foobar", "http://foobar.baz" )
#        rss.addNamespace( ns )
#        
#        item = Item()
#        item.link = "http://link.com"
#        item.description = "my link description"
#        item.title ="my item title"
#        
#        item.enclosure.url = "http://enclosure.url.com"
#        item.enclosure.length = 12345
#        item.enclosure.type = "audio/mpeg"
#        
#        item.nsItems[ns.name + ":foo"] = "bar"
#        rss.addItem( item )
#        
#        item = Item()
#        item.link = "http://link2.com"
#        item.description = "my link2 description"
#        item.title ="my item2 title"
#        item.nsItems[ns.name +":foo"] = "foo bar baz"
#        rss.addItem( item )
#        
#        print rss.write()
   

    #Write out the rss document
    def write( self ):
    
        self.contents = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        #contents += "<!--\n Last " + cnt + " urls to be shrunk \n-->\n"
        
        self.contents += "<rss version=\"" + self.version + "\" "
        if ( self.channel is not None and self.channel.namespaces is not None ):
            for ns in self.channel.namespaces :
                self.contents += "xmlns:" + ns.name + "=\"" +  ns.url + "\" "
        self.contents += ">\n"     
        self.contents += self.generateChannel()
        self.contents += "</rss>\n";
        return self.contents
            
    #Generates everything contained in a <channel> element
    def generateChannel( self ):
        contents = ""
        if ( self.channel.initialized() ):
            contents += "<channel>\n"
            contents += self.optionalWrite("title", self.channel.title );
            contents += self.optionalWrite("link", self.channel.link );
            contents += self.optionalWrite("description", self.channel.description );
            
            contents += self.optionalWrite("language", self.channel.language );
            contents += self.optionalWrite("copyright", self.channel.copyright );
            contents += self.optionalWrite("category", self.channel.category );
            contents += self.optionalWrite("managingEditor", self.channel.managingEditor );
            contents += self.optionalWrite("webMaster", self.channel.webMaster );
            contents += self.optionalWrite("pubDate", self.channel.pubDate );
            contents += self.optionalWrite("lastBuildDate", self.channel.lastBuildDate );
            contents += self.optionalWrite("docs", self.channel.docs );
            contents += self.optionalWrite("cloud", self.channel.cloud );
            contents += self.optionalWrite("ttl", self.channel.ttl );
            contents += self.optionalWrite("generator", self.channel.generator );     
            contents += self.optionalWrite("image", self.channel.image );
            contents += self.optionalWrite("rating", self.channel.rating );
            contents += self.optionalWrite("textInput", self.channel.textInput );
            contents += self.optionalWrite("skipHours", self.channel.skipHours );
            contents += self.optionalWrite("skipDays", self.channel.skipDays );
 
            contents += "\n" + self.generateItems() + "</channel>\n"
        else :
            contents = "[Channel not properly initialized.  "
            contents +="A required field is not set.(title/link/description]"
        
        return contents

    #Generates all items within a channel
    def generateItems( self ):
        c = ""
        for i in self.channel.items :

            c += "<item>"

            c += self.optionalWrite("title", i.title);
            c += self.optionalWrite("link", i.link );
            c += self.optionalWrite("description", i.description);
            c += self.optionalWrite("author", i.author );
            c += self.optionalWrite("pubDate", str(i.pubDate) )
            c += self.optionalWrite("category", i.category )
            c += self.optionalWrite("comments", i.comments )
            c += self.optionalWrite("guid", i.guid )
            c += self.optionalWrite("source", i.source )
            
            if ( i.enclosure.url != "" ):
                c+= "<enclosure url=\"" + i.enclosure.url + "\" "
                c+= "length=\"" + str(i.enclosure.length )+ "\" "
                c+= "type=\"" + i.enclosure.type + "\"/>\n"
                
            for k in i.nsItems.keys():
                c += self.optionalWrite( k , i.nsItems[ k ] )
            
            c += "</item>\n\n"
            
        return c


    def addNamespace( self, ns ):
        if ( self.channel.namespaces is not None ):
            self.channel.namespaces.append( ns )

    def addItem( self, item ):
        if ( self.channel is not None):
            self.channel.items.append( item )
            
            
    def optionalWrite( self, key, val ):
        if ( val is not None and val != "" ):
            return "<" + key + ">" + encode_for_xml(xml.sax.saxutils.escape(val)) + "</" + key + ">\n"
        else:
            return ""


#Namespace
class Namespace:
    def __init__( self, name, url ):
        self.url = url
        self.name = name

   
class Channel:
#    """
#    Channel
#    
#	(http://blogs.law.harvard.edu/tech/rss)
#	 
#	This object represents an RSS channel (as of ver2.0)
#    """

    def __init__( self ):
        #
        # Required Fields
        #
        self.title= None
        self.link= None
        self.description= None
        #
        #  Optional Fields
        #
        self.language = ""
        self.copyright = ""
        self.managingEditor = ""
        self.webMaster = ""
        self.pubDate = ""
        self.lastBuildDate = ""
        self.category = ""
        self.generator = ""
        self.docs = ""
        self.cloud = ""
        self.ttl = ""
        self.image = ""
        self.rating = ""
        self.textInput = ""
        self.skipHours = ""
        self.skipDays = ""
        
        self.items = []
        self.namespaces = []

    def initialized( self ):
        return self.title is not None and self.link is not None and self.description is not None
            
class Item:
#    """
#    Item
#     
#    http://blogs.law.harvard.edu/tech/rss#hrelementsOfLtitemgt
#     
#    A channel may contain any number of &lt;item&gt;s. An item may 
#    represent a "story" -- much like a story in a newspaper or magazine; 
#    if so its description is a synopsis of the story, and the link 
#    points to the full story. An item may also be complete in itself, 
#    if so, the description contains the text (entity-encoded HTML is 
#    allowed; see examples), and the link and title may be omitted. 
#    All elements of an item are optional, however at least one of 
#    title or description must be present.
#    """
    def __init__( self ):

        self.title = ""
        self.link = ""
        self.description = ""
        self.author = ""
        self.category = ""
        self.comments = ""
        self.enclosure = ""
        self.guid = ""
        self.pubDate = ""
        self.source = ""
        self.enclosure = Enclosure()
        
        self.nsItems = {}
        
        
class Enclosure:

#    """
#    Enclosure
#    
#    <enclosure> sub-element of <item> 
#
#    <enclosure> is an optional sub-element of <item>.
#
#    It has three required attributes:
#    
#        url:     says where the enclosure is located, 
#        length:  says how big it is in bytes, and 
#        type:    says what its type is, a standard MIME type.
#
#        The url must be an http url.
#
#    Example: <enclosure url="http://www.scripting.com/mp3s/weatherReportSuite.mp3" length="12216320" type="audio/mpeg" />
#    
#    """
    def __init__(self):
        self.url = ""
        self.length = 0
        self.type = ""
        
