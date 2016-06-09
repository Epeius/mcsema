#!/usr/bin/env python
import binaryninja
import argparse
import os
import sys
import magic
import time
import CFG_pb2

_DEBUG = False

EXT_MAP = {}
EXT_DATA_MAP = {}

EXTERNAL_NAMES = [
    '@@GLIBC_',
]


def DEBUG(s):
    if _DEBUG:
        sys.stdout.write('{}\n'.format(str(s)))


def add_inst(pb_block, addr, inst_bytes):
    # type: (CFG_pb2.Block, int, str) -> CFG_pb2.Instruction
    pb_inst = pb_block.insts.add()
    pb_inst.inst_bytes = inst_bytes
    pb_inst.inst_addr = addr
    pb_inst.inst_len = len(inst_bytes)
    # TODO: optional fields

    return pb_inst


def add_block(pb_func, block):
    # type: (CFG_pb2.Function, binaryninja.LowLevelILBasicBlock) -> CFG_pb2.Block
    pb_block = pb_func.blocks.add()
    pb_block.base_address = block.start
    # TODO: block_follows

    return pb_block


def recover_function(bv, pb_mod, pb_func):
    # type: (binaryninja.BinaryView, CFG_pb2.Module, CFG_pb2.Function) -> None
    func = bv.get_function_at(bv.platform, pb_func.entry_address)  # type: binaryninja.Function

    for block in func.basic_blocks:
        pb_block = add_block(pb_func, block)
        idx = block.start
        while idx < block.end:
            inst_data = bv.read(idx, 16)
            inst_info = bv.arch.get_instruction_info(inst_data, idx)
            pb_inst = add_inst(pb_block, idx, inst_data[:inst_info.length])
            idx += inst_info.length


def add_function(pb_mod, addr):
    # type: (CFG_pb2.Module, int) -> CFG_pb2.Function
    pb_func = pb_mod.internal_funcs.add()
    pb_func.entry_address = addr
    return pb_func


def fix_external_name(name):
    # type: (str) -> str
    if name in EXT_MAP or name in EXT_DATA_MAP:
        return name

    # TODO: unlinked elf case

    if name.endswith('_0'):
        fixed = name[:-2]
        if fixed in EXT_MAP:
            return fixed

    if name.startswith('__imp_'):
        fixed = name[6:]
        if fixed in EXT_MAP:
            return fixed

    for extName in EXTERNAL_NAMES:
        if extName in name:
            name = name[:name.find(extName)]
            break
    return name


def in_ext_map(name):
    # type: (str) -> bool
    return fix_external_name(name) in EXT_MAP


def get_from_ext_map(name):
    # type: (str) -> (int, int, chr, str)
    return EXT_MAP[fix_external_name(name)]


def get_export_type(bv, name, addr):
    # type: (binaryninja.BinaryView, str, int) -> (int, int, chr)
    DEBUG('Processing export name: {} @ {:x}'.format(name, addr))
    if in_ext_map(name):
        DEBUG('Export found in std_defs')
        argc, conv, ret, sign = get_from_ext_map(name)
    else:
        ftype = bv.get_function_at(bv.platform, addr).type

        argc = len(ftype.parameters)
        ret = 'Y' if ftype.can_return else 'N'
        # TODO: conv
        conv = CFG_pb2.ExternalFunction.CalleeCleanup
    return argc, conv, ret


def process_entry_point(bv, pb_mod, name, addr):
    # type: (binaryninja.BinaryView, CFG_pb2.Module, str, int) -> CFG_pb2.Function
    # Create the entry point
    pb_entry = pb_mod.entries.add()
    pb_entry.entry_name = name
    pb_entry.entry_address = addr

    argc, conv, ret = get_export_type(bv, name, addr)

    # Add extra data
    pb_entry.entry_extra.entry_argc = argc
    pb_entry.entry_extra.entry_cconv = conv
    pb_entry.entry_extra.does_return = ret == 'Y'

    DEBUG('At EP {}:{:x}'.format(name, addr))

    pb_func = add_function(pb_mod, addr)
    return pb_func


def recover_cfg(bv, entries, outf):
    # type: (binaryninja.BinaryView, dict, file) -> None
    pb_mod = CFG_pb2.Module()
    pb_mod.module_name = bv.file.filename
    DEBUG('PROCESSING: {}'.format(pb_mod.module_name))

    # TODO: segment related processing (not in api)

    # Process the main entry points
    for fname, faddr in entries.iteritems():
        DEBUG('Recovering: {}'.format(fname))
        pb_func = process_entry_point(bv, pb_mod, fname, faddr)
        recover_function(bv, pb_mod, pb_func)

    outf.write(pb_mod.SerializeToString())
    outf.close()

    DEBUG('Saved to: {}'.format(outf.name))


def process_defs_file(f):
    # type: (file) -> None
    """ Load the std_defs data into the externals maps """
    lines = [l.strip() for l in f.readlines()]
    for l in lines:
        if len(l) == 0 or l[0] == '#':
            continue

        if l.startswith('DATA:'):
            # Process external data
            mark, dataname, datasize = l.split()
            EXT_DATA_MAP[dataname] = int(datasize)
        else:
            # Process external function
            data = l.split()
            funcname, argc, conv, ret = data[:4]
            sign = data[4] if len(data) == 5 else None

            # Get real calling convention
            if conv == 'C':
                realconv = CFG_pb2.ExternalFunction.CallerCleanup
            elif conv == 'E':
                realconv = CFG_pb2.ExternalFunction.CalleeCleanup
            elif conv == 'F':
                realconv = CFG_pb2.ExternalFunction.FastCall
            else:
                raise Exception('Unknown calling convention: {}'.format(conv))

            # Validate return type
            if ret not in ['Y', 'N']:
                raise Exception('Unknown return type: {}'.format(ret))

            EXT_MAP[funcname] = (int(argc), realconv, ret, sign)
    f.close()


def filter_entries(bv, symbols):
    # type: (binaryninja.BinaryView, list) -> dict
    """ Filters out any function symbols that are not in the binary """
    func_syms = [func.symbol.name for func in bv.functions]
    filtered = {}
    for symb in symbols:
        if symb in func_syms:
            filtered[symb] = bv.symbols[symb].address
        else:
            DEBUG('Could not find symbol "{}" in binary'.format(symb))
    return filtered


def get_all_exports(bv):
    # type: (binaryninja.BinaryView) -> dict
    # TODO: Find all exports (not in api)
    return {bv.entry_function.symbol.name: bv.entry_point}


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('--entry-symbol', nargs='*',
                        help='Symbols(s) to start disassembling from')

    parser.add_argument('-o', '--output',
                        default=None,
                        help='The output control flow graph recovered from this file')

    parser.add_argument('-d', '--debug', action='store_true',
                        help='Enable verbose debugging mode')

    parser.add_argument('-s', '--std-defs',
                        nargs='*', default=[],
                        type=argparse.FileType('r'),
                        help='std_defs file: definitions and calling conventions of imported functions and data')

    parser.add_argument('file', help='Binary to recover control flow graph from')

    args = parser.parse_args(sys.argv[1:])

    # Enable debugging
    if args.debug:
        global _DEBUG
        _DEBUG = True

    curpath = os.path.dirname(__file__)
    filepath = os.path.relpath(args.file, curpath)

    # Resolve path to output file
    if args.output:
        outpath = os.path.dirname(args.output)

        # Attempt to create directories to the output file
        try:
            os.mkdir(outpath)
        except OSError:
            pass

        outf = open(args.output, 'wb')
    else:
        # Default output file is "{filename}_binja.cfg"
        outf = open(os.path.join(curpath, filepath + "_binja.cfg"), 'wb')
        outpath = os.path.join(curpath, filepath)

    # Look at magic bytes to choose the right BinaryViewType
    magic_type = magic.from_file(os.path.join(curpath, filepath))
    if 'ELF' in magic_type:
        bv_type = binaryninja.BinaryViewType['ELF']
    elif 'PE32' in magic_type:
        bv_type = binaryninja.BinaryViewType['PE']
    elif 'Mach-O' in magic_type:
        bv_type = binaryninja.BinaryViewType['Mach-O']
    else:
        bv_type = binaryninja.BinaryViewType['Raw']
        # Don't think this can be used for anything, quitting for now
        DEBUG('Unknown binary type: "{}"'.format(magic_type))
        return

    # Load and analyze the binary
    bv = bv_type.open(filepath)
    bv.update_analysis()
    time.sleep(0.1)  # May need to be changed

    # NOTE: at the moment binja will not load a binary
    # that doesn't have an entry point
    if len(bv) == 0:
        DEBUG("Binary could not be loaded in binja, is it linked?")
        return

    # Load std_defs files
    if len(args.std_defs) > 0:
        for dfile in args.std_defs:
            DEBUG('Loading standard definitions file: {}'.format(dfile.name))
            process_defs_file(dfile)

    epoints = []
    # TODO: exports_to_lift file
    if args.entry_symbol:
        epoints = filter_entries(bv, args.entry_symbol)
    else:
        epoints = get_all_exports(bv)

    if len(epoints) == 0:
        DEBUG("Need to have at least one entry point to lift")
        return

    recover_cfg(bv, epoints, outf)


if __name__ == '__main__':
    main()
