# Licensed under the GPLv3 - see LICENSE.rst
"""
Definitions for GSB Headers, using the timestamp files.

Somewhat out of data description for phased data:
http://gmrt.ncra.tifr.res.in/gmrt_hpage/sub_system/gmrt_gsb/GSB_beam_timestamp_note_v1.pdf
and for rawdump data
http://gmrt.ncra.tifr.res.in/gmrt_hpage/sub_system/gmrt_gsb/GSB_rawdump_data_format_v2.pdf
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import numpy as np
from astropy import units as u, _erfa as erfa
from astropy.time import Time, TimeString
from astropy.extern import six

from ..vlbi_base.header import VLBIHeaderBase, HeaderParser


__all__ = ['TimeGSB', 'GSBHeader', 'GSBRawdumpHeader', 'GSBPhasedHeader']


class TimeGSB(TimeString):
    """GSB header date-time format ``'YYYY MM DD HH MM SS 0.SSSSSS'``.

    For example, 2000 01 01 00 00 00 0.000000 is midnight on January 1, 2000.
    """
    # Implicitly uses the metaclass astropy.time.formats.TimeFormatMeta to
    # register with astropy.Time.

    name = 'gsb'

    def set_jds(self, val1, val2):
        """Parse the time strings contained in val1 and set jd1, jd2"""
        iterator = np.nditer([val1, None, None, None, None, None, None],
                             op_dtypes=([val1.dtype] + 5*[np.intc] +
                                        [np.double]))
        try:
            for val, iy, im, id, ihr, imin, dsec in iterator:
                timestr = val.item()
                components = timestr.split()
                iy[...], im[...], id[...], ihr[...], imin[...], sec = (
                    int(component) for component in components[:-1])
                dsec[...] = sec + float(components[-1])
        except Exception:
            raise ValueError('Time {0} does not match {1} format'
                             .format(timestr, self.name))

        self.jd1, self.jd2 = erfa.dtf2d(
            self.scale.upper().encode('utf8'), *iterator.operands[1:])

    def to_value(self, parent=None):
        scale = self.scale.upper().encode('ascii'),
        iys, ims, ids, ihmsfs = erfa.d2dtf(scale, self.precision,
                                           self.jd1, self.jd2)
        ihrs = ihmsfs[..., 0]
        imins = ihmsfs[..., 1]
        isecs = ihmsfs[..., 2]
        ifracs = ihmsfs[..., 3]

        fmt = ('{0:04d} {1:02d} {2:02d} {3:02d} {4:02d} {5:02d} 0.{6:0' +
               str(self.precision) + 'd}')
        outs = []
        for iy, im, id, ihr, imin, isec, ifracsec in np.nditer(
                [iys, ims, ids, ihrs, imins, isecs, ifracs]):
            outs.append(fmt.format(int(iy), int(im), int(id), int(ihr),
                                   int(imin), int(isec), int(ifracsec)))

        return np.array(outs).reshape(self.jd1.shape)

    value = property(to_value)


def make_parser(index, length, forward=None, backward=None, default=None):
    if length > 1:
        index = slice(index, index+length)

    def parser(items):
        return forward(items[index])

    return parser


def make_setter(index, length, forward, backward, default=None):
    def setter(items, value):
        value = backward(value)
        if length == 1:
            items[index] = value
        else:
            for i, val in enumerate(value):
                items[index + i] = val
        return items

    return setter


def get_default(index, length, forward, backward, default=None):
    return default


class GSBHeader(VLBIHeaderBase):
    """GSB Header, based on a line from a time-stamp file.

    Parameters
    ----------
    words : list of str, or None
        If ``None``, set to a list of empty strings for later initialisation.
    mode : str, or None
        Mode in which data was taken: 'phased' or 'rawdump'. If not given, it
        is determined from the words.
    size : int, or None
        Number of characters in the header, including trailing blank spaces and
        carriage returns.  If not given, is determined from the words assuming
        one trailing blank space and one CR.
    verify : bool
        Whether to do basic verification of integrity.  Default: `True`.

    Returns
    -------
    header : `GSBHeader` subclass
        As appropriate for the mode.
    """
    _mode = None
    _gsb_header_classes = {}

    def __new__(cls, words, mode=None, size=None, utc_offset=5.5*u.hr,
                verify=True):

        if mode is None:
            if words is None:
                raise TypeError("Cannot construct an empty GSB header without "
                                "knowing the mode.")
            mode = 'rawdump' if len(words) == 7 else 'phased'

        cls = cls._gsb_header_classes.get(mode)
        self = super(GSBHeader, cls).__new__(cls)
        # We intialise VDIFHeader subclasses, so their __init__ will be called.
        return self

    def __init__(self, words, mode=None, size=None, utc_offset=5.5*u.hr,
                 verify=True):
        if words is None:
            self.words = [''] * self._number_of_words
        else:
            self.words = words
        if size is not None:
            self._size = size
        if mode is not None:
            self._mode = mode
        self.utc_offset = utc_offset
        if verify:
            self.verify()

    def verify(self):
        assert self.mode == self.__class__._mode
        assert len(self.words) == self._number_of_words

    @property
    def mode(self):
        return self._mode

    @property
    def size(self):
        """Size of the header in characters.

        Assumes the string terminates in one blank space and one carriage
        return.
        """
        if self._size is None:
            self._size = len(' '.join(self.words)) + 2
        return self._size

    @classmethod
    def fromfile(cls, fh, *args, **kwargs):
        """Read GSB Header from a line from a timestamp file.

        Arguments are the same as for class initialisation.  The header
        constructed will be immutable.
        """
        start_pos = fh.tell()
        s = fh.readline()
        size = fh.tell() - start_pos
        return cls(tuple(s.split()), mode=None, size=size, *args, **kwargs)

    def tofile(self, fh):
        """Write GSB header as a line to the filehandle."""
        return fh.write(' '.join(self.words) + '\n')

    @classmethod
    def fromvalues(cls, mode=None, size=None, *args, **kwargs):
        if mode is None:
            if cls._mode is not None:
                mode = cls._mode
            else:
                if set(kwargs.keys()) & {'pc', 'pc_time',
                                         'seq_nr', 'mem_block'}:
                    mode = 'phased'
                else:
                    raise TypeError("Cannot construct a GSB header from "
                                    "values without knowing the mode.")
        return super(GSBHeader, cls).fromvalues(mode, size, *args, **kwargs)

    @classmethod
    def fromkeys(cls, mode=None, size=None, *args, **kwargs):
        if mode is None:
            if cls._mode is not None:
                mode = cls._mode
            else:
                if set(kwargs.keys()) & {'pc', 'seq_nr', 'mem_block'}:
                    mode = 'phased'
                else:
                    mode = 'rawdump'
        return super(GSBHeader, cls).fromkeys(mode, size, *args, **kwargs)

    def seek_offset(self, n, size=None):
        """Offset in bytes needed to move a file pointer to another header.

        Some GSB headers have variable size and hence one cannot trivially jump
        to another entry in a timestamp file.  This routine allows one to
        calculate the offset required to move the file pointer ``n`` headers.

        Parameters
        ----------
        n : int
            The number of headers to move to, relative to the present header.
        size : int, optional
            The size in bytes of the present header (if not given, will use
            the header's `size` property).
        """
        if size is None:
            size = self.size
        return n * size

    def __eq__(self, other):
        return (type(self) is type(other) and
                tuple(self.words) == tuple(other.words))


if six.PY2:  # pragma: py2
    def str_split(string):
        return str(string).split()
else:
    str_split = str.split


class GSBRawdumpHeader(GSBHeader):
    """GSB rawdump header."""

    _mode = 'rawdump'
    _number_of_words = 7
    _gps_time_precision = 9
    _properties = ('gps_time', 'time')

    _header_parser = HeaderParser(
        (('gps', (0, 7, ' '.join, str_split)),),
        make_parser=make_parser,
        make_setter=make_setter,
        get_default=get_default)

    @property
    def gps_time(self):
        return Time(self['gps'], format='gsb',
                    precision=self._gps_time_precision) - self.utc_offset

    @gps_time.setter
    def gps_time(self, time):
        t = time + self.utc_offset
        t.precision = self._gps_time_precision
        self['gps'] = t.gsb

    time = gps_time


class GSBPhasedHeader(GSBRawdumpHeader):
    """GSB phased header."""

    _mode = 'phased'
    _number_of_words = GSBRawdumpHeader._number_of_words + 7 + 2
    _pc_time_precision = 6
    _properties = ('time', 'pc_time') + GSBRawdumpHeader._properties

    _header_parser = HeaderParser(
        (('pc', (0, 7, ' '.join, str_split)),
         ('gps', (7, 7, ' '.join, str_split)),
         ('seq_nr', (14, 1, int, str, 1)),
         ('mem_block', (15, 1, int, str, 1))),
        make_parser=make_parser,
        make_setter=make_setter,
        get_default=get_default)

    @property
    def pc_time(self):
        return Time(self['pc'], format='gsb',
                    precision=self._pc_time_precision) - self.utc_offset

    @pc_time.setter
    def pc_time(self, time):
        t = time + self.utc_offset
        t.precision = self._pc_time_precision
        self['pc'] = t.gsb

    @property
    def time(self):
        return self.gps_time

    @time.setter
    def time(self, time):
        self.gps_time = time
        self.pc_time = time

    def seek_offset(self, n, size=None):
        """Offset in bytes needed to move a file pointer to another header.

        GSB headers for phased data differ in size depending on the sequence
        number, making it impossible to trivially jump to another entry in a
        timestamp file.  This routine allows one to calculate the offset
        required to move the file pointer ``n`` headers.

        Parameters
        ----------
        n : int
            The number of headers to move to, relative to the present header.
        size : int, optional
            The size in bytes of the present header (if not given, will use
            the header's `size` property).
        """
        if size is None:
            size = self.size
        # Initial guess assuming all headers have same size.
        guess = n * size
        # Get number of digits of current sequence number.
        seq = self['seq_nr']
        ndseq = len(str(seq))
        # Find the sequence number we're trying to reach.
        seq_sub_targ = seq + n
        # And get number of digits for this value.
        ndtarg = len(str(seq_sub_targ))
        # If numbers not the same, correct appropriately.
        while ndseq != ndtarg:
            if n > 0:
                next_power_of_ten = int('1' + ndseq * '0')
                guess += seq_sub_targ - next_power_of_ten
                ndseq += 1
            else:
                next_power_of_ten = int('1' + (ndseq - 1) * '0')
                guess += next_power_of_ten - seq_sub_targ
                ndseq -= 1

        return guess


GSBHeader._gsb_header_classes.update(rawdump=GSBRawdumpHeader,
                                     phased=GSBPhasedHeader)
