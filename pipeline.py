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
from typing import Dict, Tuple, Optional, List

INDEXES = ['SP500', 'DJIA', 'DJCA', 'DJTA', 'DJUA']


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
        """Get effective threshold considering CLI overrides.
        
        Priority: index-specific CLI > global CLI override > config file
        """
        if index in self.index_overrides:
            val = self.index_overrides[index].get(check_type)
            if val is not None:
                return val
        
        if check_type == 'daily' and self.daily_override is not None:
            return self.daily_override
        if check_type == 'weekly' and self.weekly_override is not None:
            return self.weekly_override
        
        if index in self.config.index_overrides:
            override = self.config.index_overrides[index].get(check_type)
            if override is not None:
                return override
        
        return self.config.global_daily if check_type == 'daily' else self.config.global_weekly
    
    def _perform_check(self, df: pd.DataFrame, index_name: str, check_type: str,
                       get_comparison: callable) -> List[Dict]:
        """Perform a single type of check (daily or weekly) on the dataframe."""
        threshold = self._get_threshold(index_name, check_type)
        violations = []
        
        for i in range(len(df)):
            comparison = get_comparison(df, i)
            if comparison is None:
                continue
            
            curr_date, curr_price, prev_date, prev_price = comparison
            pct_change = ((curr_price - prev_price) / prev_price) * 100
            
            if abs(pct_change) > threshold:
                violations.append({
                    'type': check_type,
                    'date': curr_date,
                    'compared_date': prev_date,
                    'date_val': curr_price,
                    'compared_date_val': prev_price,
                    'value_difference': curr_price - prev_price,
                    'pct_change': round(pct_change, 2)
                })
        
        return violations
    
    def _get_daily_comparison(self, df: pd.DataFrame, i: int) -> Optional[Tuple]:
        """Get comparison for daily check."""
        if i == 0:
            return None
        return (df.loc[i, 'date'], df.loc[i, 'price'],
                df.loc[i-1, 'date'], df.loc[i-1, 'price'])
    
    def _get_weekly_comparison(self, df: pd.DataFrame, i: int) -> Optional[Tuple]:
        """Get comparison for weekly check."""
        curr_date = df.loc[i, 'date']
        target_date = curr_date - timedelta(days=7)
        prev_rows = df[df['date'] <= target_date]
        
        if len(prev_rows) == 0:
            return None
        
        prev_idx = prev_rows.index[-1]
        return (curr_date, df.loc[i, 'price'],
                df.loc[prev_idx, 'date'], df.loc[prev_idx, 'price'])
    
    def process_file(self, file_path: str, index_name: str) -> Tuple[pd.DataFrame, Dict]:
        """Process a single CSV file and return violations."""
        try:
            df = pd.read_csv(file_path)
            
            if len(df.columns) != 2:
                return None, {'error': f"CSV must have exactly 2 columns, found {len(df.columns)}"}
            
            df.columns = ['date', 'price']
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            df['price'] = pd.to_numeric(df['price'], errors='coerce')
            df = df.dropna(subset=['date', 'price'])
            df = df.sort_values('date').reset_index(drop=True)
            
            violations = []
            
            if self.daily_check:
                violations.extend(self._perform_check(df, index_name, 'daily', self._get_daily_comparison))
            
            if self.weekly_check:
                violations.extend(self._perform_check(df, index_name, 'weekly', self._get_weekly_comparison))
            
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
    
    # Index-specific overrides (dynamically generated)
    for index in INDEXES:
        parser.add_argument(f'--{index.lower()}-daily', type=float, 
                          dest=f'{index.lower()}_daily',
                          help=f'{index} daily threshold')
        parser.add_argument(f'--{index.lower()}-weekly', type=float,
                          dest=f'{index.lower()}_weekly',
                          help=f'{index} weekly threshold')
    
    return parser.parse_args()



def create_output_directory():
    """Create timestamped output directory."""
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    unique_id = str(uuid.uuid4())[:8]
    output_dir = Path('results') / f'results_{timestamp}_{unique_id}'
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def write_results_csv(df: pd.DataFrame, index_name: str, thresholds: Dict, output_dir: Path):
    """Write violations to CSV with header info."""
    output_file = output_dir / f'{index_name}.csv'
    
    with open(output_file, 'w') as f:
        f.write(f'# Index: {index_name}, Daily Threshold: {thresholds["daily"]}%, Weekly Threshold: {thresholds["weekly"]}%\n')
        f.write('type,date,compared_date,date_val,compared_date_val,value_difference,pct_change\n')
        
        if not df.empty:
            for _, row in df.iterrows():
                f.write(f"{row['type']},{row['date'].strftime('%Y-%m-%d')},{row['compared_date'].strftime('%Y-%m-%d')},{row['date_val']},{row['compared_date_val']},{row['value_difference']},{row['pct_change']}\n")


def main():
    args = parse_arguments()
    
    daily_check = not args.weekly_only
    weekly_check = not args.daily_only
    
    if not daily_check and not weekly_check:
        print("Error: Cannot disable both daily and weekly checks")
        sys.exit(1)
    
    config = PipelineConfig()
    
    # Build index-specific overrides from CLI args
    index_overrides = {}
    for index in INDEXES:
        daily_val = getattr(args, f'{index.lower()}_daily', None)
        weekly_val = getattr(args, f'{index.lower()}_weekly', None)
        
        if daily_val is not None or weekly_val is not None:
            index_overrides[index] = {'daily': daily_val, 'weekly': weekly_val}
    
    processor = StockDataProcessor(
        config=config,
        daily=daily_check,
        weekly=weekly_check,
        daily_threshold=args.daily_threshold,
        weekly_threshold=args.weekly_threshold,
        index_overrides=index_overrides
    )
    
    output_dir = create_output_directory()
    print(f"Output directory: {output_dir}\n")
    
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
