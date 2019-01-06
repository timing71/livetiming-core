from livetiming.recording import generate_analysis


def main():
    # Generate an analysis data dump from a recording file
    recFile = sys.argv[1]
    generate_analysis(recFile, 'data.out.json', True)


if __name__ == '__main__':
    main()
