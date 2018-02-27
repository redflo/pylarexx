#!/usr/bin/python3
# encoding: utf-8
'''
pylarexx -- Reads data from a Arexx TL-300 or TL-500 Datalogger


@author:     Florian Gleixner

@copyright:  2018. All rights reserved.

@license:    pylarexx is licensed under the Apache License, version 2, see License.txt

@deffield    updated: Updated
'''

import sys
import os
import datalogger.Logger
from argparse import ArgumentParser
from argparse import RawDescriptionHelpFormatter
import logging

__all__ = []
__version__ = 0.2
__date__ = '2017-11-22'
__updated__ = '2018-02-27'

DEBUG = 0
TESTRUN = 0
PROFILE = 0

class CLIError(Exception):
    '''Generic exception to raise and log different fatal errors.'''
    def __init__(self, msg):
        super(CLIError).__init__(type(self))
        self.msg = "E: %s" % msg
    def __str__(self):
        return self.msg
    def __unicode__(self):
        return self.msg

def main(argv=None): # IGNORE:C0111
    '''Command line options.'''

    if argv is None:
        argv = sys.argv
    else:
        sys.argv.extend(argv)

    program_name = os.path.basename(sys.argv[0])
    program_version = "v%s" % __version__
    program_build_date = str(__updated__)
    program_version_message = '%%(prog)s %s (%s)' % (program_version, program_build_date)
    program_shortdesc = __import__('__main__').__doc__.split("\n")[1]
    program_license = '''%s

  Created by Florian Gleixner on %s.
  Copyright 2017. All rights reserved.
  
  pylarexx is licensed under the Apache License, version 2, see License.txt

  Distributed on an "AS IS" basis without warranties
  or conditions of any kind, either express or implied.

USAGE
''' % (program_shortdesc, str(__date__))

    try:
        # Setup argument parser
        parser = ArgumentParser(description=program_license, formatter_class=RawDescriptionHelpFormatter)
        parser.add_argument("-f", "--file", dest="conffile", default="/etc/pylarexx.yml", help="Configfile for sensors, calibration and output.")
        parser.add_argument("-v", "--verbose", dest="verbose", action="count", help="set verbosity level [default: %(default)s]")
        parser.add_argument('-V', '--version', action='version', version=program_version_message)
        # parser.add_argument(dest="paths", help="paths to folder(s) with source file(s) [default: %(default)s]", metavar="path", nargs='+')

        # Process arguments
        args = parser.parse_args()

        conffile = args.conffile
        verbose = args.verbose
        if verbose==None:
            verbose=0
        if verbose > 3:
            verbose=3

        logginglevels={0:logging.ERROR, 1:logging.WARN, 2:logging.INFO, 3:logging.DEBUG}
        logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logginglevels[verbose])
        logging.info("log level %d" % logginglevels[verbose])


    except KeyboardInterrupt:
        ### handle keyboard interrupt ###
        return 0
    except Exception as e:
        if DEBUG or TESTRUN:
            raise(e)
        indent = len(program_name) * " "
        sys.stderr.write(program_name + ": " + repr(e) + "\n")
        sys.stderr.write(indent + "  for help use --help")
        return 2

    params={}
    if conffile != None:
        params['conffile']=conffile
    myDataLogger = datalogger.Logger.TLX00(params)
    myDataLogger.findDevices()
    myDataLogger.initializeDevices()
    myDataLogger.loop()
    


if __name__ == "__main__":
    if DEBUG:
        sys.argv.append("-vvv")
    if TESTRUN:
        import doctest
        doctest.testmod()
    if PROFILE:
        import cProfile
        import pstats
        profile_filename = 'pylarexx_profile.txt'
        cProfile.run('main()', profile_filename)
        statsfile = open("profile_stats.txt", "wb")
        p = pstats.Stats(profile_filename, stream=statsfile)
        stats = p.strip_dirs().sort_stats('cumulative')
        stats.print_stats()
        statsfile.close()
        sys.exit(0)
    sys.exit(main())