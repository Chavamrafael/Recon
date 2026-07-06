#!/usr/bin/env python3
"""
Stock Market Movement Anomaly Detector Pipeline
Flags significant price movements based on configurable thresholds.
"""

import argparse
import sys
import os
import yaml
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import uuid
from typing import Dict, Tuple, Optional


class PipelineConfig:
    def __init__(self, config_file: Optional[str] = None):
        self.global_daily = 1.0
        self.global_weekly = 5.0
        self.index_overrides = {}
        
        if config_file and os.path.exists(config_file):
            self._load_config(config_file)
        elif os.path.exists("config.yaml"):
            self._load_config("config.yaml")
    
    def _load_config(self, file_path: str):
        try:
            with open(file_path, 'r') as f:
                config = yaml.safe_load(f)
                
            if config and 'global' in config:
                self.global_daily = config['global'].get('daily_threshold', 1.0)
                self.global_weekly = config['global'].get('weekly_threshold', 5.0)
            
            if config and 'indexes' in config:
                for index, settings in config['indexes'].items():
                    if settings:
                        self.index_overrides[index] = {
                            'daily': settings.get('daily_threshold'),
                            'weekly': settings.get('weekly_threshold')
                        }
        except Exception as e:
            print(f"Warning: Failed to load config file {file_path}: {e}")
    
    def get_threshold(self, index: str, check_type: str) -> float:
        """Get threshold for index and check type.
        
        Priority: index-specific override > global > default
        """
        if index in self.index_overrides:
            override = self.index_overrides[index].get(check_type)
            if override is not None:
                return override
        
        if check_type == 'daily':
            return self.global_daily
        else:
            return self.global_weekly


class StockDataProcessor:
    def __init__(self, config: PipelineConfig, daily: bool, weekly: bool,
                 daily_threshold: Optional[float] = None,
                 weekly_threshold: Optional[float] = None,
                 index_overrides: Optional[Dict] = None):
        self.config = config
        self.daily_check = daily
        self.weekly_check = weekly
        self.daily_override = daily_threshold
        self.weekly_override = weekly_threshold
        self.index_overrides = index_overrides or {}
    
    def _get_threshold(self, index: str, check_type: str) -> float:
        """Get effective threshold considering CLI overrides."""
        # Priority: index-specific CLI > global CLI override > config
        if check_type == 'daily' and index in self.index_overrides:
            val = self.index_overrides[index]['daily']
            if val is not None:
                return val
        if check_type == 'weekly' and index in self.index_overrides:
            val = self.index_overrides[index]['weekly']
            if val is not None:
                return val
        
        if check_type == 'daily' and self.daily_override is not None:
            return self.daily_override
        if check_type == 'weekly' and self.weekly_override is not None:
            return self.weekly_override
        
        return self.config.get_threshold(index, check_type)
    
    def process_file(self, file_path: str, index_name: str) -> Tuple[pd.DataFrame, Dict]:
        """Process a single CSV file and return violations."""
        try:
            df = pd.read_csv(file_path)
            
            # Validate structure
            if len(df.columns) != 2:
                return None, {'error': f"CSV must have exactly 2 columns, found {len(df.columns)}"}
            
            date_col, price_col = df.columns
            
            # Rename for consistency
            df.columns = ['date', 'price']
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            df['price'] = pd.to_numeric(df['price'], errors='coerce')
            
            # Remove rows with missing dates or prices
            df = df.dropna(subset=['date', 'price'])
            df = df.sort_values('date').reset_index(drop=True)
            
            violations = []
            
            # Daily checks
            if self.daily_check:
                daily_threshold = self._get_threshold(index_name, 'daily')
                for i in range(1, len(df)):
                    curr_date = df.loc[i, 'date']
                    prev_date = df.loc[i-1, 'date']
                    curr_price = df.loc[i, 'price']
                    prev_price = df.loc[i-1, 'price']
                    
                    pct_change = ((curr_price - prev_price) / prev_price) * 100
                    
                    if abs(pct_change) > daily_threshold:
                        violations.append({
                            'type': 'daily',
                            'date': curr_date,
                            'compared_date': prev_date,
                            'date_val': curr_price,
                            'compared_date_val': prev_price,
                            'value_difference': curr_price - prev_price,
                            'pct_change': round(pct_change, 2)
                        })
            
            # Weekly checks
            if self.weekly_check:
                weekly_threshold = self._get_threshold(index_name, 'weekly')
                for i in range(len(df)):
                    curr_date = df.loc[i, 'date']
                    curr_price = df.loc[i, 'price']
                    
                    # Find date 7 days ago
                    target_date = curr_date - timedelta(days=7)
                    
                    # Find the closest date >= target_date in the past
                    prev_rows = df[df['date'] <= target_date]
                    if len(prev_rows) == 0:
                        continue
                    
                    prev_idx = prev_rows.index[-1]
                    prev_date = df.loc[prev_idx, 'date']
                    prev_price = df.loc[prev_idx, 'price']
                    
                    pct_change = ((curr_price - prev_price) / prev_price) * 100
                    
                    if abs(pct_change) > weekly_threshold:
                        violations.append({
                            'type': 'weekly',
                            'date': curr_date,
                            'compared_date': prev_date,
                            'date_val': curr_price,
                            'compared_date_val': prev_price,
                            'value_difference': curr_price - prev_price,
                            'pct_change': round(pct_change, 2)
                        })
            
            violations_df = pd.DataFrame(violations) if violations else pd.DataFrame()
            
            thresholds = {
                'daily': self._get_threshold(index_name, 'daily'),
                'weekly': self._get_threshold(index_name, 'weekly')
            }
            
            return violations_df, {'thresholds': thresholds}
            
        except Exception as e:
            return None, {'error': str(e)}


def parse_arguments():
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
    parser.add_argument('--sp500-daily', type=float, dest='sp500_daily',
                        help='SP500 daily threshold')
    parser.add_argument('--sp500-weekly', type=float, dest='sp500_weekly',
                        help='SP500 weekly threshold')
    parser.add_argument('--djia-daily', type=float, dest='djia_daily',
                        help='DJIA daily threshold')
    parser.add_argument('--djia-weekly', type=float, dest='djia_weekly',
                        help='DJIA weekly threshold')
    parser.add_argument('--djca-daily', type=float, dest='djca_daily',
                        help='DJCA daily threshold')
    parser.add_argument('--djca-weekly', type=float, dest='djca_weekly',
                        help='DJCA weekly threshold')
    parser.add_argument('--djta-daily', type=float, dest='djta_daily',
                        help='DJTA daily threshold')
    parser.add_argument('--djta-weekly', type=float, dest='djta_weekly',
                        help='DJTA weekly threshold')
    parser.add_argument('--djua-daily', type=float, dest='djua_daily',
                        help='DJUA daily threshold')
    parser.add_argument('--djua-weekly', type=float, dest='djua_weekly',
                        help='DJUA weekly threshold')
    
    return parser.parse_args()


def create_output_directory():
    """Create timestamped output directory."""
    timestamp = datetime.now().strftime('%Y-%m-%d')
    unique_id = str(uuid.uuid4())[:8]
    output_dir = Path('results') / f'results_{timestamp}_{unique_id}'
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def write_results_csv(df: pd.DataFrame, index_name: str, thresholds: Dict, output_dir: Path):
    """Write violations to CSV with header info."""
    output_file = output_dir / f'{index_name}.csv'
    
    with open(output_file, 'w') as f:
        # Write header with thresholds
        f.write(f'# Index: {index_name}, Daily Threshold: {thresholds["daily"]}%, Weekly Threshold: {thresholds["weekly"]}%\n')
        
        # Write column headers
        f.write('type,date,compared_date,date_val,compared_date_val,value_difference,pct_change\n')
        
        if not df.empty:
            # Format and write data rows
            for _, row in df.iterrows():
                f.write(f"{row['type']},{row['date'].strftime('%Y-%m-%d')},{row['compared_date'].strftime('%Y-%m-%d')},{row['date_val']},{row['compared_date_val']},{row['value_difference']},{row['pct_change']}\n")


def main():
    args = parse_arguments()
    
    # Determine which checks to run
    daily_check = not args.weekly_only
    weekly_check = not args.daily_only
    
    if not daily_check and not weekly_check:
        print("Error: Cannot disable both daily and weekly checks")
        sys.exit(1)
    
    # Load configuration
    config = PipelineConfig()
    
    # Build index-specific overrides from CLI args
    index_overrides = {}
    for index in ['SP500', 'DJIA', 'DJCA', 'DJTA', 'DJUA']:
        daily_key = f'{index.lower()}_daily'
        weekly_key = f'{index.lower()}_weekly'
        
        daily_val = getattr(args, daily_key, None)
        weekly_val = getattr(args, weekly_key, None)
        
        if daily_val is not None or weekly_val is not None:
            index_overrides[index] = {
                'daily': daily_val,
                'weekly': weekly_val
            }
    
    # Create processor
    processor = StockDataProcessor(
        config=config,
        daily=daily_check,
        weekly=weekly_check,
        daily_threshold=args.daily_threshold,
        weekly_threshold=args.weekly_threshold,
        index_overrides=index_overrides
    )
    
    # Create output directory
    output_dir = create_output_directory()
    print(f"Output directory: {output_dir}\n")
    
    # Process all CSV files
    data_dir = Path('Data')
    csv_files = sorted(data_dir.glob('*.csv'))
    
    if not csv_files:
        print("Error: No CSV files found in Data/ directory")
        sys.exit(1)
    
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
