"""
    The guts that actually do the work. This is available here for the
    'qtfaststart' script and for your application's direct use.
"""

import shutil
import logging
import os
import struct
import collections

import io

from qtfaststart.exceptions import FastStartException

CHUNK_SIZE = 8192

log = logging.getLogger("qtfaststart")

# Older versions of Python require this to be defined
if not hasattr(os, 'SEEK_CUR'):
    os.SEEK_CUR = 1

Atom = collections.namedtuple('Atom', 'name position size')

def read_atom(datastream):
    """
        Read an atom and return a tuple of (size, type) where size is the size
        in bytes (including the 8 bytes already read) and type is a "fourcc"
        like "ftyp" or "moov".
    """
    size, type = struct.unpack(">L4s", datastream.read(8))
    type = type.decode('ascii')
    return size, type


def _read_atom_ex(datastream):
    """
    Read an Atom from datastream
    """
    pos = datastream.tell()
    atom_size, atom_type = read_atom(datastream)
    if atom_size == 1:
        atom_size, = struct.unpack(">Q", datastream.read(8))
    return Atom(atom_type, pos, atom_size)


def get_index(datastream):
    """
        Return an index of top level atoms, their absolute byte-position in the
        file and their size in a list:

        index = [
            ("ftyp", 0, 24),
            ("moov", 25, 2658),
            ("free", 2683, 8),
            ...
        ]

        The tuple elements will be in the order that they appear in the file.
    """
    log.debug("Getting index of top level atoms...")

    index = list(_read_atoms(datastream))
    _ensure_valid_index(index)

    return index


def _read_atoms(datastream):
    """
    Read atoms until an error occurs
    """
    while datastream:
        try:
            atom = _read_atom_ex(datastream)
            log.debug("%s: %s" % (atom.name, atom.size))
        except:
            break

        yield atom

        if atom.size == 0:
            if atom.name == "mdat":
                # Some files may end in mdat with no size set, which generally
                # means to seek to the end of the file. We can just stop indexing
                # as no more entries will be found!
                break
            else:
                # Weird, but just continue to try to find more atoms
                continue

        datastream.seek(atom.position + atom.size)


def _ensure_valid_index(index):
    """
    Ensure the minimum viable atoms are present in the index.

    Raise FastStartException if not.
    """
    top_level_atoms = set([item.name for item in index])
    for key in ["moov", "mdat"]:
        if key not in top_level_atoms:
            log.error("%s atom not found, is this a valid MOV/MP4 file?" % key)
            raise FastStartException()


def find_atoms(size, datastream):
    """
    Compatibilty interface for _find_atoms_ex
    """
    fake_parent = Atom('fake', datastream.tell()-8, size+8)
    for atom in _find_atoms_ex(fake_parent, datastream):
        yield atom.name


def _find_atoms_ex(parent_atom, datastream):
    """
        Yield either "stco" or "co64" Atoms from datastream.
        datastream will be 8 bytes into the stco or co64 atom when the value
        is yielded.

        It is assumed that datastream will be at the end of the atom after
        the value has been yielded and processed.

        parent_atom is the parent atom, a 'moov' or other ancestor of CO
        atoms in the datastream.
    """
    stop = parent_atom.position + parent_atom.size

    while datastream.tell() < stop:
        try:
            atom = _read_atom_ex(datastream)
        except:
            log.exception("Error reading next atom!")
            raise FastStartException()

        if atom.name in ["trak", "mdia", "minf", "stbl"]:
            # Known ancestor atom of stco or co64, search within it!
            for res in _find_atoms_ex(atom, datastream):
                yield res
        elif atom.name in ["stco", "co64"]:
            yield atom
        else:
            # Ignore this atom, seek to the end of it.
            datastream.seek(atom.position + atom.size)


def process(infilename, outfilename, limit=float('inf')):
    """
        Convert a Quicktime/MP4 file for streaming by moving the metadata to
        the front of the file. This method writes a new file.

        If limit is set to something other than zero it will be used as the
        number of bytes to write of the atoms following the moov atom. This
        is very useful to create a small sample of a file with full headers,
        which can then be used in bug reports and such.
    """
    datastream = open(infilename, "rb")

    # Get the top level atom index
    index = get_index(datastream)

    mdat_pos = 999999
    free_size = 0

    # Make sure moov occurs AFTER mdat, otherwise no need to run!
    for atom in index:
        # The atoms are guaranteed to exist from get_index above!
        if atom.name == "moov":
            moov_atom = atom
            moov_pos = atom.position
        elif atom.name == "mdat":
            mdat_pos = atom.position
        elif atom.name == "free" and atom.position < mdat_pos:
            # This free atom is before the mdat!
            free_size += atom.size
            log.info("Removing free atom at %d (%d bytes)" % (atom.position, atom.size))
        elif atom.name == "\x00\x00\x00\x00" and atom.position < mdat_pos:
            # This is some strange zero atom with incorrect size
            free_size += 8
            log.info("Removing strange zero atom at %s (8 bytes)" % atom.position)

    # Offset to shift positions
    offset = moov_atom.size - free_size

    if moov_pos < mdat_pos:
        # moov appears to be in the proper place, don't shift by moov size
        offset -= moov_atom.size
        if not free_size:
            # No free atoms and moov is correct, we are done!
            log.error("This file appears to already be setup for streaming!")
            raise FastStartException()

    # Read and fix moov
    moov = _patch_moov(datastream, moov_atom, offset)

    log.info("Writing output...")
    outfile = open(outfilename, "wb")

    # Write ftype
    for atom in index:
        if atom.name == "ftyp":
            log.debug("Writing ftyp... (%d bytes)" % atom.size)
            datastream.seek(atom.position)
            outfile.write(datastream.read(atom.size))

    # Write moov
    bytes = moov.getvalue()
    log.debug("Writing moov... (%d bytes)" % len(bytes))
    outfile.write(bytes)

    # Write the rest
    atoms = [item for item in index if item.name not in ["ftyp", "moov", "free"]]
    for atom in atoms:
        log.debug("Writing %s... (%d bytes)" % (atom.name, atom.size))
        datastream.seek(atom.position)

        # for compatability, allow '0' to mean no limit
        cur_limit = limit or float('inf')
        cur_limit = min(cur_limit, atom.size)

        for chunk in get_chunks(datastream, CHUNK_SIZE, cur_limit):
            outfile.write(chunk)

    # Close and set permissions
    outfile.close()
    try:
        shutil.copymode(infilename, outfilename)
    except:
        log.warn("Could not copy file permissions!")

def _patch_moov(datastream, atom, offset):
    datastream.seek(atom.position)
    moov = io.BytesIO(datastream.read(atom.size))

    # reload the atom from the fixed stream
    atom = _read_atom_ex(moov)

    for atom in _find_atoms_ex(atom, moov):
        # Read either 32-bit or 64-bit offsets
        ctype, csize = dict(
            stco=('L', 4),
            co64=('Q', 8),
        )[atom.name]

        # Get number of entries
        version, entry_count = struct.unpack(">2L", moov.read(8))

        log.info("Patching %s with %d entries" % (atom.name, entry_count))

        entries_pos = moov.tell()

        struct_fmt = ">%(entry_count)s%(ctype)s" % vars()

        # Read entries
        entries = struct.unpack(struct_fmt, moov.read(csize * entry_count))

        # Patch and write entries
        offset_entries = [entry + offset for entry in entries]
        moov.seek(entries_pos)
        moov.write(struct.pack(struct_fmt, *offset_entries))
    return moov

def get_chunks(stream, chunk_size, limit):
    remaining = limit
    while remaining:
        chunk = stream.read(min(remaining, chunk_size))
        if not chunk:
            return
        remaining -= len(chunk)
        yield chunk
