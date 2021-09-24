"""
Copyright (c) 2018-2025 Nasir Khan (r0ot h3x49)

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the
Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, 
and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR
ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH 
THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

from __future__ import unicode_literals

import re
import six
import unicodedata
from unidecode import unidecode


def smart_text(s, encoding="utf-8", errors="strict"):
    if isinstance(s, six.text_type):
        return s

    if not isinstance(s, six.string_types):
        if six.PY3:
            if isinstance(s, bytes):
                s = six.text_type(s, encoding, errors)
            else:
                s = six.text_type(s)
        elif hasattr(s, "__unicode__"):
            s = six.text_type(s)
        else:
            s = six.text_type(bytes(s), encoding, errors)
    else:
        s = six.text_type(s)
    return s


# Extra characters outside of alphanumerics that we'll allow.
SLUG_OK = "-_~"


def slugify(s,
            ok=SLUG_OK,
            lower=True,
            spaces=False,
            only_ascii=False,
            space_replacement="_"):
    """
    Creates a unicode slug for given string with several options.
    L and N signify letter/number.
    http://www.unicode.org/reports/tr44/tr44-4.html#GC_Values_Table
    :param s: Your unicode string.
    :param ok: Extra characters outside of alphanumerics to be allowed.
               Default is '-_~'
    :param lower: Lower the output string. 
                  Default is True
    :param spaces: True allows spaces, False replaces a space with the "space_replacement" param
    :param only_ascii: True to replace non-ASCII unicode characters with 
                       their ASCII representations.
    :param space_replacement: Char used to replace spaces if "spaces" is False. 
                              Default is dash ("-") or first char in ok if dash not allowed
    :type s: String
    :type ok: String
    :type lower: Bool
    :type spaces: Bool
    :type only_ascii: Bool
    :type space_replacement: String
    :return: Slugified unicode string
    """

    if only_ascii and ok != SLUG_OK and hasattr(ok, "decode"):
        try:
            ok.decode("ascii")
        except UnicodeEncodeError:
            raise ValueError(
                ('You can not use "only_ascii=True" with '
                 'a non ascii available chars in "ok" ("%s" given)') % ok)

    rv = []
    for c in unicodedata.normalize("NFKC", smart_text(s)):
        cat = unicodedata.category(c)[0]
        if cat in "LN" or c in ok:
            rv.append(c)
        elif cat == "Z":  # space
            rv.append(" ")
    new = "".join(rv).strip()

    if only_ascii:
        new = unidecode(new)
    if not spaces:
        if space_replacement and space_replacement not in ok:
            space_replacement = ok[0] if ok else ""
        new = re.sub("[%s\s]+" % space_replacement, space_replacement, new)
    if lower:
        new = new.lower()

    return new


def sanitize(title):
    _locale = {
        "194": "A",
        "199": "C",
        "286": "G",
        "304": "I",
        "206": "I",
        "214": "O",
        "350": "S",
        "219": "U",
        "226": "a",
        "231": "c",
        "287": "g",
        "305": "i",
        "238": "i",
        "246": "o",
        "351": "s",
        "251": "u",
        "191": "",
        "225": "a",
        "233": "e",
        "237": "i",
        "243": "o",
        "250": "u",
        "252": "u",
        "168u": "u",
        "241": "n",
        "193": "A",
        "201": "E",
        "205": "I",
        "211": "O",
        "218": "U",
        "220": "U",
        "168U": "U",
        "209": "N",
        "223": "ss",
    }
    _temp = "".join([str(ord(i)) if ord(i) > 128 else i for i in title])
    for _ascii, _char in _locale.items():
        if _ascii in _temp:
            _temp = _temp.replace(_ascii, _char)

    ok = re.compile(r'[^\\/:*?"<>]')
    _title = "".join(x if ok.match(x) else "_" for x in _temp)
    return _title
