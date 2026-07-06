"""Output handling and file writing."""

import pandas as pd
from datetime import datetime
from pathlib import Path
import uuid
from typing import Dict


def create_output_directory() -> Path:
    """Create timestamped output directory for results."""
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
