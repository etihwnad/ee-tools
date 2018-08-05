import argparse
import busparse
from decimal import Decimal as D
import logging
import os
import PyLTSpice.LTSpice_RawRead as rawparse
from unit import unit

def clockedge_index(time_array, target_time):
    '''Return the index of the last time less than the target time

    It is necessary to find the 'last time less than a target time' because
    many circuit simulators, like LTSpice, do not necessarily maintain uniform
    spacing betwee time points

    The time_array should be sliced before it is passed to this function such
    that the first element in time_array is the last clock edge.
    '''

    logging.debug('Searching for target time: {}'.format(target_time))
    enumerated_times = enumerate(time_array)
    # Find the time of the first clock edge
    edge_index = 0
    for index, time in enumerated_times:
        # We take the absolute value of 'time' here because I've found that
        # in LTSpice RawFiles, there's sometimes negative times. The magnitude
        # of the times appears to be correct (it falls between the positive
        # times above and below it), but the sign is negative. I'm assuming
        # this is just another LTSpice bug
        if abs(time) < target_time:
            edge_index = index
        else:
            break

    logging.debug('Advanced {} time samples'.format(edge_index))

    return edge_index

def busverify(bus, raw):
    '''Checks that SPICE waveforms conform to the ouput spec in a bus file'''

    assert os.path.isfile(bus)
    assert os.path.isfile(raw)

    bus_parsed = busparse.parse_busfile(bus)
    try:
        bus_outputs = bus_parsed['outputs']
    except KeyError:
        logging.critical('No output spec found in {}'.format(bus))
        raise
    # Get the names of the signals we are checking
    output_signals = bus_outputs.keys()
    logging.debug('The following outputs were specified in the busfile: {}'\
            .format(output_signals))
    # Convert output signals to voltage net names
    output_netnames = [''.join(('V(',signal,')')) for signal in output_signals]
    logging.debug('Finding the following netnames in the rawfile: {}'\
            .format(output_netnames))
    # Unpack output signals into a list of strings passed to LTSpiceRawRead
    raw_parsed = rawparse.LTSpiceRawRead(raw, ' '.join(output_netnames))
    # Verify that all signals in output specification are in our rawfile. If
    # we find that any are missing, this is likely because the netname in the
    # BUS file does no match the one in the raw file.
    logging.debug('Ensuring that all specified outputs are in the rawfile...')
    for net in output_netnames:
        assert net in raw_parsed.get_trace_names(), \
                'Specified output signal {} was not found in the rawfile'\
                .format(net)
    logging.info('All specified outputs were found in the rawfile')

    time_array = raw_parsed.axis.data

    clockparams = bus_parsed['params']
    bittime = unit(clockparams['bittime'])
    tsu = unit(clockparams['tsu'])
    th = unit(clockparams['th'])
    clockdelay = unit(clockparams['clockdelay'])
    clockrisefall = unit(clockparams['clockrisefall'])
    logging.debug('Params:\n\tBit time: {}\n\tSetup time: {}\n\tHold time: {}\
            \n\tClock delay: {}\n\tClockrisefall: {}'\
            .format(bittime, tsu, th, clockdelay, clockrisefall))

    # First edge starts at the clock delay - subsequent edges are found at
    # last_edge + clockperiod
    first_edge_time = clockdelay
    clockperiod = bittime + 2*clockrisefall

    logic_hi = D(clockparams['bithigh'])
    logic_lo = D(clockparams['bitlow'])
    logic_thresh = (logic_hi - logic_lo) * D(0.75)
    logging.debug('Threshold voltage for logic 1: {}'.format(logic_thresh))

    all_passed = True

    # Verify waveforms
    for signal, net in zip(output_signals, output_netnames):
        logging.debug('Testing signal: {}'.format(signal))
        loop_edge_time = first_edge_time
        su_index = 0
        hold_index = 0
        bit_count = 0
        trace = raw_parsed.get_trace(net).data
        simulation_results = ''
        for bit in bus_outputs[signal]:
            logging.debug(' - Testing bit {}'.format(bit_count))
            bit_count += 1
            logging.debug('Looking for logic {} at t={}'\
                    .format(bit, loop_edge_time))
            # Find the array indices of the setup and hold times associated
            # with a given clock edge
            edge_su_time = loop_edge_time - tsu
            edge_hold_time = loop_edge_time + th + clockrisefall
            # Start searching for su_index after last hold index
            next_su = clockedge_index(time_array[hold_index:], edge_su_time)
            su_index = hold_index + next_su
            # Start searching for next hold index after the su_index
            next_h = clockedge_index(time_array[su_index:], edge_hold_time)
            hold_index = su_index + next_h
            logging.debug('su_index: {}'.format(su_index))
            logging.debug('hold_index: {}'.format(hold_index))

            # Determine whether simulation yielded a '1' or '0' after clk edge
            if hold_index - su_index != 0:
                # We use hold_index+1 for the slice because we want hold_index
                # to be included in the slice
                logging.debug(time_array[su_index:(hold_index+1)])
                logging.debug(trace[su_index:(hold_index+1)])
                v_avg = sum(trace[su_index:(hold_index+1)])
                logging.debug('Sum of voltages over points: {}'.format(v_avg))
                npoints = hold_index - su_index + 1
                v_avg /= (hold_index - su_index + 1)
                logging.debug('Dividing sum by {}'.format(npoints))
            else:
                v_avg = trace[su_index]

            logging.debug('Average voltage found: {}'.format(v_avg))
            simulated_bit = '1' if v_avg > logic_thresh else '0'
            simulation_results += simulated_bit

            # Get time of next clock edge
            loop_edge_time += clockperiod

        if simulation_results == bus_outputs[signal]:
            logging.info('{} passed - outputs were: {}'\
                    .format(signal, simulation_results))
        else:
            all_passed = False
            logging.error("{} failed.\nActual: {}\nSpec'd: {}"\
                    .format(signal, simulation_results, bus_outputs[signal]))
    return all_passed

if __name__ == '__main__':
    descript = "Verify SPICE waveforms against output specs from a busfile"
    parser = argparse.ArgumentParser(description=descript)
    parser.add_argument('buspath', help="path to a busfile")
    parser.add_argument('rawpath', help="path to a SPICE rawfile")
    parser.add_argument('-v', '--verbose', action="store_true",
            help="enable verbose logs")
    args = parser.parse_args()

    # Setup logging
    logfile = 'busverify.log'
    try:
        os.remove(logfile)
    except FileNotFoundError:
        pass  # Indicates that logfile didn't previously exist
    loglevel = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=loglevel, filename=logfile)

    all_pass = busverify(bus=args.buspath, raw=args.rawpath)
    if (all_pass):
        print('All vectors passed')
    else:
        print('Some vectors failed')
