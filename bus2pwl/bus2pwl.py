#!/usr/bin/python

# (C) Dan White <dan@whiteaudio.com>

from __future__ import print_function, with_statement

import os
import re
import sys

from decimal import Decimal


# TODO:
# - allow comments in input file
# - passthru (header) comments
# - system info + datetime in output header


def usage():
    print('''
Usage: python bus2pwl.py digitalinputs.bus

bus file format
===============
[one name=value parameter per line]
[space-separated column labels for voltage source names AND node names]
[one line per bit interval of 0 or 1 for each column, no spaces between]

Example .bus contents for testing an adder
==========================================
clockdelay=500p
clockrisefall = 100p
risefall=200p
bittime=1n
bitlow=0
bithigh=5
a3 a2 a1 a0 b3 b2 b1 b0
00000000
00010001
00010010
11111111
01011010
01011011

Include the generated file, which also includes the Voltage-source definitons
for the input nodes as:
    .include "foo.pwl"

The "clockdelay=" parameter, if present, also generates a voltage source for a
clock as "Vclock clock 0 PWL ..." with a rising edge at every bittime with an
offset of clockdelay.  Hence, set "clockdelay=" to the maximum setup time of
your registers and the data on each line will be clocked in at the right time.
Parameter "clockrisefall=" is optional to separately specify the clock rise/
fall time if it is different from the data lines rise/fall.
''')


def info(s):
    print('INFO:', s)


def error(s):
    print('ERROR:', s)
    sys.exit(1)


def warn(s):
    print('WARNING:', s)


RE_BUS = re.compile(r'^(\S+)\[(\d+):(\d+)\]$')
def expand_bus_notation(names):
    nodes = []
    for n in names:
        m = RE_BUS.match(n)
        name, left, right = m.group(1, 2, 3)
        # valid bus notation
        if left is not None and right is not None:
            start = int(left)
            stop = int(right)
            if start >= stop:
                inc = -1
            else:
                inc = 1

            for i in range(start, (stop + inc), inc):
                s = '%s[%i]' % (name, i)
                nodes.append(s)
        else:
            nodes.append(name)

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



def read_params(f):
    """Read name=value lines from the input file.
    Validate agains required parameters.
    Return dict of the pairs.
    """
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



def parse_words(words):
    """Accepts a list of strings.
    Returns a list of '1' or '0' strings.
    """
    bits = []
    for w in words:
        if w.startswith('0x'):
            n = 4 * (len(w) - 2)
            w = bin(int(w[2:], 16))[2:].zfill(n)
        elif w.startswith('0b'):
            w = w[2:]

        bits.extend([b for b in w])
    return bits



def read_vectors(f, nodes):
    """Read the data vectors from the rest of the file.
    """
    signals = {n:[] for n in nodes}
    n_signals = len(nodes)

    for line in f:
        line = line.strip()
        words = line.split()
        bits = parse_words(words)

        if len(bits) != n_signals:
            error("Must have same # characters as column labels: %s" % line)

        for i in range(n_signals):
            signals[nodes[i]].append(bits[i])

    return signals



def read_busfile(bus):
    #read in the bus definition file
    with open(bus) as f:
        params = read_params(f)

        #next line is column labels
        line = f.readline()
        names = [c.strip() for c in line.strip().split()]
        nodes = expand_bus_notation(names)
        params['nodes'] = nodes
        info("Columns: %s" % nodes)

        #read in signal vectors
        signals = read_vectors(f, nodes)
        params['signals'] = signals

    return params




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



if len(sys.argv) < 2:
    usage()
    sys.exit(1)


bus_name = sys.argv[1]
if not bus_name.endswith('.bus'):
    usage()
    print("Error: File must have a .bus extension")
    sys.exit(1)


# read and parse input file
params = read_busfile(bus_name)

#get the numbers
risefall = unit(params['risefall'])
bittime = unit(params['bittime'])
bitlow = unit(params['bitlow'])
bithigh = unit(params['bithigh'])

#generate output file
pwl_name = bus_name.replace('.bus', '.pwl')
with open(pwl_name, 'w') as fpwl:
    output = lambda s: print(s, file=fpwl)

    #output clock definition if specified
    if params['clockdelay']:
        #calculate clock high time
        if params['clockrisefall']:
            clockrisefall = unit(params['clockrisefall'])
        else:
            clockrisefall = risefall

        clockhigh = Decimal('0.5') * (bittime - clockrisefall)
        clockperiod = bittime

        params['clockrisefall'] = str(clockrisefall)
        params['clockhigh'] = str(clockhigh)
        params['clockperiod'] = str(clockperiod)

        clk = 'Vclock clock 0 pulse(%(bitlow)s %(bithigh)s %(clockdelay)s %(clockrisefall)s %(clockrisefall)s %(clockhigh)s %(clockperiod)s)' % params
        info(clk)

        output(clk)
        output('')


    #output each input source
    for name, signal in iteritems(params['signals']):
        #first line
        s = 'V%s %s 0 PWL' % (name, name)
        info(s)
        output(s)

        generate_waveform(signal)
        output('')

    info('Output file: ' + pwl_name)
