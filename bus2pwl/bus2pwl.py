# (C) Dan White <dan@whiteaudio.com>

# Imports for Python 2 compatibility
from __future__ import print_function, with_statement

import argparse
import os
import re
import sys

from decimal import Decimal


# TODO:
# - allow comments in input file
# - passthru (header) comments
# - system info + datetime in output header


def info(s):
    if args.verbose:
        print('INFO:', s)

def error(s):
    print('ERROR:', s)
    sys.exit(1)


def warn(s):
    print('WARNING:', s)


# expand_bus:
# Expands signals that are specified as buses using square brackets (e.g.
# data[7:0]) into individual nodes. Returns a list of nodes given a correctly
# formatted string containing a signal bus
def expand_bus(signal):
    nodes = [] # Init empty list for nodes

    # parse into:  name[left:right]suffix
    name, lbrack, tail = signal.partition('[')
    left, colon, end = tail.partition(':')
    right, rbrack, suffix = end.partition(']')

    # only expand a complete bus - force users to be specific instead of
    # assuming what they wanted and giving them bogus results
    if lbrack and colon and rbrack:
        if (not name):
            error("No bus name for signal: %s. Did you add a space?" % signal)

        try:
            start = int(left)
            stop = int(right)
        except ValueError:
            if args.permissive:
                warn('Bad bus range: Start: %s Stop: %s Passing through as wire' % (left, right))
                nodes.append(signal)
            else:
                error('Bad bus range: Start: %s Stop: %s Passing through as wire' % (left, right))
        else:
            inc = 1 if (stop > start) else -1 # [4:0] or [0:4)
            signal_bus = range(start, (stop + inc), inc)

            for wire in signal_bus:
                single_signal = '%s[%i]%s' % (name, wire, suffix)
                nodes.append(single_signal)

    elif args.permissive:
        # If the user has specified they would like signal definitions to be
        # 'permissive', we'll just pass the improperly specified signal through
        # as a single wire.
        # We will use 'name' as the name of the new signal - we know that the
        # first partition _had_ to work because the presence of '[' was
        # what got us to this function in the first place.
        if (name):
            warn('Improperly specified bus: %s. Passing through.' % signal)
            nodes.append(name)
        else:
            error("No bus name for signal: %s. Did you add a space?" % signal)

    else:
        # Partial bus notation - error
        error("Improperly specified bus signal: %s" % signal)

    return nodes



def generate_waveform(d):
    t = Decimal('0.0')

    #first bit interval starts at t=0, start from this value
    lastbit = d[0]
    bitv = Decimal(lastbit) * (bithigh - bitlow) + bitlow
    s = '+ 0 %s' % str(bitv)
    output(s)

    trf = risefall
    tb = bittime - risefall
    t += trf + tb
    for bit in d[1:]:
        # only output a point when there is a change
        if bit != lastbit:
            ti = t + trf
            tf = ti + tb
            lastbitv = Decimal(lastbit) * (bithigh - bitlow) + bitlow
            bitv = Decimal(bit) * (bithigh - bitlow) + bitlow
            output('+ %s %s' % (str(t), str(lastbitv)))
            output('+ %s %s' % (str(ti), str(bitv)))
            #output('+ %s %s' % (str(tf), str(bitv)))

        t += trf + tb
        lastbit = bit



RE_UNIT = re.compile(r'^([0-9e\+\-\.]+)(t|g|meg|x|k|mil|m|u|n|p|f)?')
def unit(s):
    """Takes a string and returns the equivalent float.
    '3.0u' -> 3.0e-6"""
    mult = {'t'  :Decimal('1.0e12'),
            'g'  :Decimal('1.0e9'),
            'meg':Decimal('1.0e6'),
            'x'  :Decimal('1.0e6'),
            'k'  :Decimal('1.0e3'),
            'mil':Decimal('25.4e-6'),
            'm'  :Decimal('1.0e-3'),
            'u'  :Decimal('1.0e-6'),
            'n'  :Decimal('1.0e-9'),
            'p'  :Decimal('1.0e-12'),
            'f'  :Decimal('1.0e-15')}

    m = RE_UNIT.search(s.lower())
    try:
        if m.group(2):
            return Decimal(Decimal(m.group(1)))*mult[m.group(2)]
        else:
            return Decimal(m.group(1))
    except:
        error("Bad unit: %s" % s)


# read_params:
# Reads 'name=value' pairs from the top of the .bus file.
# Ensures that all required parameters have been provided.
# Returns a dict containing the parameters
def read_params(f):
    requiredParams = ('risefall', 'bittime', 'bitlow', 'bithigh')
    params = {'clockdelay':None, 'clockrisefall':None}

    #get parameters
    fposition = f.tell()
    line = f.readline()
    while '=' in line:
        name, value = line.split('=')
        name = name.strip()
        value = value.strip()
        params[name] = value
        fposition = f.tell()
        line = f.readline()

    #fixup file position back to start of next line
    f.seek(fposition)

    #check
    for p in requiredParams:
        if p not in params:
            error("%s is not specified, aborting." % p)

    info('Parameters:')
    for p,v in params.items():
        info('  %s = %s' % (p, v))

    return params

# read_signals:
# Reads and tokenizes the line containing signal names from the .bus file.
# Expands any busses specified using square brackets.
# Returns a list of strings representing the nodes to be included in the PWL
# file
def read_signals(f):
    line = f.readline()
    signals = [tok.strip() for tok in line.strip().split()] # Tokenize line

    nodes = [] # Init list of nodes
    for signal in signals: # Find and expand buses
        if '[' not in signal:
            nodes.append(signal) # Not a bus signal
        else:
            nodes.extend(expand_bus(signal)) # Expand bus to nodes

    info("Nodes: %s" % nodes)
    return nodes

# parse_word:
# Accepts as an argument a string. Converts a hex value or binary value
# specified with a leading '0b' to a string of '1's and '0's.
def parse_word(tok):
    if tok.startswith('0x'): # Specified as hex
        # Calculate the length of the binary string that will result from
        # expanding the hex value - each hex digit represents 4 binary digits
        n = 4 * (len(tok) - 2)

        # Convert hex value to binary
        intval = int(tok[2:], 16) # Convert hex value to integer
        binstr = bin(intval) # Convert integer value to binary string with '0b'
        bitstr = binstr[2:] # Get rid of the '0b'
        bits = bitstr.zfill(n) # Left-pad string with the zeros
    elif tok.startswith('0b'): # Specified as binary
        bits = tok[2:]
    else: # Base not specified - assume binary literal is given
        bits = tok

    return bits

# expand_vector_range:
# Expands 'range' shorthand notation in a bit vector specification into a list
# of bit strings. Returns a list of strings.
def expand_vector_range(pre_string, range_token):
    range_parts = range_token.split(']')

    # We now have a list of strings of the following format:
    # ['[n_bits', '(lo_val, hi_val)']
    n_bits = int(range_parts[0][1:]) # Remove leading '[' from nbits, make int

    range_parts = range_parts[1].split(',') # Split high and low of range
    range_parts[0] = int(range_parts[0][1:]) # Remove leading paren, make int
    range_parts[1] = int(range_parts[1][:-1]) # Remove trailing paren, make int

    # We now have a list containing the bounds of the range we will expand over
    expanded_range = [] # Will soon contain a bunch of strings

    range_ordered = sorted(range_parts) # Sort so that we can do a range:

    if range_parts[1] > 2**n_bits: # Ensure we have enough bits for range
        error('Expressing desired range requires more bits than specified')

    direction = 1 if range_parts[0] < range_parts[1] else -1

    for n in range(range_ordered[0], range_ordered[1], direction):
        bin_str = format(n, 'b').zfill(n_bits)
        expanded_range.append(pre_string + bin_str)

    return expanded_range

# add_vector:
# Adds a bit vector, specified as a string, to the dict containing all read
# vectors (signal_dict). Note that signal_dict is itself an entry to the
def add_vector(vector, signals, signal_dict):
    nsignals = len(signals) # Get expected length of vector
    if len(vector) == nsignals: # Ensure length of vector is as expected
        for signal, bit in zip(signals, vector):
            signal_dict[signal] += bit
    else:
        error('Vector length does not match number of signals (%s): %s' % (nsignals, vector))
    return

# read_vectors:
# Reads bit vectors line-by-line, expanding ranges as it goes.
# Returns a list of binary numbers represented as strings of 1s and 0s
def read_vectors(f, signal_labels):
    nsignals = len(signal_labels) # Get the number of individual signals
    signal_dict = dict([(label, '') for label in signal_labels])

    vectors = [] # Init blank list of vectors
    for line in f:
        range_flag = 0 # Clear range flag
        v = ""
        expanded_vector = []
        tokens = line.strip().split()
        for tok in tokens:
            tok = tok.strip() # Strip extra whitespace
            if '[' not in tok: # No range specified by token
                if range_flag: # If range has been processed previously
                    # If we've processed a range on this line, that means that
                    # expanded_vector will be a list of strings, all of which
                    # need the new bits to be added to them. Iterate over them
                    # and add the elements.
                    expanded_vector = [bitstr + parse_word(tok) for bitstr in expanded_vector]
                else: # No range has been processed on this line
                    # Convert token to bits; add to vector
                    v += parse_word(tok)
            else: # Range specified
                # We need to expand range notation into a list of strings. The
                # bits we've already registered need to be appended to the end
                # of every element in the range. Pass the bits we've gathered
                # so far as well as our 'range token' to the function that will
                # expand them.
                if range_flag == 0:
                    # This is the first range we have encoutered. We just need
                    # to expand it
                    range_flag = 1 # Set range flag
                    expanded_vector = expand_vector_range(v, tok)
                else:
                    # This is not the first range we have encoutered on this
                    # line. More processing is required.
                    next_exp_vector = expand_vector_range(v, tok) # expand

                    # The length of two ranges on the same line must be the
                    # same.
                    if len(next_exp_vector) != len(expanded_vector):
                        error('Ranges on the same line must have the same length: %s' % line)

                    # Add bit vectors from new token line-by-line to the
                    # existing list of bit vectors
                    expanded_vector = [old + new for (old, new) in zip(expanded_vector, next_exp_vector)]

        if range_flag:
            for vector in expanded_vector:
                add_vector(vector, signal_labels, signal_dict)
        else:
            add_vector(v, signal_labels, signal_dict)

    return signal_dict


# parse_busfile:
# Parses the contents of a .bus file given a path to the file
# Returns a dict with a 'param' key, and a 'signal' key. Each are, themselves,
# dicts containing specifications of parameters or signals
def parse_busfile(busfile):
    file_contents = { 'params': {}, 'signals': {} } # Init contents
    with open(busfile) as f:
        # Top of file will contain parameters - parse these first
        file_contents['params'] = read_params(f)
        # Read signal labels from the first line following parameters
        signal_labels = read_signals(f)
        # Read signal vectors
        file_contents['signals'] = read_vectors(f, signal_labels)

    return file_contents


# Execution begins here if module run as a script
if __name__ == '__main__':
    # python 2 vs 3 compatibility
    try:
        dict.iteritems
    except AttributeError:
        #this is python3
        def iteritems(d):
            return iter(d.items())
    else:
        def iteritems(d):
            return d.iteritems()

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description = "Parse a .bus file into a SPICE PWL file")
    parser.add_argument(
        'busfile',
        help = "File with specifying input and clock parameters")
    parser.add_argument(
        '-v', '--verbose',
        help = "Increase output verbosity",
        action = 'store_true')
    parser.add_argument(
        '-o', '--out',
        help = "Name of output PWL file")
    parser.add_argument(
        '-p', '--permissive',
        help = '''If specified, improperly specified bus signal names pass as
        wires instead of triggering errors''',
        action = 'store_true')
    args = parser.parse_args()

    # Basic error checking on input file
    if not args.busfile.endswith('.bus'):
        print("Error: Input file must have '.bus' extension")
        sys.exit(1)

    bus = parse_busfile(args.busfile) # Read and parse input file

    #get the numbers
    risefall = unit(bus['params']['risefall'])
    bittime = unit(bus['params']['bittime'])
    bitlow = unit(bus['params']['bitlow'])
    bithigh = unit(bus['params']['bithigh'])

    #generate output file
    if args.out:
        pwl_name = args.out # if user specified an output file, use it
    else:
        pwl_name = args.busfile.replace('.bus', '.pwl') # default out file name
    with open(pwl_name, 'w') as fpwl:
        output = lambda s: print(s, file=fpwl)
        # output clock definition if specified
        if bus['params']['clockdelay']:
            # calculate clock high time
            if bus['params']['clockrisefall']:
                clockrisefall = unit(bus['params']['clockrisefall'])
            else:
                clockrisefall = risefall

            clockhigh = Decimal('0.5') * (bittime - clockrisefall)
            clockperiod = bittime

            bus['params']['clockrisefall'] = str(clockrisefall)
            bus['params']['clockhigh'] = str(clockhigh)
            bus['params']['clockperiod'] = str(clockperiod)

            clk = 'Vclock clock 0 pulse(%(bitlow)s %(bithigh)s %(clockdelay)s %(clockrisefall)s %(clockrisefall)s %(clockhigh)s %(clockperiod)s)' % bus['params']
            info(clk)

            output(clk)
            output('')

        #output each input source
        for name, signal in iteritems(bus['signals']):
            #first line
            s = 'V%s %s 0 PWL' % (name, name)
            info(s)
            output(s)

            generate_waveform(signal)
            output('')

        info('Output file: ' + pwl_name)
