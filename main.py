#!/usr/bin/env python3
"""
Stock Market Movement Anomaly Detector
Main entry point - orchestrates the pipeline.
"""

import sys
from pathlib import Path

from helpers.cli import parse_arguments, INDEXES
from helpers.config import PipelineConfig
from helpers.processor import StockDataProcessor
from helpers.output import create_output_directory, write_results_csv


def main():
    """Main pipeline orchestration."""
    # Parse CLI arguments
    args = parse_arguments()
    
    # Determine which checks to run
    daily_check = not args.weekly_only
    weekly_check = not args.daily_only
    
    if not daily_check and not weekly_check:
        print("Error: Cannot disable both daily and weekly checks")
        sys.exit(1)
    
    # Load configuration
    config = PipelineConfig()
    
    # Build index-specific CLI overrides
    index_overrides = {}
    for index in INDEXES:
        daily_val = getattr(args, f'{index.lower()}_daily', None)
        weekly_val = getattr(args, f'{index.lower()}_weekly', None)
        
        if daily_val is not None or weekly_val is not None:
            index_overrides[index] = {'daily': daily_val, 'weekly': weekly_val}
    
    # Create processor with all settings
    processor = StockDataProcessor(
        config=config,
        daily=daily_check,
        weekly=weekly_check,
        daily_threshold=args.daily_threshold,
        weekly_threshold=args.weekly_threshold,
        index_overrides=index_overrides
    )
    
    # Create output directory and process files
    output_dir = create_output_directory()
    print(f"Output directory: {output_dir}\n")
    
    data_dir = Path('Data')
    csv_files = sorted(data_dir.glob('*.csv'))
    
    if not csv_files:
        print("Error: No CSV files found in Data/ directory")
        sys.exit(1)
    
    # Process each CSV file
    errors = []
    processed = []
    
    for csv_file in csv_files:
        index_name = csv_file.stem
        print(f"Processing {csv_file.name}...", end=' ')
        
        violations_df, result = processor.process_file(str(csv_file), index_name)
        
        if violations_df is None:
            error_msg = result.get('error', 'Unknown error')
            print(f"FAILED: {error_msg}")
            errors.append((csv_file.name, error_msg))
        else:
            write_results_csv(violations_df, index_name, result['thresholds'], output_dir)
            violation_count = len(violations_df)
            print(f"OK ({violation_count} violations)")
            processed.append((index_name, violation_count))
    
    # Print summary
    print("\n" + "="*50)
    print("SUMMARY")
    print("="*50)
    print(f"Processed: {len(processed)} files")
    for index, count in processed:
        print(f"  {index}: {count} violations")
    
    if errors:
        print(f"\nErrors: {len(errors)} files failed")
        for filename, error in errors:
            print(f"  {filename}: {error}")
    
    print(f"\nResults saved to: {output_dir}")


if __name__ == '__main__':
    main()
