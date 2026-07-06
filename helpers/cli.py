"""Command-line interface argument parsing."""

import argparse

INDEXES = ['SP500', 'DJIA', 'DJCA', 'DJTA', 'DJUA']


def parse_arguments():
    """Parse and return command-line arguments."""
    parser = argparse.ArgumentParser(
        description='Process stock market data and flag significant price movements'
    )
    parser.add_argument('--daily-only', action='store_true',
                        help='Only perform daily checks')
    parser.add_argument('--weekly-only', action='store_true',
                        help='Only perform weekly checks')
    parser.add_argument('--daily-threshold', type=float,
                        help='Global daily threshold (percent) - overrides config')
    parser.add_argument('--weekly-threshold', type=float,
                        help='Global weekly threshold (percent) - overrides config')
    
    # Index-specific overrides
    for index in INDEXES:
        parser.add_argument(f'--{index.lower()}-daily', type=float, 
                          dest=f'{index.lower()}_daily',
                          help=f'{index} daily threshold')
        parser.add_argument(f'--{index.lower()}-weekly', type=float,
                          dest=f'{index.lower()}_weekly',
                          help=f'{index} weekly threshold')
    
    return parser.parse_args()
