"""
DATA STORE HELPER
=================

Centralized file I/O operations for JSON persistence.
Handles all read/write operations with error handling.
"""

import json
import os
from typing import Dict, List, Optional, Any
from pathlib import Path
import time


class DataStore:
    """Centralized data persistence layer"""
    
    # File mappings
    FILE_MAPPINGS = {
        'users': 'users.json',
        'products': 'products.json',
        'sales': 'sales.json',
        'expenses': 'expenses.json',
        'shifts': 'shifts.json',
        'time_entries': 'time_entries.json',
        'clock_entries': 'clock_entries.json',
        'batches': 'batches.json',
        'discounts': 'discounts.json',
        'credit_requests': 'credit_requests.json',
        'settings': 'settings.json',
        'reminders': 'reminders.json',
        'recipes': 'recipes.json',
        'notes': 'cashier_notes.json',
        'raw_materials': 'raw_materials.json',
        'subscriptions': 'subscriptions.json',
        'subscription_plans': 'subscription_plans.json',
        'vendors': 'vendors.json',
        'inventory_transactions': 'inventory_transactions.json'
    }
    
    def __init__(self, data_dir: str):
        """
        Args:
            data_dir: Base directory for data files
        """
        self.data_dir = data_dir
        self._ensure_data_dir()
    
    def _ensure_data_dir(self) -> None:
        """Ensure data directory exists and is writable"""
        try:
            Path(self.data_dir).mkdir(parents=True, exist_ok=True)
            
            # Test write access
            test_file = os.path.join(self.data_dir, '.write_test')
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            
            print(f"✅ DataStore ready: {self.data_dir}")
        except PermissionError:
            print(f"⚠️  Permission denied on {self.data_dir}, trying fallback")
            self.data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'data'))
            Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"⚠️  Error setting up data directory: {e}")
    
    def _get_file_path(self, key: str) -> str:
        """Get full path for a data file"""
        filename = self.FILE_MAPPINGS.get(key)
        if not filename:
            raise ValueError(f'Unknown data key: {key}')
        
        return os.path.join(self.data_dir, filename)
    
    def load(self, key: str) -> Optional[Any]:
        """
        Load data from file.
        
        Args:
            key: Data key (e.g., 'products', 'sales')
        
        Returns:
            Loaded data (list or dict), or None if error
        """
        try:
            filepath = self._get_file_path(key)
            
            if not os.path.exists(filepath):
                # Initialize empty file
                self._init_file(filepath)
                return []
            
            with open(filepath, 'r') as f:
                content = f.read().strip()
                
                if not content:
                    return []
                
                data = json.loads(content)
                return data if isinstance(data, list) else [data]
        
        except json.JSONDecodeError as e:
            print(f"⚠️  JSON parse error in {key}: {e}")
            return []
        except Exception as e:
            print(f"❌ Error loading {key}: {e}")
            return None
    
    def save(self, key: str, data: Any) -> bool:
        """
        Save data to file.
        
        Args:
            key: Data key
            data: Data to save (list or dict)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            filepath = self._get_file_path(key)
            
            # Ensure directory exists
            Path(filepath).parent.mkdir(parents=True, exist_ok=True)
            
            # Write to temporary file first (atomic write)
            temp_filepath = filepath + '.tmp'
            
            with open(temp_filepath, 'w') as f:
                json.dump(data, f, indent=2)
            
            # Atomic rename
            if os.path.exists(filepath):
                os.remove(filepath)
            os.rename(temp_filepath, filepath)
            
            return True
        
        except Exception as e:
            print(f"❌ Error saving {key}: {e}")
            # Clean up temp file if it exists
            try:
                temp_filepath = filepath + '.tmp'
                if os.path.exists(temp_filepath):
                    os.remove(temp_filepath)
            except:
                pass
            return False
    
    def _init_file(self, filepath: str) -> None:
        """Initialize a data file with empty array"""
        try:
            Path(filepath).parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, 'w') as f:
                json.dump([], f)
        except Exception as e:
            print(f"⚠️  Error initializing {filepath}: {e}")
    
    def init_all(self) -> None:
        """Initialize all data files"""
        for key in self.FILE_MAPPINGS.keys():
            try:
                filepath = self._get_file_path(key)
                if not os.path.exists(filepath):
                    self._init_file(filepath)
            except Exception as e:
                print(f"⚠️  Error initializing {key}: {e}")
    
    def export_account_data(self, account_id: str) -> Dict[str, Any]:
        """
        Export all data for an account (for backup/export).
        
        Returns:
            {
                'users': [...],
                'products': [...],
                'sales': [...],
                ...
            }
        """
        export = {}
        
        try:
            for key in self.FILE_MAPPINGS.keys():
                data = self.load(key)
                if data:
                    # Filter by account ID if applicable
                    if key in ['products', 'sales', 'expenses', 'shifts']:
                        filtered = [item for item in data 
                                  if item.get('accountId') == account_id]
                        export[key] = filtered
                    else:
                        export[key] = data
        
        except Exception as e:
            print(f"❌ Error exporting account data: {e}")
        
        return export
    
    def clear_all(self, exclude_keys: List[str] = None) -> bool:
        """Clear all data files (except those in exclude_keys)"""
        exclude_keys = exclude_keys or []
        
        try:
            for key in self.FILE_MAPPINGS.keys():
                if key in exclude_keys:
                    continue
                
                if not self.save(key, []):
                    print(f"⚠️  Failed to clear {key}")
            
            return True
        
        except Exception as e:
            print(f"❌ Error clearing data: {e}")
            return False
