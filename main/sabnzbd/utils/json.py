import string
import types

##    json.py implements a JSON (http://json.org) reader and writer.
##    Copyright (C) 2005  Patrick D. Logan
##    Contact mailto:patrickdlogan@stardecisions.com
##
##    This library is free software; you can redistribute it and/or
##    modify it under the terms of the GNU Lesser General Public
##    License as published by the Free Software Foundation; either
##    version 2.1 of the License, or (at your option) any later version.
##
##    This library is distributed in the hope that it will be useful,
##    but WITHOUT ANY WARRANTY; without even the implied warranty of
##    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
##    Lesser General Public License for more details.
##
##    You should have received a copy of the GNU Lesser General Public
##    License along with this library; if not, write to the Free Software
##    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

##    Remark by ShyPike: removed the decoding of JSON,
##                       because it's not used by SABnzbd+
##    The full source package can be obtained from:
##    http://sourceforge.net/projects/json-py

class WriteException(Exception):
    pass

class JsonWriter(object):
        
    def _append(self, s):
        self._results.append(s)

    def write(self, obj, escaped_forward_slash=False):
        self._escaped_forward_slash = escaped_forward_slash
        self._results = []
        self._write(obj)
        return "".join(self._results)

    def _write(self, obj):
        ty = type(obj)
        if ty is types.DictType:
            n = len(obj)
            self._append("{")
            for k, v in obj.items():
                self._write(k)
                self._append(":")
                self._write(v)
                n = n - 1
                if n > 0:
                    self._append(",")
            self._append("}")
        elif ty is types.ListType or ty is types.TupleType:
            n = len(obj)
            self._append("[")
            for item in obj:
                self._write(item)
                n = n - 1
                if n > 0:
                    self._append(",")
            self._append("]")
        elif ty is types.StringType or ty is types.UnicodeType:
            self._append('"')
	    obj = obj.replace('\\', r'\\')
            if self._escaped_forward_slash:
                obj = obj.replace('/', r'\/')
	    obj = obj.replace('"', r'\"')
	    obj = obj.replace('\b', r'\b')
	    obj = obj.replace('\f', r'\f')
	    obj = obj.replace('\n', r'\n')
	    obj = obj.replace('\r', r'\r')
	    obj = obj.replace('\t', r'\t')
            self._append(obj)
            self._append('"')
        elif ty is types.IntType or ty is types.LongType:
            self._append(str(obj))
        elif ty is types.FloatType:
            self._append("%f" % obj)
        elif obj is True:
            self._append("true")
        elif obj is False:
            self._append("false")
        elif obj is None:
            self._append("null")
        else:
            raise WriteException, "Cannot write in JSON: %s" % repr(obj)
