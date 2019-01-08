from livetiming.recording import generate_analysis

import os
import sys


def main():
    # Generate an analysis data dump from a recording file
    recFile = sys.argv[1]
    generate_analysis(recFile, os.path.join(os.getcwd(), 'data.out.json'), True)


if __name__ == '__main__':
    main()
