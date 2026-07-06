"""Stock data processing and anomaly detection."""

import pandas as pd
from datetime import timedelta
from typing import Dict, Tuple, Optional, List
from .config import PipelineConfig


class StockDataProcessor:
    """Process stock CSV files and detect price movement anomalies."""
    
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
        """Get effective threshold with priority: index CLI > global CLI > config > default."""
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
    
    def _perform_check(self, df: pd.DataFrame, index_name: str, check_type: str) -> List[Dict]:
        """Perform a single type of check (daily or weekly) on the dataframe."""
        threshold = self._get_threshold(index_name, check_type)
        violations = []
        
        for i in range(len(df)):
            comparison = self._get_comparison(df, i, check_type)
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
    
    def _get_comparison(self, df: pd.DataFrame, i: int, check_type: str) -> Optional[Tuple]:
        """Get price comparison based on check type (daily vs 7-day)."""
        if check_type == 'daily':
            if i == 0:
                return None
            return (df.loc[i, 'date'], df.loc[i, 'price'],
                    df.loc[i-1, 'date'], df.loc[i-1, 'price'])
        else:  # weekly
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
                violations.extend(self._perform_check(df, index_name, 'daily'))
            
            if self.weekly_check:
                violations.extend(self._perform_check(df, index_name, 'weekly'))
            
            violations_df = pd.DataFrame(violations) if violations else pd.DataFrame()
            
            thresholds = {
                'daily': self._get_threshold(index_name, 'daily'),
                'weekly': self._get_threshold(index_name, 'weekly')
            }
            
            return violations_df, {'thresholds': thresholds}
            
        except Exception as e:
            return None, {'error': str(e)}
