#  2005/08/28
# v1.4.0
# listquote.py

# Lists 'n' Quotes
# Handling lists and quoted strings
# Can be used for parsing/creating lists - or lines in a CSV file
# And also quoting or unquoting elements.

# Homepage : http://www.voidspace.org.uk/python/modules.shtml

# Copyright Michael Foord, 2004 & 2005.
# Released subject to the BSD License
# Please see http://www.voidspace.org.uk/python/license.shtml

# For information about bugfixes, updates and support, please join the Pythonutils mailing list.
# http://groups.google.com/group/pythonutils/
# Comments, suggestions and bug reports welcome.
# Scripts maintained at http://www.voidspace.org.uk/python/index.shtml
# E-mail fuzzyman@voidspace.org.uk

"""
Having written modules to handle turning a string representation of a list back
into a list (including nested lists) and also a very simple CSV parser, I
realised I needed a more solid set of functions for handling lists (comma
delimited lines) and quoting/unquoting elements of lists.

The test stuff provides useful examples of how the functions work.
"""

# Pre-2.3 workaround for basestring.
try:
    basestring
except NameError:
    basestring = (str, unicode)

import re
inquotes = re.compile(r'''\s*(".*?"|'.*?')(.*)''')
badchars = re.compile(r'''^[^'," \[\]\(\)#]+$''')
##commented_line = re.compile(r'''\s*([^#]*)\s*(#.*)''')
paramfinder = re.compile(r'''(?:'.*?')|(?:".*?")|(?:[^'",\s][^,]*)''')
unquoted = re.compile(r'''
    ([^\#,"'\(\)\[\]][^\#,\]\)]*)  # value
    \s*                         # whitespace - XXX not caught
    ([\#,\)\]].*)?                  # rest of the line
    $''', re.VERBOSE)

__all__ = [
    'elem_quote',
    'unquote',
    'ListQuoteError',
    'QuoteError',
    'UnQuoteError',
    'BadLineError',
    'CommentError',
    'quote_escape',
    'quote_unescape',
    'simplelist',
    'LineParser',
    'lineparse',
    'csvread',
    'csvwrite',
    'list_stringify',
    'makelist'
    ]

class ListQuoteError(SyntaxError):
    """Base class for errors raised by the listquote module."""

class QuoteError(ListQuoteError):
    """This value can't be quoted."""

class UnQuoteError(ListQuoteError):
    """The value is badly quoted."""

class BadLineError(ListQuoteError):
    """A line is badly built."""

class CommentError(BadLineError):
    """A line contains a disallowed comment."""

class CSVError(ListQuoteError):
    """The CSV File contained errors."""

#################################################################
# functions for quoting and unquoting

def elem_quote(member, nonquote=True, stringify=False, encoding=None):
    """
    Simple method to add the most appropriate quote to an element - either single
    quotes or double quotes.

    If member contains ``\n`` a ``QuoteError`` is raised - multiline values
    can't be quoted by elem_quote.

    If ``nonquote`` is set to ``True`` (the default), then if member contains none
    of ``'," []()#;`` then it isn't quoted at all.

    If member contains both single quotes *and* double quotes then all double
    quotes (``"``) will be escaped as ``&mjf-quot;`` and member will then be quoted
    with double quotes.

    If ``stringify`` is set to ``True`` (the default is ``False``) then non string
    (unicode or byte-string) values will be first converted to strings using the
    ``str`` function. Otherwise elem_quote raises a ``TypeError``.

    If ``encoding`` is not ``None`` and member is a byte string, then it will be
    decoded into unicode using this encoding.

    >>> elem_quote('hello')
    'hello'
    >>> elem_quote('hello', nonquote=False)
    '"hello"'
    >>> elem_quote('"hello"')
    '\\'"hello"\\''
    >>> elem_quote(3)
    Traceback (most recent call last):
    TypeError: Can only quote strings. "3"
    >>> elem_quote(3, stringify=True)
    '3'
    >>> elem_quote('hello', encoding='ascii')
    u'hello'
    >>> elem_quote('\\n')
    Traceback (most recent call last):
    QuoteError: Multiline values can't be quoted.
    "
    "
    """
    if not isinstance(member, basestring):
        if stringify:
            member = str(member)
        else:
            # FIXME: is this the appropriate error message ?
            raise TypeError('Can only quote strings. "%s"' % str(member))
    if encoding and isinstance(member, str):
        # from string to unicode
        member = unicode(member, encoding)
    if '\n' in member:
        raise QuoteError('Multiline values can\'t be quoted.\n"%s"' % str(member))
    #
    if nonquote and badchars.match(member) is not None:
        return member
    # this ordering of tests determines which quote character will be used in
    # preference - here we have \" first...
    elif member.find('"') == -1:
        return '"%s"' % member
    # but we will use either... which may not suit some people
    elif member.find("'") == -1:
        return "'%s'" % member
    else:
        raise QuoteError('Value can\'t be quoted : "%s"' % member)

def unquote(inline, fullquote=True, retain=False):
    """
    Unquote a value.

    If the value isn't quoted it returns the value.

    If the value is badly quoted it raises ``UnQuoteError``.

    If retain is ``True`` (default is ``False``) then the quotes are left
    around the value (but leading or trailing whitespace will have been
    removed).

    If fullquote is ``False`` (default is ``True``) then unquote will only
    unquote the first part of the ``inline``. If there is anything after the
    quoted element, this will be returned as well (instead of raising an
    error).

    In this case the return value is ``(value, rest)``.

    >>> unquote('hello')
    'hello'
    >>> unquote('"hello"')
    'hello'
    >>> unquote('"hello')
    Traceback (most recent call last):
    UnQuoteError: Value is badly quoted: ""hello"
    >>> unquote('"hello" fish')
    Traceback (most recent call last):
    UnQuoteError: Value is badly quoted: ""hello" fish"
    >>> unquote("'hello'", retain=True)
    "'hello'"
    >>> unquote('"hello" fish', fullquote=False)
    ('hello', ' fish')
    """
    mat = inquotes.match(inline)
    if mat is None:
        if inline.strip()[0] not in '\'\"': # not quoted
            return inline
        else:
            # badly quoted
            raise UnQuoteError('Value is badly quoted: "%s"' % inline)
    quoted, rest = mat.groups()
    if fullquote and rest.strip():
        # badly quoted
        raise UnQuoteError('Value is badly quoted: "%s"' % inline)
    if not retain:
        quoted = quoted[1:-1]
    if not fullquote:
        return quoted, rest
    else:
        return quoted

def quote_escape(value, lf='&mjf-lf;', quot='&mjf-quot;'):
    """
    Escape a string so that it can safely be quoted. You should use this if the
    value to be quoted *may* contain line-feeds or both single quotes and double
    quotes.

    If the value contains ``\n`` then it will be escaped using ``lf``. By
    default this is ``&mjf-lf;``.

    If the value contains single quotes *and* double quotes, then all double
    quotes will be escaped using ``quot``. By default this is ``&mjf-quot;``.

    >>> quote_escape('hello')
    'hello'
    >>> quote_escape('hello\\n')
    'hello&mjf-lf;'
    >>> quote_escape('hello"')
    'hello"'
    >>> quote_escape('hello"\\'')
    "hello&mjf-quot;'"
    >>> quote_escape('hello"\\'\\n', '&fish;', '&wobble;')
    "hello&wobble;'&fish;"
    """
    if '\n' in value:
        value = value.replace('\n', lf)
    if '\'' in value and '\"' in value:
        value = value.replace('"', quot)
    return value

def quote_unescape(value, lf='&mjf-lf;', quot='&mjf-quot;'):
    """
    Unescape a string escaped by ``quote_escape``.

    If it was escaped using anything other than the defaults for ``lf`` and
    ``quot`` you must pass them to this function.

    >>> quote_unescape("hello&wobble;'&fish;",  '&fish;', '&wobble;')
    'hello"\\'\\n'
    >>> quote_unescape('hello')
    'hello'
    >>> quote_unescape('hello&mjf-lf;')
    'hello\\n'
    >>> quote_unescape("'hello'")
    "'hello'"
    >>> quote_unescape('hello"')
    'hello"'
    >>> quote_unescape("hello&mjf-quot;'")
    'hello"\\''
    >>> quote_unescape("hello&wobble;'&fish;",  '&fish;', '&wobble;')
    'hello"\\'\\n'
    """
    return value.replace(lf, '\n').replace(quot, '"')

def simplelist(inline):
    """
    Parse a string to a list.

    A simple regex that extracts quoted items from a list.

    It retains quotes around elements. (So unquote each element)

    >>> simplelist('''hello, goodbye, 'title', "name", "I can't"''')
    ['hello', 'goodbye', "'title'", '"name"', '"I can\\'t"']

    FIXME:  This doesn't work fully (allows some badly formed lists):
    e.g.
    >>> simplelist('hello, fish, "wobble" bottom hooray')
    ['hello', 'fish', '"wobble"', 'bottom hooray']
    """
    return paramfinder.findall(inline)

##############################################
# LineParser - a multi purpose line parser
# handles lines with comma separated values on it, followed by a comment
# correctly handles quoting
# *and* can handle nested lists - marked between '[...]' or '(...)'
# See the docstring for how this works
# by default it returns a (list, comment) tuple !
# There are several keyword arguments that control how LineParser works.

class LineParser(object):
    """An object to parse nested lists from strings."""

    liststart = { '[' : ']', '(' : ')' }
    quotes = ['\'', '"']

    def __init__(self, options=None, **keywargs):
        """Initialise the LineParser."""
        self.reset(options, **keywargs)

    def reset(self, options=None, **keywargs):
        """Reset the parser with the specified options."""
        if options is None:
            options = {}
        options.update(keywargs)
        #
        defaults = {
                    'recursive': True,
                    'comment': True,
                    'retain': False,
                    'force_list': False,
                    'csv': False
                    }
        defaults.update(options)
        if defaults['csv']:
            defaults.update({
                        'recursive': False,
                        'force_list': True,
                        'comment': False,
                        })
        # check all the options are valid
        for entry in defaults.keys():
            if entry not in ['comment',
                            'retain',
                            'csv',
                            'recursive',
                            'force_list']:
                raise TypeError, ("'%s' is an invalid keyword argument for "
                                    "this function" % entry)
        #
        self.recursive = defaults['recursive']
        self.comment = defaults['comment']
        self.retain = defaults['retain']
        self.force_list = defaults['force_list']

    def feed(self, inline, endchar=None):
        """
        Parse a single line (or fragment).

        Uses the options set in the parser object.

        Can parse lists - including nested lists. (If ``recursive`` is
        ``False`` then nested lists will cause a ``BadLineError``).

        Return value depends on options.

        If ``comment`` is ``False`` it returns ``outvalue``

        If ``comment`` is ``True`` it returns ``(outvalue, comment)``. (Even if
        comment is just ``''``).

        If ``force_list`` is ``False`` then ``outvalue`` may be a list or a
        single item.

        If ``force_list`` is ``True`` then ``outvalue`` will always be a list -
        even if it has just one member.

        List syntax :

        * Comma separated lines ``a, b, c, d``
        * Lists can optionally be between square or ordinary brackets
            - ``[a, b, c, d]``
            - ``(a, b, c, d)``
        * Nested lists *must* be between brackets -  ``a, [a, b, c, d], c``
        * A single element list can be shown by a trailing quote - ``a,``
        * An empty list is shown by ``()`` or ``[]``

        Elements can be quoted with single or double quotes (but can't contain
        both).

        The line can optionally end with a comment (preeded by a '#').
        This depends on the ``comment`` attribute.

        If the line is badly built then this method will raise one of : ::

            CommentError, BadLineError, UnQuoteError

        Using the ``csv`` option is the same as setting : ::

                        'recursive': False
                        'force_list': True
                        'comment': False
        """
        # preserve the original line
        # for error messages
        if endchar is None:
            self.origline = inline
        inline = inline.lstrip()
        #
        outlist = []
        comma_needed = False
        found_comma = False
        while inline:
            # NOTE: this sort of operation would be quicker
            # with lists - but then can't use regexes
            thischar = inline[0]
            if thischar == '#':
                # reached a comment
                # end of the line...
                break
            #
            if thischar == endchar:
                return outlist, inline[1:]
            #
            if comma_needed:
                if thischar == ',':
                    inline = inline[1:].lstrip()
                    comma_needed = False
                    found_comma = True
                    continue
                raise BadLineError('Line is badly built :\n%s' % self.origline)
            #
            try:
                # the character that marks the end of the list
                listend = self.liststart[thischar]
            except KeyError:
                pass
            else:
                if not self.recursive and endchar is not None:
                    raise BadLineError('Line is badly built :\n%s' % self.origline)
                newlist, inline = self.feed(inline[1:], endchar=listend)
                outlist.append(newlist)
                inline = inline.lstrip()
                comma_needed = True
                continue
            #
            if thischar in self.quotes:
                # this might raise an error
                # FIXME: trap the error and raise a more appropriate one ?
                element, inline = unquote(inline, fullquote=False,
                                                    retain=self.retain)
                inline = inline.lstrip()
                outlist.append(element)
                comma_needed = True
                continue
            #
            # must be an unquoted element
            mat = unquoted.match(inline)
            if mat is not None:
                # FIXME: if the regex was better we wouldn't need an rstrip
                element = mat.group(1).rstrip()
                # group 2 will be ``None`` if we reach the end of the line
                inline = mat.group(2) or ''
                outlist.append(element)
                comma_needed = True
                continue
            # or it's a badly built line
            raise BadLineError('Line is badly built :\n%s' % self.origline)
        #
        # if we've been called recursively
        # we shouldn't have got this far
        if endchar is not None:
            raise BadLineError('Line is badly built :\n%s' % self.origline)
        #
        if not found_comma:
            # if we didn't find a comma
            # the value could be a nested list
            if outlist:
                outlist = outlist[0]
            else:
                outlist = ''
        if self.force_list and not isinstance(outlist, list):
            if outlist:
                outlist = [outlist]
            else:
                outlist = []
        if not self.comment:
            if inline:
                raise CommentError('Comment not allowed :\n%s' % self.origline)
            return outlist
        return outlist, inline

def lineparse(inline, options=None, **keywargs):
    """
    A compatibility function that mimics the old lineparse.

    Also more convenient for single line use.

    Note: It still uses the new ``LineParser`` - and so takes the same
    keyword arguments as that.

    >>> lineparse('''"hello", 'goodbye', "I can't do that", 'You "can" !' # a comment''')
    (['hello', 'goodbye', "I can't do that", 'You "can" !'], '# a comment')
    >>> lineparse('''"hello", 'goodbye', "I can't do that", 'You "can" !' # a comment''', comment=False)
    Traceback (most recent call last):
    CommentError: Comment not allowed :
    "hello", 'goodbye', "I can't do that", 'You "can" !' # a comment
    >>> lineparse('''"hello", 'goodbye', "I can't do that", 'You "can" !' # a comment''', recursive=False)
    (['hello', 'goodbye', "I can't do that", 'You "can" !'], '# a comment')
    >>> lineparse('''"hello", 'goodbye', "I can't do that", 'You "can" !' # a comment''', csv=True)
    Traceback (most recent call last):
    CommentError: Comment not allowed :
    "hello", 'goodbye', "I can't do that", 'You "can" !' # a comment
    >>> lineparse('''"hello", 'goodbye', "I can't do that", 'You "can" !' ''', comment=False)
    ['hello', 'goodbye', "I can't do that", 'You "can" !']
    >>> lineparse('')
    ('', '')
    >>> lineparse('', force_list=True)
    ([], '')
    >>> lineparse('[]')
    ([], '')
    >>> lineparse('()')
    ([], '')
    >>> lineparse('()', force_list=True)
    ([], '')
    >>> lineparse('1,')
    (['1'], '')
    >>> lineparse('"Yo"')
    ('Yo', '')
    >>> lineparse('"Yo"', force_list=True)
    (['Yo'], '')
    >>> lineparse('''h, i, j, (h, i, ['hello', "f"], [], ([]),), k''')
    (['h', 'i', 'j', ['h', 'i', ['hello', 'f'], [], [[]]], 'k'], '')
    >>> lineparse('''h, i, j, (h, i, ['hello', "f"], [], ([]),), k''', recursive=False)
    Traceback (most recent call last):
    BadLineError: Line is badly built :
    h, i, j, (h, i, ['hello', "f"], [], ([]),), k
    >>> lineparse('fish#dog')
    ('fish', '#dog')
    >>> lineparse('"fish"#dog')
    ('fish', '#dog')
    >>> lineparse('(((())))')
    ([[[[]]]], '')
    >>> lineparse('((((,))))')
    Traceback (most recent call last):
    BadLineError: Line is badly built :
    ((((,))))
    >>> lineparse('hi, ()')
    (['hi', []], '')
    >>> lineparse('"hello", "",')
    (['hello', ''], '')
    >>> lineparse('"hello", ,')
    Traceback (most recent call last):
    BadLineError: Line is badly built :
    "hello", ,
    >>> lineparse('"hello", ["hi", ""], ""')
    (['hello', ['hi', ''], ''], '')
    >>> lineparse('''"member 1", "member 2", ["nest 1", ("nest 2", 'nest 2b', ['nest 3', 'value'], nest 2c), nest1b]''')
    (['member 1', 'member 2', ['nest 1', ['nest 2', 'nest 2b', ['nest 3', 'value'], 'nest 2c'], 'nest1b']], '')
    >>> lineparse('''"member 1", "member 2", ["nest 1", ("nest 2", 'nest 2b', ['nest 3', 'value'], nest 2c), nest1b]]''')
    Traceback (most recent call last):
    BadLineError: Line is badly built :
    "member 1", "member 2", ["nest 1", ("nest 2", 'nest 2b', ['nest 3', 'value'], nest 2c), nest1b]]
    """
    p = LineParser(options, **keywargs)
    return p.feed(inline)

############################################################################
# a couple of functions to help build lists

def list_stringify(inlist):
    """
    Recursively rebuilds a list - making sure all the members are strings.

    Can take any iterable or a sequence as the argument and always
    returns a list.

    Useful before writing out lists.

    Used by makelist if stringify is set.

    Uses the ``str`` function for stringification.

    Every element will be a string or a unicode object.

    Doesn't handle decoding strings into unicode objects (or vice-versa).

    >>> list_stringify([2, 2, 2, 2, (3, 3, 2.9)])
    ['2', '2', '2', '2', ['3', '3', '2.9']]
    >>> list_stringify(None)
    Traceback (most recent call last):
    TypeError: 'NoneType' object is not iterable
    >>> list_stringify([])
    []

    FIXME: can receive any iterable - e.g. a sequence
    >>> list_stringify('')
    []
    >>> list_stringify('Hello There')
    ['H', 'e', 'l', 'l', 'o', ' ', 'T', 'h', 'e', 'r', 'e']
    """
    outlist = []
    for item in inlist:
        if not isinstance(item, (tuple, list)):
            if not isinstance(item, basestring):
                item = str(item)
        else:
            item = list_stringify(item)
        outlist.append(item)
    return outlist


def makelist(inlist, listchar='', stringify=False, escape=False, encoding=None):
    """
    Given a list - turn it into a string that represents that list. (Suitable
    for parsing by ``LineParser``).

    listchar should be ``'['``, ``'('`` or ``''``. This is the type of bracket
    used to enclose the list. (``''`` meaning no bracket of course).

    If you have nested lists and listchar is ``''``, makelist will
    automatically use ``'['`` for the nested lists.

    If stringify is ``True`` (default is ``False``) makelist will stringify the
    inlist first (using ``list_stringify``).

    If ``escape`` is ``True`` (default is ``False``) makelist will call
    ``quote_escape`` on each element before passing them to ``elem_quote`` to
    be quoted.

    If encoding keyword is not ``None``, all strings are decoded to unicode
    with the specified encoding. Each item will then be a unicode object
    instead of a string.

    >>> makelist([])
    '[]'
    >>> makelist(['a', 'b', 'I can\\'t do it', 'Yes you "can" !'])
    'a, b, "I can\\'t do it", \\'Yes you "can" !\\''
    >>> makelist([3, 4, 5, [6, 7, 8]], stringify=True)
    '3, 4, 5, [6, 7, 8]'
    >>> makelist([3, 4, 5, [6, 7, 8]])
    Traceback (most recent call last):
    TypeError: Can only quote strings. "3"
    >>> makelist(['a', 'b', 'c', ('d', 'e'), ('f', 'g')], listchar='(')
    '(a, b, c, (d, e), (f, g))'
    >>> makelist(['hi\\n', 'Quote "heck\\''], escape=True)
    'hi&mjf-lf;, "Quote &mjf-quot;heck\\'"'
    >>> makelist(['a', 'b', 'c', ('d', 'e'), ('f', 'g')], encoding='UTF8')
    u'a, b, c, [d, e], [f, g]'
    """
    if stringify:
        inlist = list_stringify(inlist)
    listdict = {'[' : '[%s]', '(' : '(%s)', '' : '%s'}
    outline = []
    # this makes '[' the default for empty or single value lists
    if len(inlist) < 2:
        listchar = listchar or '['
    for item in inlist:
        if not isinstance(item, (list, tuple)):
            if escape:
                item = quote_escape(item)
            outline.append(elem_quote(item, encoding=encoding))
        else:
            # recursive for nested lists
            outline.append(makelist(item, listchar or '[',
                                        stringify, escape, encoding))
    return listdict[listchar] % (', '.join(outline))

############################################################################
# CSV functions
# csvread, csvwrite

def csvread(infile):
    """
    Given an infile as an iterable, return the CSV as a list of lists.

    infile can be an open file object or a list of lines.

    If any of the lines are badly built then a ``CSVError`` will be raised.
    This has a ``csv`` attribute - which is a reference to the parsed CSV.
    Every line that couldn't be parsed will have ``[]`` for it's entry.

    The error *also* has an ``errors`` attribute. This is a list of all the
    errors raised. Error in this will have an ``index`` attribute, which is the
    line number, and a ``line`` attribute - which is the actual line that
    caused the error.

    Example of usage :

    .. raw:: html

        {+coloring}

        handle = open(filename)
        # remove the trailing '\n' from each line
        the_file = [line.rstrip('\n') for line in handle.readlines()]
        csv = csvread(the_file)

        {-coloring}

    >>> a = '''"object 1", 'object 2', object 3
    ...     test 1 , "test 2" ,'test 3'
    ...     'obj 1',obj 2,"obj 3"'''
    >>> csvread(a.splitlines())
    [['object 1', 'object 2', 'object 3'], ['test 1', 'test 2', 'test 3'], ['obj 1', 'obj 2', 'obj 3']]
    >>> csvread(['object 1,'])
    [['object 1']]
    >>> try:
    ...     csvread(['object 1, "hello', 'object 1, # a comment in a csv ?'])
    ... except CSVError, e:
    ...     for entry in e.errors:
    ...         print entry.index, entry
    0 Value is badly quoted: ""hello"
    1 Comment not allowed :
    object 1, # a comment in a csv ?
    """
    out_csv = []
    errors = []
    index = -1
    p = LineParser(csv=True)
    for line in infile:
        index += 1
        try:
            values = p.feed(line)
        except ListQuoteError, e:
            values = []
            e.line = line
            e.index = index
            errors.append(e)
        #
        out_csv.append(values)
    #
    if errors:
        e = CSVError("Parsing CSV failed. See 'errors' attribute.")
        e.csv = out_csv
        e.errors = errors
        raise e
    return out_csv

def csvwrite(inlist, stringify=False):
    """
    Given a list of lists it turns each entry into a line in a CSV.
    (Given a list of lists it returns a list of strings).

    The lines will *not* be ``\n`` terminated.

    Set stringify to ``True`` (default is ``False``) to convert entries to
    strings before creating the line.

    If stringify is ``False`` then any non string value will raise a
    ``TypeError``.

    Every member will be quoted using ``elem_quote``, but no escaping is done.

    Example of usage :

    .. raw:: html

        {+coloring}

        # escape each entry in each line (optional)
        for index in range(len(the_list)):
            the_list[index] = [quote_escape(val) for val in the_list[index]]
        #
        the_file = csvwrite(the_list)
        # add a '\n' to each line - ready to write to file
        the_file = [line + '\n' for line in the_file]

        {-coloring}

    >>> csvwrite([['object 1', 'object 2', 'object 3'], ['test 1', 'test 2', 'test 3'], ['obj 1', 'obj 2', 'obj 3']])
    ['"object 1", "object 2", "object 3"', '"test 1", "test 2", "test 3"', '"obj 1", "obj 2", "obj 3"']
    >>> csvwrite([[3, 3, 3]])
    Traceback (most recent call last):
    TypeError: Can only quote strings. "3"
    >>> csvwrite([[3, 3, 3]], True)
    ['3, 3, 3']
    """
    out_list = []
    for entry in inlist:
        if stringify:
            new_entry = []
            for val in entry:
                if not isinstance(val, basestring):
                    val = str(val)
                new_entry.append(val)
            entry = new_entry
        this_line = ', '.join([elem_quote(val) for val in entry])
        out_list.append(this_line)
    return out_list

############################################################################

def _test():
    import doctest
    doctest.testmod()

if __name__ == "__main__":
    _test()


"""
ISSUES/TODO
===========

Fix bug in simplelist

Triple quote multiline values ?

Doesn't allow Python style string escaping (but has '&mjf-quot;' and '&mjf-lf;').

Uses both \' and \" as quotes and sometimes doesn't quote at all - see
elem_quote - may not *always* be compatible with other programs.

Allow space separated lists ? e.g. 10 5 100 20

Lineparser could create tuples.

Allow ',' as an empty list ?

CHANGELOG
=========

2005/08/28 - Version 1.4.0
--------------------------

* Greater use of regular expressions for added speed
* Re-implemented ``lineparse`` as the ``LineParser`` object
* Added doctests
* Custom exceptions
* Changed the behaviour of ``csvread`` and ``csvwrite``
* Removed the CSV ``compare`` function and the ``uncomment`` function
* Only ``'#'`` allowed for comments
* ``elem_quote`` raises exceptions
* Changed behaviour of ``unquote``
* Added ``quote_escape`` and ``quote_unescape``
* Removed the ``uni_conv`` option in the CSV functions

.. note::

    These changes are quite extensive. If any of them cause you problems then
    let me know. I can provide a workaround in the next release.

2005/06/01          Version 1.3.0
Fixed bug in lineparse handling of empty list members.
    Thnks to bug report and fix by Par Pandit <ppandit@yahoo.com>
The 'unquote' function is now regex based.
    (bugfix it now doesn't return a tuple if fullquote is 0)
Added the simplelist regex/function.
elem_quote and uncomment use a regex for clarity and speed.
Added a bunch of asserts to the tests.

2005/03/07          Version 1.2.1
makelist improved - better handling of empty or single member lists

2005/02/23          Version 1.2.0
Added uncomment for ConfigObj 3.3.0
Optimised unquote - not a character by character search any more.
lineparse does full '&mjf..;' escape conversions - even when unquote isn't used
makelist and elem_quote takes an 'encoding' keyword for string members to be used to decode strigns to unicode
optimised makelist (including a minor bugfix)
Change to lineparse - it wouldn't allow '[' or '(' inside elements unless they were quoted.

2004/12/04          Version 1.1.2
Changed the license (*again* - now OSI compatible).
Empty values are now quoted by elem_quote.

30-08-04            Version 1.1.1
Removed the unicode hammer in csvread.
Improved docs.

16-08-04            Version 1.1.0
Added handling for non-string elements in elem_quote (optional).
Replaced some old += with lists and ''.join() for speed improvements...
Using basestring and hasattr('__getitem__') tests instead of isinstance(list) and str in a couple of places.
Changed license text.
Made the tests useful.

19-06-04            Version 1.0.0
Seems to work ok. A worthy successor to listparse and csv_s - although not as elegant as it could be.

"""
