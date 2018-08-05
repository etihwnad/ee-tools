"""Return a dict containing information specified in an input busfile

Given a valid path to a file with either the .bus or .txt extension, attempts
to load the information specified by the file into numpy arrays and return the
information contained in the file as a dict. This dict will have keys 'param',
'signal', and 'out'. Each entry in the dict is, itself, a dict containing
information read from the busfile.

Positional arguments:
path: String that gives a path from the module to the busfile.
"""

import argparse
import os
import logging
from unit import unit

class ParseError(Exception):
    """Base class for exceptions in this module"""
    pass

class ParamMissingError(ParseError):
    """Exception raised if not all required parameters were in the bus file

    Attributes:
        message -- message indicating cause of failure
    """

    def __init__(self, param):
        self.message = "Required parameter '{}' was not found in bus file"\
                .format(param)

class NameExpandError(ParseError):
    """Exception raised if a bus name was improperly specified

    Attribute:
        message -- message containing the signal that expand_signal failed to
            expand
    """

    def __init__(self, signal):
        self.message = 'Improperly formatted bus signal: {}'.format(signal)

class VectorRangeError(ParseError):
    """Exception raised if an attempt to expand a vector range fails

    Attributes:
        message -- error message containing the string that expand_vector
            failed to expand
    """

    def __init__(self, vector):
        self.message = 'Bad vector range: {}'.format(vector)

def bin_str(tok):
    """Returns a binary string equivalent to the input value.

    Given a string that represents a binary number (with or without a '0b') or
    a hex value with a '0x' in front, converts the value to a string of 1s and
    0s. If a hex value is specified, each hex digit specifies four bits.
    """

    if tok.startswith('0x'): # Specified as hex
        # Calculate the length of the binary string if each hex digit
        # specifies 4 binary digits
        bin_strlen = 4 * (len(tok) - 2)
        # Convert hex value to binary
        intval = int(tok[2:], 16) # Convert hex value to integer
        binstr = bin(intval) # Convert integer value to binary string with '0b'
        bitstr = binstr[2:] # Get rid of the '0b'
        bits = bitstr.zfill(bin_strlen) # Left-pad string with the zeros
    elif tok.startswith('0b'): # Specified as binary
        bits = tok[2:]
    else: # Base not specified - assume binary literal
        bits = tok

    return bits

def expand_vector(range_token):
    """Expands busfile vector notation into a list of strings"""

    range_parts = range_token.split(']')

    # We now have a list of strings of the following format:
    # ['[n_bits', '(lo_val, hi_val)']
    try:
        n_bits = int(range_parts[0][1:]) # Remove leading '[' from nbits
    except IndexError:
        logging.critical('Bad vector range: {}'.format(range_token))
        raise

    # Generate a list with two integer elements that will specify the numeric
    # bounds to the values we will expand
    try:
        range_parts = range_parts[1].split(',') # Split high and low of range
        assert len(range_parts) in (2,3)
        # Account for difference in start/stop/step vs. start/stop syntax
        if len(range_parts) == 2:
            start = range_parts[0]
            step = 1
            stop = range_parts[1]
        elif len(range_parts) == 3:
            start = range_parts[0]
            step = int(range_parts[1])
            stop = range_parts[2]
        # Handle different bases for start value
        if start.lower().startswith('0x'):
            # Convert to integer using base 16
            start = int(start[3:], 16)
        elif start.lower().startswith('0b'):
            # Convert to integer using base 2
            start = int(start[3:], 2)
        else:
            # Convert to integer using base 10
            start = int(start[1:])
        # Handle different bases for the end value
        if stop.lower().startswith('0x'):
            # Convert to integer using base 16
            stop = int(stop[2:-1], 16)
        elif stop.lower().startswith('0b'):
            # Convert to integer using base 2
            stop = int(stop[2:-1], 2)
        else:
            # Convert to integer using base 10
            stop = int(stop[:-1])
    except (IndexError, AssertionError):
        logging.critical('Bad vector range: {}'.format(range_token))
        raise

    if stop > 2**n_bits: # Ensure the user left enough bits for range
        logging.critical('Insufficient bits to express range for vector {}'\
                .format(range_token))
        raise VectorRangeError(range_token)

    direction = 1 if range_parts[0] < range_parts[1] else -1
    range_sorted = sorted((start, stop))
    expanded_range = []
    logging.debug('expanded range: {}'.format(list(range(range_sorted[0], (range_sorted[1] + 1), (step * direction)))))
    for n in range(range_sorted[0], (range_sorted[1] + 1), (step * direction)):
        bin_str = format(n, 'b').zfill(n_bits)
        expanded_range.append(bin_str)

    return expanded_range

def read_vectors(f_obj, signals):
    """Read bit vectors from the busfile into a list.

    Reads bit vectors line-by-line. Expands any value ranges as it finds them.
    Returns a list of binary numbers represented as strings of 1s and 0s.

    Positional arguments:
        f_obj -- file object for busfile. The position should be set to the
            beginning of a line that starts with 'Vectors:'
        signals -- Python list of signal names. These should be in the same
            order that bits will be specified in these vectors.
    """

    # Ensure that our position in f_obj is at the beginning of a 'Vectors:'
    # section
    line = f_obj.readline()
    tokens = [tok.strip() for tok in line.strip().split()]
    assert tokens[0] == 'Vectors:', "keyword 'Vectors:' expected, found {}"\
            .format(tokens[0])
    # Read in and tokenize another line
    fposition = f_obj.tell()
    line = f_obj.readline()
    tokens = [tok.strip() for tok in line.strip().split()]

    # Initialize a dictionary with signal names as keys and empty strings as
    # entries. 1s and 0s will be appended to these empty strings as we read in
    # bit vectors
    signal_dict = dict([(sig, '') for sig in signals])

    # Our vectors array is going to be an array of strings. Each of these
    # strings must have a length equal to the number of signals we are
    # specifying, but the number of strings could vary from 1 to however large
    # a user-specified range is.
    vectors = []
    while line != '' and tokens[0].lower() != 'outputs:':
        line_vectors = [''] # Temporary holding place for this line's vectors
        # If we come across a line where 'Output:' is the first token on the
        # line, we stop reading vectors and return our inputs
        for tok in tokens:
            if '[' not in tok and ']' not in tok:
                # No range specified by token. Add the bits from this token to
                # the end of each of each vector we've found on this line
                line_vectors = [vect + bin_str(tok) for vect in line_vectors]
            else:
                # This token specifies a range of values we need to expand.
                vector_range = expand_vector(tok)

                # If we've previously expanded a range, line_vectors will have
                # length > 1. If this is the case, the lenth of vector_range
                # should be the same as that of line_vectors. We don't allow
                # expanding two ranges of different sizes on the same line.
                if len(line_vectors) > 1:
                    assert len(vector_range) == len(line_vectors), \
                            'ranges on same line must have same length'
                    # Create a new list of vectors where our new range is
                    # appended element-wise onto the old range
                    line_vectors = [old + new for (old, new) in \
                            zip(line_vectors, vector_range)]
                else:
                    # If we've not previously encountered a range, our list
                    # size needs to be increased to that of the range we just
                    # read.
                    line_vectors = [line_vectors[0] + v for v in vector_range]

        for vect in line_vectors:
            assert len(vect) == len(signals),\
                'Vector {} has length {} and should have length {}.'\
                .format(vect, len(vect), len(signals))
        vectors.extend(line_vectors)

        # Read in and tokenize another line
        fposition = f_obj.tell()
        line = f_obj.readline()
        # We want to eat blank lines, but also if we hit EOF we shouldn't try
        # to keep reading lines. Also: eat comment lines
        while not line.strip() or line[0] == '#':
            # If line evaluates to true, it's a blank line, not EOF.
            if line:
                fposition = f_obj.tell()
                line = f_obj.readline()
            else:
                # line == '', we've hit EOF. When the main while loop for this
                # function sees that line == '', the loop will exit.
                break # line == '', we've hit EOF. 
        tokens = [tok.strip() for tok in line.strip().split()]

    f_obj.seek(fposition)
    return vectors

def expand_signal(signal):
    """Returns a list of 1-wire signals from a signal specified as a bus

    Given a string of the form: "name[left:right]suffix", expands into a series
    of signals of the form: "name[#]". If the supplied string is not formatted
    correctly, this function will raise exceptions.
    """

    # Anatomy of a bus signal:  name[left:right]suffix
    name, lbrack, tail = signal.partition('[')
    left, colon, end = tail.partition(':')
    right, rbrack, suffix = end.partition(']')

    if not name:
        msg = 'No signal name found for signal {}'.format(signal)
        logging.critical(msg)
        raise NameExpandError(signal)

    # Only expand a complete bus - force users to be specific instead of
    # assuming what they wanted and giving them bogus results
    nodes = []
    if lbrack and colon and rbrack:
        try:
            start = int(left)
            stop = int(right)
        except ValueError:
            msg = 'Bad bus range: Start: {} Stop: {}.'.format(left, right)
            logging.critical(msg)
            raise NameExpandError(signal)

        inc = 1 if (stop > start) else -1 # [4:0] or [0:4]
        signal_bus = range(start, (stop + inc), inc)
        for wire in signal_bus:
            single_signal = '%s[%i]%s' % (name, wire, suffix)
            nodes.append(single_signal)
    else:
        # Partial bus notation - error
        msg = 'Improperly specified bus signal: {}'.format(signal)
        logging.critical('One of ([,:,]) is missing from bus signal {}'\
                .format(signal))
        raise NameExpandError(signal)

    return nodes

def read_signals(f_obj):
    """Return a list of signals defined by the busfile

    Reads a list of signal names from the bus file. Names may use square
    brackets to describe a multi-wire bus. Buses will be expanded to
    individual signals.

    Positional argument:
        f_obj -- File object for the bus file. Current position in the file
            should be the beginning of the 'Signals:' section
    """

    fposition = f_obj.tell()
    line = f_obj.readline()
    while not line.strip() or line[0] == '#':
        fposition = f_obj.tell()
        line = f_obj.readline()

    # Make sure that we are at the beginning of the signal declaration section.
    # We know we're there if the first token on the first line we read in is
    # 'Signals:'.
    tokens = [tok.strip() for tok in line.strip().split()]
    assert tokens[0].lower() == 'signals:' or tokens[0].lower() == 'outputs:',\
            "keyword 'Signals:' or 'Outputs:' expected, found {}" \
            .format(tokens[0])

    # 'Signals:' should be alone on its line. Read in the next line.
    fposition = f_obj.tell()
    line = f_obj.readline()
    # Ignore empty lines and comments
    while not line.strip() or line[0] == '#':
        fposition = f_obj.tell()
        line = f_obj.readline()
    sig_names = [tok.strip() for tok in line.strip().split()]

    # Everything from this point in the file until we find a line that begins
    # with the token 'Vectors:' will be taken to be a signal. Blank lines are
    # ignored, as are comment lines.
    signals = []
    while sig_names[0].lower() != 'vectors:':
        for sig in sig_names:
            # Check whether the signal is a bus. If it is, expand the signal
            # bus into individual wires. If the signal is already a single wire
            # we add it to our list straight away. We go into our bus
            # processing function if we find *either* a '[' or a ']' because
            # expand_signal contains logic that informs the user if their
            # bus signal declaration is incorrect.
            if '[' in sig or ']' in sig:
                individual_signals = expand_signal(sig)
                signals.extend(individual_signals)
            else:
                signals.append(sig)

        # Read and tokenize a new line
        fposition = f_obj.tell()
        line = f_obj.readline()
        # Ignore empty lines and comments
        while not line.strip() or line[0] == '#':
            fposition = f_obj.tell()
            line = f_obj.readline()
            if line == '':
                raise NameExpandError(\
                        "'Vectors:' keyword not reached before EOL")
        sig_names = [tok.strip() for tok in line.strip().split()]

    # We just found the 'Vectors:' line. Reset our position in f_obj to the
    # beginning of that line so that the read_vectors function can verify that
    # it's in the right place
    f_obj.seek(fposition)

    return signals

def read_params(f_obj):
    """Return a dict containing name, value pairs from the bus file

    Starts looking at the beginning of the file for a line that isn't a comment
    or whitespace. It tokenizes each line that it finds and attempts to match
    the first token on the line with a valid parameter name. If there is a
    match, the value of the parameter is shown. Otherwise, a warning is
    displayed.

    Positional argument:
    f_obj: File object returned by open() for the bus file.
    """

    params = {}
    # Required parameters
    logging.debug('Searching for input parameters')
    required_params = ['risefall', 'bittime', 'bitlow', 'bithigh']
    # Optional parameters
    params['edge'] = 'rising'
    params['clockdelay'] = None
    params['clockrisefall'] = None
    params['tsu'] = None
    params['th'] = None
    for p in required_params:
        params[p] = None

    fposition = f_obj.tell()
    line = f_obj.readline()
    # Ignore empty lines and comments
    while not line.strip() or line[0] == '#':
        fposition = f_obj.tell()
        line = f_obj.readline()

    # Read in parameters, ignoring blank lines
    while line.split()[0].lower() != 'signals:':
        assert '=' in line, 'improperly formatted param line: {}'.format(line)
        name, value = line.split('=')
        name = name.strip().lower()
        # Add read-in param to our dict, if it is a valid param.
        # If it is not a valid param, warn the user.
        if name in params:
            value = value.strip()
            params[name] = value
            logging.info('Parameter {} set to {}'.format(name, value))
        else:
            logging.error('Unkown parameter encountered: {}'.format(name))

        fposition = f_obj.tell()
        line = f_obj.readline()
        # Ignore empty lines and comments
        while not line.strip() or line[0][0] == '#':
            fposition = f_obj.tell()
            line = f_obj.readline()

    # Put file position back to the beginning of the line that did not start
    # with a parameter name.
    f_obj.seek(fposition)

    # Ensure that we have all of the required parameters. Raise an exception if
    # a required param is missing. We put all of these parameters into our
    # params dict with the value None. If any of our required params evaluate
    # as false now, we know we didn't find it in our bus file.
    for p in required_params:
        if not params[p]:
            raise ParamError(p)

    valid_edge_settings = ('rising', 'falling')
    assert params['edge'] in valid_edge_settings,\
            'Invalid edge value: {}. Valid values are: {}'\
            .format(params['edge'], valid_edge_settings)

    return params


def parse_busfile(buspath):
    """Return a dict containing information from a busfile.

    Positional argument:
    path: String that gives a path from this module to the busfile
    """

    file_contents = {'params': {}, 'signals': {}, 'outputs': {}}
    try:
        with open(buspath) as f:
            file_contents['params'] = read_params(f)
            # Read signal labels from the first line following parameters
            signals = read_signals(f)
            # Read signal vectors
            vectors = read_vectors(f, signals)
            # Prepare to load in vectors
            for sig in signals:
                file_contents['signals'][sig] = ''
            # Create signal dict from vectors and signals
            for vect in vectors:
                for (sig, bit) in zip(signals, vect):
                    file_contents['signals'][sig] += bit

            # Read in the next line from the file. There are only two things
            # it can be if no exceptions were thrown by read_vectors: it can
            # be EOF, or it can start with 'Outputs:'.
            line = f.readline()
            if line.lower().startswith('outputs:'):
                assert 'th' in file_contents['params'].keys(), \
                        'Outputs were specified for verification but no hold \
time ("th") was specified to use for verification.'
                assert 'tsu' in file_contents['params'].keys(), \
                        'Outputs were specified for verification but no setup \
time ("tsu") was specified to use for verification.'
                output_signals = read_signals(f)
                logging.info('Output signals: {}'.format(str(output_signals)))
                output_vectors = read_vectors(f, output_signals)
                for sig in output_signals:
                    file_contents['outputs'][sig] = ''
                for vect in output_vectors:
                    for (sig, bit) in zip(output_signals, vect):
                        file_contents['outputs'][sig] += bit

                # Check that an output was specified for all inputs
                input_sig = list(file_contents['signals'].keys())[0]
                output_sig = list(file_contents['outputs'].keys())[0]
                n_input_vectors = len(file_contents['signals'][input_sig])
                n_output_vectors = len(file_contents['outputs'][output_sig])
                assert n_input_vectors == n_output_vectors, \
                        'Number of output vectors ({}) does not match number \
of input vectors ({})'.format(n_output_vectors, n_input_vectors)
            elif line == '':
                logging.info('No output signals detected')
            else:
                logging.error('Expected "outputs:" or EOF, got {}'\
                        .format(line))

    except FileNotFoundError:
        msg = 'No bus file exists at {}'.format(buspath)
        logging.critical(msg)
        raise

    return file_contents

def write_busfile(file_contents):
    """Writes the contents of a busfile to a text file. Useful for debugging"""

    with open('busout.txt', 'w') as f:
        for key in file_contents['params']:
            f.write('{}, {}\n'.format(key, file_contents['params'][key]))
            f.write('\n')
        f.write('\nSignals:\n')
        for sig in file_contents['signals']:
            f.write('{}, {}\n'.format(sig, file_contents['signals'][sig]))
        f.write('\nOutputs:\n')
        for sig in file_contents['outputs']:
            f.write('{}, {}\n'.format(sig, file_contents['outputs'][sig]))

if __name__ == '__main__':
    """Barebones interface for calling this module standalone

    This is useful for debugging.
    """

    parser = argparse.ArgumentParser()
    parser.add_argument('file')
    args = parser.parse_args()

    path = os.path.abspath(args.file)

    write_busfile(parse_busfile(path))

