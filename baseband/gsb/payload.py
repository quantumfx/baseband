"""
Definitions for GSB payloads.

Implements a GSBPayload class used to store payload blocks, and decode to
or encode from a data array.

See http://gmrt.ncra.tifr.res.in/gmrt_hpage/sub_system/gmrt_gsb/index.htm
"""
from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import numpy as np

from ..vlbi_base.payload import VLBIPayloadBase


__all__ = ['GSBPayload']


shift40 = np.array([4, 0], np.int8)
shift04 = np.array([0, 4], np.int8)


def decode_4bit(words):
    """Decode 4-bit data.

    For a given int8 byte containing bits 76543210,
    the first sample is in 3210, the second in 7654, and both are interpreted
    as signed 4-bit integers.
    """
    b = words.view(np.int8)
    # left_shift(byte[:,np.newaxis], shift40):  [3210xxxx, 76543210]
    split = np.left_shift(b[:, np.newaxis], shift40).ravel()
    # right_shift(..., 4):                      [33333210, 77777654]
    # so least significant bits go first.
    split >>= 4
    return split.astype(np.float32)


def decode_8bit(words):
    """GSB decoder for data stored using 8 bit signed integer.
    """
    return words.view(np.int8).astype(np.float32)


def encode_4bit(values):
    b = np.clip(np.round(values), -8, 7).astype(np.int8).reshape(-1, 2)
    b &= 0xf
    b <<= shift04
    return b[:, 0] | b[:, 1]


def encode_8bit(values):
    return np.clip(np.rint(values), -128, 127).astype(np.int8)


class GSBPayload(VLBIPayloadBase):
    """Container for decoding and encoding GSB payloads.

    Parameters
    ----------
    words : ndarray
        Array containg LSB unsigned words (with the right size) that
        encode the payload.
    nchan : int
        Number of channels in the data.  Default: 1.
    bps : int
        Number of bits per sample part (i.e., per channel and per real or
        imaginary component).  Default: 2.
    complex_data : bool
        Whether data is complex or float.  Default: False.
    """

    _encoders = {4: encode_4bit,
                 8: encode_8bit}
    _decoders = {4: decode_4bit,
                 8: decode_8bit}
