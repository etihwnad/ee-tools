# (C) Dan White <dan@whiteaudio.com>

import argparse
import busparse
from decimal import Decimal as D
import logging
import os
from unit import unit

def gen_signal(bus_params, signal, vector):
    '''Returns a string specifying signal using params in bus_params

    Arguments:
        bus_params: the 'params' dict from the dict returned by parse_bus
        signal: the name of the signal
        vector: a string of 1s and 0s
    '''

    pwl = 'V%s %s 0 PWL\n' % (signal, signal)

    hi = unit(bus_params['bithigh'])
    lo = unit(bus_params['bitlow'])
    trf = unit(bus_params['risefall'])
    bittime = unit(bus_params['bittime'])
    # Calculate a bittime that accounts for differences in rise/fall times
    # between the clock signal and the data signal
    clockrisefall = unit(bus_params['clockrisefall'])
    bittime += (clockrisefall + (clockrisefall - trf))

    # Lambda to get bit voltage from a '1' or '0'
    vbit = lambda bit: D(hi) if bit=='1' else D(lo)

    # Calculate the initial value of the PWL
    t = D('0.0')
    lastbit = vector[0]
    v_lastbit = vbit(lastbit)
    pwl += '+ 0 %s\n' % v_lastbit

    for bit in vector[1:]:
        t += bittime
        # only output a point when there is a change
        if bit != lastbit:
            # Mimic behavior of SPICE pulse source
            # Total period = 2*t_bit + 2*trf
            t_trans = t + trf
            v_nextbit = vbit(bit)
            pwl += '+ %s %s\n' % (t, v_lastbit)
            pwl += '+ %s %s\n' % (t_trans, v_nextbit)
            # Our new time reference is now the start of this 'bit' instead of
            # the start of the transition to this bit. If we didn't do this,
            # bits would get cut short by trf.
            t += trf
            lastbit = bit
            v_lastbit = v_nextbit

    return pwl

def gen_clock(bus_params):
    '''Returns a string that uses params to specify a clock signal'''

    logging.info('Generating clock signal')

    bittime = unit(bus_params['bittime'])

    if bus_params['clockrisefall']:
        clockrisefall = unit(bus_params['clockrisefall'])
    else:
        clockrisefall = unit(bus_params['risefall'])

    # Write these values back into params to ease string formatting
    bus_params['clockhigh'] = D('0.5') * (bittime - clockrisefall)
    bus_params['clockperiod'] = bittime + 2*clockrisefall

    if bus_params['clockdelay']:
        clockdelay = bus_params['clockdelay']
    else:
        # No clockdelay specified - set the clock such that input changes will
        # occur in the middle of the clock bit
        clockdelay = D('0.25') * bittime

    if bus_params['edge'] == 'rising':
        logging.debug('Generating clock for rising active edge')
        clk = 'Vclock clock 0 PULSE(%(bitlow)s %(bithigh)s %(clockdelay)s %(clockrisefall)s %(clockrisefall)s %(clockhigh)s %(clockperiod)s)\n' % bus_params
    elif bus_params['edge'] == 'falling':
        logging.debug('Generating clock for falling active edge')
        clk = 'Vclock clock 0 PULSE(%(bithigh)s %(bitlow)s %(clockdelay)s %(clockrisefall)s %(clockrisefall)s %(clockhigh)s %(clockperiod)s)\n' % bus_params
    else:
        raise ValueError('Invalid clock edge specified: {}'.\
                format(params['edge']))
    return clk

def bus2pwl(busfile, out=None):
    '''Translates inputs specified by a busfile into SPICE PWL sources

    Outputs the result of this translation to a .pwl file at the path specified
    by 'out'
    '''

    if out:
        assert os.path.isdir(os.path.dirname(out))
    # If the user specified an outpath, use it. Otherwise, use busfile name
    pwl_name = out if out else busfile.replace('.bus', '.pwl')

    bus_parsed = busparse.parse_busfile(busfile)
    bus_params = bus_parsed['params']

    with open(pwl_name, 'w') as f:
        # Write a newline at the beginning of the file. Most SPICE interpreters
        # skip the first line of a file. While the user is actually supposed
        # to import this pwl, not run it standalone, this shouldn't matter, but
        # we'll write a blank line just in case.
        f.write('\n')

        # Generate a clock signal if the user has requested one
        if bus_params['edge'] != 'none':
            f.write(gen_clock(bus_params))
            f.write('\n')

        # Output each input source
        for signal, vector in bus_parsed['signals'].items():
            f.write(gen_signal(bus_params, signal, vector))
            f.write('\n')

        logging.info('Busfile translated. Output file: {}'.format(pwl_name))
        return pwl_name

if __name__ == '__main__':

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description = "Parse a .bus file into a SPICE PWL file")
    parser.add_argument(
        'busfile',
        help = "File with specifying input and clock parameters")
    parser.add_argument(
        '-v', '--verbose', action='store_true',
        help = "Increase output verbosity")
    parser.add_argument(
        '-o', '--out', default=None,
        help = "Name of output PWL file")
    args = parser.parse_args()

    loglvl = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(filename='bus2pwl.log', level=loglvl)

    busfile_abspath = os.path.abspath(args.busfile)
    assert os.path.exists(busfile_abspath), 'busfile does not exist {}'\
            .format(busfile_abspath)

    bus2pwl(args.busfile, args.out)
