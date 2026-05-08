"""
CLI Framework Output Formatter

Supports multiple output formats: text/json/table
"""

import json
import sys
from typing import Any, List, Dict, Optional

from .constants import VALID_OUTPUT_FORMATS, DEFAULT_OUTPUT_FORMAT


class Output:
    """
    Output Formatter
    
    Supports multiple output formats: text/json/table
    
    Example:
        output = Output('json')
        output.print({'name': 'agent1'})
        
        output.success("Operation completed")
        output.error("Failed to execute")
    """
    
    def __init__(self, format: str = DEFAULT_OUTPUT_FORMAT):
        """
        Initialize output formatter
        
        Args:
            format: Output format (text/json/table)
        """
        if format not in VALID_OUTPUT_FORMATS:
            raise ValueError(f"Invalid format: {format}. Must be one of {VALID_OUTPUT_FORMATS}")
        self.format = format
    
    def print(self, data: Any, title: Optional[str] = None):
        """
        Format and output data
        
        Args:
            data: Data to output
            title: Title (optional)
        """
        if self.format == 'json':
            self._print_json(data)
        elif self.format == 'table':
            self._print_table(data, title)
        else:
            self._print_text(data, title)
    
    def print_table(self, headers: List[str], rows: List[List[Any]], title: Optional[str] = None):
        """
        Print data as formatted table
        
        Args:
            headers: Column headers
            rows: Data rows
            title: Optional title
        """
        if self.format == 'json':
            data = [dict(zip(headers, row)) for row in rows]
            self._print_json(data)
        else:
            self._print_formatted_table(headers, rows, title)
    
    def print_dict_table(self, data: Dict, field_order: Optional[List[str]] = None, 
                         labels: Optional[Dict[str, str]] = None, title: Optional[str] = None):
        """
        Print dictionary as attribute table
        
        First row shows attribute names, subsequent rows show values
        
        Args:
            data: Dictionary data
            field_order: Optional field order
            labels: Optional field label mapping
            title: Optional title
        """
        if self.format == 'json':
            self._print_json(data)
            return
        
        if field_order:
            keys = field_order
        else:
            keys = list(data.keys())
        
        headers = [labels.get(k, k) if labels else k for k in keys]
        values = [self._format_value(data.get(k, '')) for k in keys]
        
        self._print_formatted_table(headers, [values], title)
    
    def print_separate(self, label: str, data: Any, max_width: int = 50):
        """
        Print large data separately
        
        Args:
            label: Label for the data
            data: Data to print
            max_width: Maximum width for preview
        """
        if self.format == 'json':
            return
        
        print()
        print(f'{label}:')
        print('-' * len(label))
        
        if isinstance(data, (dict, list)):
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            data_str = str(data)
            if len(data_str) > max_width * 10:
                print(data_str[:max_width * 5] + '\n...\n' + data_str[-max_width * 5:])
            else:
                print(data_str)
    
    def _print_formatted_table(self, headers: List[str], rows: List[List[Any]], title: Optional[str] = None):
        """
        Print formatted table with fixed-width columns
        
        Args:
            headers: Column headers
            rows: Data rows
            title: Optional title
        """
        if title:
            print(f'\n{title}')
            print('=' * len(title))
        
        try:
            from tabulate import tabulate
            formatted_rows = []
            for row in rows:
                formatted_row = [self._format_value(v) for v in row]
                formatted_rows.append(formatted_row)
            print(tabulate(formatted_rows, headers=headers, tablefmt='grid'))
        except ImportError:
            self._print_simple_table(headers, rows)
    
    def _print_simple_table(self, headers: List[str], rows: List[List[Any]]):
        """
        Simple table format without tabulate
        
        Args:
            headers: Column headers
            rows: Data rows
        """
        col_width = 20
        
        header_line = ' | ' + ' | '.join(f'{h:<{col_width}}' for h in headers) + ' |'
        separator = '-+-' + '-+-'.join('-' * col_width for _ in headers) + '-'
        
        print()
        print(separator)
        print(header_line)
        print(separator)
        
        for row in rows:
            formatted_row = ' | ' + ' | '.join(f'{self._truncate(str(v), col_width-3):<{col_width}}' for v in row) + ' |'
            print(formatted_row)
        
        print(separator)
    
    def _format_value(self, value: Any, max_len: int = 50) -> str:
        """Format value for display"""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)[:max_len] + '...' if len(json.dumps(value)) > max_len else json.dumps(value, ensure_ascii=False)
        if isinstance(value, bool):
            return 'Yes' if value else 'No'
        if value is None:
            return ''
        return str(value)
    
    def _truncate(self, text: str, max_len: int) -> str:
        """Truncate text"""
        if len(text) > max_len:
            return text[:max_len - 3] + '...'
        return text
    
    def _print_json(self, data: Any):
        """
        JSON format output
        
        Args:
            data: Data
        """
        print(json.dumps(data, indent=2, ensure_ascii=False))
    
    def _print_table(self, data: Any, title: Optional[str] = None):
        """
        Table format output
        
        Args:
            data: Data
            title: Title
        """
        if title:
            print(f"\n{title}")
            print('=' * len(title))
        
        try:
            from tabulate import tabulate
            
            if isinstance(data, list) and data and isinstance(data[0], dict):
                headers = list(data[0].keys())
                rows = [[self._format_value(item.get(h, '')) for h in headers] for item in data]
                print(tabulate(rows, headers=headers, tablefmt='grid'))
            elif isinstance(data, dict):
                rows = [[k, self._format_value(v)] for k, v in data.items()]
                print(tabulate(rows, headers=['Property', 'Value'], tablefmt='grid'))
            else:
                print(data)
        except ImportError:
            self._print_text(data, title)
    
    def _print_text(self, data: Any, title: Optional[str] = None):
        """
        Text format output
        
        Args:
            data: Data
            title: Title
        """
        if title:
            print(f"\n{title}")
            print('=' * len(title))
        
        if isinstance(data, dict):
            for k, v in data.items():
                print(f"{k}: {v}")
        elif isinstance(data, list):
            for item in data:
                print(item)
        else:
            print(data)
    
    def success(self, msg: str):
        """
        Output success message
        
        Args:
            msg: Message content
        """
        if self.format == 'json':
            print(json.dumps({"status": "success", "message": msg}, ensure_ascii=False))
        else:
            print(f"[OK] {msg}")
    
    def error(self, msg: str):
        """
        Output error message
        
        Args:
            msg: Message content
        """
        if self.format == 'json':
            print(json.dumps({"status": "error", "message": msg}, ensure_ascii=False), file=sys.stderr)
        else:
            print(f"[ERROR] {msg}", file=sys.stderr)
    
    def warning(self, msg: str):
        """
        Output warning message
        
        Args:
            msg: Message content
        """
        if self.format == 'json':
            print(json.dumps({"status": "warning", "message": msg}, ensure_ascii=False))
        else:
            print(f"[WARN] {msg}")
    
    def info(self, msg: str):
        """
        Output info message
        
        Args:
            msg: Message content
        """
        if self.format == 'json':
            print(json.dumps({"status": "info", "message": msg}, ensure_ascii=False))
        else:
            print(msg)
    
    def set_format(self, format: str):
        """
        Set output format
        
        Args:
            format: Output format
        """
        if format not in VALID_OUTPUT_FORMATS:
            raise ValueError(f"Invalid format: {format}. Must be one of {VALID_OUTPUT_FORMATS}")
        self.format = format
    
    def get_format(self) -> str:
        """
        Get current output format
        
        Returns:
            Output format
        """
        return self.format