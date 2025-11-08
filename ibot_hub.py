#!/usr/bin/env python3
"""
LeaDMify - Unified Automation Platform
Combines Campaign Automation, Unread Messages Checker, and Profile Manager
Version 4.0 - All-in-One Edition

Features:
- Single token authentication for all tools
- Campaign automation with auto-restart
- Unread messages checker across all profiles
- Firefox profile manager
- Unified menu system

Author: LeaDMify Team
"""

import requests
import json
import time
import threading
import random
import pyperclip
import subprocess
import sys
import os
import re
import shutil
import uuid
import platform
import unicodedata
from datetime import datetime
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import (
    TimeoutException, 
    NoSuchElementException, 
    WebDriverException,
    SessionNotCreatedException
)
from requests.exceptions import (
    ConnectionError, 
    Timeout, 
    RequestException,
    HTTPError
)

# Platform-specific imports
if sys.platform == "win32":
    import win32gui
    import win32con
    import io

# Configure environment
os.environ['WDM_LOG_LEVEL'] = '0'
os.environ['WDM_PRINT_FIRST_LINE'] = 'False'

# Fix Windows console encoding
if sys.platform == "win32":
    try:
        os.system("chcp 65001 >nul 2>&1")
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except:
        pass

# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """Centralized configuration"""
    API_BASE_URL = "https://api.leadmify.com"
    MONITOR_INTERVAL = 15
    MAX_RETRIES_PROFILE = 3
    MAX_RETRIES_API = 5
    API_TIMEOUT = 30
    CONNECTION_CHECK_INTERVAL = 5
    MAX_CONNECTION_FAILURES = 10
    BACKOFF_BASE = 2
    MAX_BACKOFF = 300

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def safe_print(message, emoji="ℹ️", level="INFO"):
    """Thread-safe printing with timestamp"""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {emoji} {message}", flush=True)
    except Exception:
        try:
            print(f"{emoji} {message}")
        except:
            pass

def check_internet_connection(url="https://www.google.com", timeout=5):
    """Check if internet connection is available"""
    try:
        requests.get(url, timeout=timeout)
        return True
    except:
        return False

def exponential_backoff(attempt, base=2, max_delay=300):
    """Calculate exponential backoff delay"""
    delay = min(base ** attempt, max_delay)
    return delay + random.uniform(0, 1)

def extract_int(text):
    """Extract integer from text using regex"""
    if not text:
        return 0
    m = re.search(r'(\d+)', text)
    return int(m.group(1)) if m else 0

# ============================================================================
# CUSTOM EXCEPTIONS
# ============================================================================

class TokenExpiredException(Exception):
    """Token has expired or is invalid"""
    pass

class CampaignStoppedException(Exception):
    """Campaign was stopped by user"""
    pass

class ProfileException(Exception):
    """Profile-related error"""
    pass

class ConnectionLostException(Exception):
    """Internet connection lost"""
    pass

# ============================================================================
# FIREFOX PROFILE MANAGER
# ============================================================================

class FirefoxProfileManager:
    """Manages Firefox profiles programmatically"""
    
    def __init__(self):
        self.system = sys.platform
        self.profiles_dir = self._get_profiles_directory()
    
    def _get_profiles_directory(self):
        """Get Firefox profiles directory"""
        if sys.platform == "win32":
            return Path.home() / "AppData" / "Roaming" / "Mozilla" / "Firefox" / "Profiles"
        elif sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / "Firefox" / "Profiles"
        else:
            return Path.home() / ".mozilla" / "firefox"
    
    def list_profiles(self):
        """List all Firefox profiles"""
        profiles = []
        
        if not self.profiles_dir.exists():
            return {'profiles': [], 'error': f'Profiles directory not found: {self.profiles_dir}'}
        
        for item in self.profiles_dir.iterdir():
            if item.is_dir():
                try:
                    profiles.append({
                        'name': item.name,
                        'path': str(item),
                        'size_mb': round(sum(f.stat().st_size for f in item.rglob('*') if f.is_file()) / (1024 * 1024), 2)
                    })
                except:
                    pass
        
        return {'profiles': profiles, 'profiles_dir': str(self.profiles_dir)}
    
    def test_profile(self, profile_path):
        """Test if profile is valid"""
        try:
            profile_path = Path(profile_path)
            
            if not profile_path.exists():
                return {'valid': False, 'error': 'Profile does not exist'}
            
            if not (profile_path / 'prefs.js').exists():
                return {'valid': False, 'error': 'Missing prefs.js file'}
            
            return {'valid': True}
        except Exception as e:
            return {'valid': False, 'error': str(e)}
    
    def create_profile(self, profile_name, is_default=False):
        """Create a new Firefox profile"""
        try:
            # Create a unique profile directory name
            profile_id = str(uuid.uuid4())[:8]
            profile_dir_name = f"{profile_id}.{profile_name}"
            profile_path = self.profiles_dir / profile_dir_name
            
            # Create the profile directory
            profile_path.mkdir(parents=True, exist_ok=True)
            
            # Create basic profile files
            prefs_js = profile_path / 'prefs.js'
            with open(prefs_js, 'w') as f:
                f.write('// Firefox profile preferences\n')
                f.write('user_pref("browser.startup.homepage", "about:blank");\n')
                f.write('user_pref("browser.startup.page", 0);\n')
            
            # Create user.js for additional preferences
            user_js = profile_path / 'user.js'
            with open(user_js, 'w') as f:
                f.write('// User preferences\n')
                f.write('user_pref("browser.shell.checkDefaultBrowser", false);\n')
                f.write('user_pref("browser.startup.homepage", "about:blank");\n')
            
            return {
                'success': True, 
                'message': f'Profile "{profile_name}" created successfully',
                'profile_path': str(profile_path),
                'profile_name': profile_name
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def delete_profile(self, profile_path):
        """Delete a Firefox profile"""
        try:
            profile_path = Path(profile_path)
            
            if not profile_path.exists():
                return {'success': False, 'error': 'Profile does not exist'}
            
            # Check if profile is currently in use
            if self._is_profile_in_use(profile_path):
                return {'success': False, 'error': 'Profile is currently in use and cannot be deleted'}
            
            # Remove the entire profile directory
            shutil.rmtree(profile_path)
            
            return {
                'success': True, 
                'message': f'Profile deleted successfully',
                'deleted_path': str(profile_path)
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _is_profile_in_use(self, profile_path):
        """Check if profile is currently in use by Firefox"""
        try:
            if sys.platform == "win32":
                try:
                    result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq firefox.exe'], 
                                          capture_output=True, text=True, timeout=5)
                    if 'firefox.exe' in result.stdout.lower():
                        # Check if any Firefox process is using this profile
                        try:
                            result = subprocess.run(['wmic', 'process', 'where', 'name="firefox.exe"', 'get', 'commandline'], 
                                                  capture_output=True, text=True, timeout=5)
                            if str(profile_path) in result.stdout:
                                return True
                        except:
                            pass
                except:
                    pass
            return False
        except Exception:
            return False

# ============================================================================
# UNREAD MESSAGES CHECKER
# ============================================================================

class UnreadMessagesChecker:
    """Checks unread DM count for Instagram profiles"""
    
    def __init__(self, api_url, token):
        self.api_url = api_url
        self.token = token
        self.headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
    
    def _get_unread_for_profile(self, profile_path):
        """Check unread messages for a single profile"""
        options = Options()
        options.add_argument("--headless")
        options.add_argument("-profile")
        options.add_argument(profile_path)
        options.add_argument("--log-level=3")
        options.set_preference("dom.webdriver.enabled", False)
        options.set_preference('useAutomationExtension', False)
        
        driver = None
        unread = 0
        
        try:
            geckodriver_paths = [
                "geckodriver.exe",
                "C:\\geckodriver\\geckodriver.exe",
                "/usr/local/bin/geckodriver",
                "/usr/bin/geckodriver"
            ]
            
            for path in geckodriver_paths:
                if os.path.exists(path):
                    driver = webdriver.Firefox(options=options)
                    break
            
            if not driver:
                driver = webdriver.Firefox(options=options)
            
            driver.get("https://www.instagram.com")
            time.sleep(6)
            
            try:
                badge = WebDriverWait(driver, 6).until(
                    EC.presence_of_element_located((By.XPATH, "//a[contains(@href, '/direct/inbox')]//span"))
                )
                unread = extract_int(badge.text.strip())
            except:
                unread = 0
                
        except Exception as e:
            safe_print(f"Error checking profile: {str(e)[:50]}", "⚠️", "WARNING")
            unread = 0
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
        
        return unread
    
    def check_all_profiles(self):
        """Check unread messages for all active profiles"""
        try:
            response = requests.get(
                f"{self.api_url}/api/profiles?page=1&limit=100",
                headers=self.headers,
                timeout=30
            )
            
            if response.status_code != 200:
                return {'error': 'Failed to fetch profiles'}
            
            profiles_data = response.json().get('profiles', [])
            active_profiles = [p for p in profiles_data if p.get('is_active', False)]
            
            safe_print(f"Checking {len(active_profiles)} active profile(s) for unread messages", "📬", "INFO")
            
            results = []
            total_unread = 0
            
            for profile in active_profiles:
                profile_path = profile.get('profile_path')
                profile_name = profile.get('profile_name', 'Unknown')
                
                if not profile_path or not os.path.exists(profile_path):
                    continue
                
                safe_print(f"Checking: {profile_name}", "🔍", "INFO")
                unread_count = self._get_unread_for_profile(profile_path)
                
                results.append({
                    'profile_name': profile_name,
                    'unread_count': unread_count
                })
                
                total_unread += unread_count
                
                if unread_count > 0:
                    safe_print(f"  → {unread_count} unread message(s)", "📩", "INFO")
                else:
                    safe_print(f"  → No unread messages", "✅", "INFO")
            
            return {
                'success': True,
                'results': results,
                'total_unread': total_unread,
                'profiles_checked': len(results)
            }
            
        except Exception as e:
            return {'error': str(e)}

# ============================================================================
# MAIN AUTOMATION CLASS
# ============================================================================

class IBotAutomation:
    """Campaign automation with all features from v3.0"""
    
    def __init__(self, api_base_url=None, token=None):
        self.api_base_url = api_base_url or Config.API_BASE_URL
        self.token = token
        self.session = None
        self._init_session()
        
        self.running = True
        self.global_stop = False
        self.active_campaigns = {}
        self.processed_requests = set()  # Track processed requests to avoid loops
        self.request_cleanup_counter = 0  # Counter for cleanup
        self.open_profiles = set()  # Track profiles that are already open
        
        self.campaign_lock = threading.Lock()
        self.connection_lock = threading.Lock()
        
        self.connection_failures = 0
        self.last_connection_check = time.time()
        
        safe_print("Automation initialized successfully", "✅", "INFO")
    
    def _init_session(self):
        """Initialize requests session with retry strategy"""
        self.session = requests.Session()
        import certifi
        self.session.verify = certifi.where()
        
        try:
            from requests.adapters import HTTPAdapter
            from urllib3.util.retry import Retry
            
            try:
                retry_strategy = Retry(
                    total=3,
                    backoff_factor=1,
                    status_forcelist=[429, 500, 502, 503, 504],
                    allowed_methods=["HEAD", "GET", "OPTIONS", "POST", "PUT"]
                )
            except TypeError:
                retry_strategy = Retry(
                    total=3,
                    backoff_factor=1,
                    status_forcelist=[429, 500, 502, 503, 504],
                    method_whitelist=["HEAD", "GET", "OPTIONS", "POST", "PUT"]
                )
            
            adapter = HTTPAdapter(max_retries=retry_strategy)
            self.session.mount("http://", adapter)
            self.session.mount("https://", adapter)
        except Exception:
            pass
        
        if self.token:
            self.session.headers.update({
                'Authorization': f'Bearer {self.token}',
                'Content-Type': 'application/json'
            })
    
    # ========================================================================
    # CONNECTION MANAGEMENT
    # ========================================================================
    
    def check_connection(self):
        """Check API connection health"""
        with self.connection_lock:
            try:
                response = self.session.get(
                    f"{self.api_base_url}/api/campaigns",
                    timeout=5
                )
                
                if response.status_code == 401:
                    raise TokenExpiredException("Token expired or invalid")
                
                if response.status_code >= 200 and response.status_code < 500:
                    self.connection_failures = 0
                    self.last_connection_check = time.time()
                    return True
                
                return False
                
            except TokenExpiredException:
                raise
            except Exception:
                self.connection_failures += 1
                return False
    
    def wait_for_connection(self, max_wait=300):
        """Wait for connection to be restored"""
        safe_print("Waiting for connection to be restored...", "🔄", "INFO")
        start_time = time.time()
        attempt = 0
        
        while time.time() - start_time < max_wait and not self.global_stop:
            if check_internet_connection():
                if self.check_connection():
                    safe_print("Connection restored!", "✅", "INFO")
                    return True
            
            delay = exponential_backoff(attempt)
            safe_print(f"Retrying in {int(delay)} seconds...", "⏳", "INFO")
            time.sleep(delay)
            attempt += 1
        
        return False
    
    def api_request(self, method, endpoint, **kwargs):
        """Make API request with retry logic"""
        url = f"{self.api_base_url}{endpoint}"
        max_retries = Config.MAX_RETRIES_API
        
        for attempt in range(max_retries):
            try:
                if time.time() - self.last_connection_check > Config.CONNECTION_CHECK_INTERVAL:
                    if not self.check_connection():
                        if not self.wait_for_connection():
                            raise ConnectionLostException("Failed to restore connection")
                
                if 'timeout' not in kwargs:
                    kwargs['timeout'] = Config.API_TIMEOUT
                
                response = self.session.request(method, url, **kwargs)
                
                if response.status_code == 401:
                    raise TokenExpiredException("Authentication failed")
                
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 60))
                    safe_print(f"Rate limited. Waiting {retry_after}s...", "⏳", "WARNING")
                    time.sleep(retry_after)
                    continue
                
                if response.status_code >= 200 and response.status_code < 300:
                    self.connection_failures = 0
                    return response
                
                if response.status_code >= 400 and response.status_code < 500:
                    return None
                
                if response.status_code >= 500:
                    delay = exponential_backoff(attempt)
                    safe_print(f"Server error {response.status_code}. Retrying...", "⚠️", "WARNING")
                    time.sleep(delay)
                    continue
                
            except TokenExpiredException:
                raise
            except (ConnectionError, Timeout):
                self.connection_failures += 1
                
                if self.connection_failures >= Config.MAX_CONNECTION_FAILURES:
                    if not self.wait_for_connection():
                        raise ConnectionLostException("Failed to restore connection")
                
                delay = exponential_backoff(attempt)
                time.sleep(delay)
                
            except Exception:
                delay = exponential_backoff(attempt)
                time.sleep(delay)
        
        return None
    
    # ========================================================================
    # API METHODS
    # ========================================================================
    
    def get_running_campaigns(self):
        """Get all running campaigns"""
        try:
            response = self.api_request('GET', '/api/campaigns')
            
            if response and response.status_code == 200:
                data = response.json()
                campaigns = data.get('campaigns', [])
                running = [c for c in campaigns if c.get('status') == 'running']
                return running
            
            return []
            
        except TokenExpiredException:
            raise
        except Exception:
            return []
    
    def get_pending_unread_requests(self):
        """Get pending unread check requests"""
        try:
            response = self.api_request('GET', '/api/unread-checker/requests')
            
            if response and response.status_code == 200:
                data = response.json()
                requests = data.get('requests', [])
                pending = [r for r in requests if r.get('status') == 'pending']
                return pending
            
            return []
            
        except TokenExpiredException:
            raise
        except Exception:
            return []
    
    def get_pending_profile_requests(self):
        """Get pending profile opening requests"""
        try:
            
            # Try the new endpoint first
            try:
                direct_response = self.session.get(f"{self.api_base_url}/api/profiles/requests", timeout=10)
                
                if direct_response.status_code == 200:
                    data = direct_response.json()
                    requests = data.get('requests', [])
                    pending = [r for r in requests if r.get('status') == 'pending']
                    return pending
                elif direct_response.status_code == 404:
                    # Endpoint doesn't exist yet - this is expected until server restart
                    safe_print("Profile requests endpoint not available yet (server needs restart)", "ℹ️", "INFO")
                    return []
                else:
                    safe_print(f"Direct API error: {direct_response.status_code} - {direct_response.text[:100]}", "⚠️", "WARNING")
                    return []
            except Exception as e:
                safe_print(f"Direct API request failed: {str(e)}", "⚠️", "WARNING")
                return []
            
        except TokenExpiredException:
            raise
        except Exception as e:
            safe_print(f"Error getting profile requests: {str(e)}", "⚠️", "WARNING")
            return []
    
    def get_pending_firefox_profile_requests(self):
        """Get pending Firefox profile requests"""
        try:
            response = self.api_request('GET', '/api/firefox-profiles/requests')
            
            if response and response.status_code == 200:
                data = response.json()
                requests = data.get('requests', [])
                pending = [r for r in requests if r.get('status') == 'pending']
                return pending
            
            return []
            
        except TokenExpiredException:
            raise
        except Exception:
            return []
    
    def get_campaign_status(self, campaign_id):
        """Check campaign status"""
        try:
            response = self.api_request('GET', f'/api/campaigns/{campaign_id}')
            
            if response and response.status_code == 200:
                campaign = response.json().get('campaign', {})
                return campaign.get('status')
            
            return None
            
        except Exception:
            return None
    
    def get_campaign_data(self, campaign_id):
        """Get campaign data"""
        try:
            response = self.api_request('GET', f'/api/automation/campaign/{campaign_id}')
            
            if response and response.status_code == 200:
                return response.json()
            
            return None
            
        except Exception:
            return None
    
    def update_campaign_progress(self, campaign_id, profile_id=None, recipient=None, 
                                 action=None, message=None, total_sent=None, total_failed=None):
        """Update campaign progress"""
        try:
            data = {
                'action': action,
                'message': message
            }
            
            if profile_id:
                data['profile_id'] = profile_id
            if recipient:
                data['recipient'] = recipient
            if total_sent is not None:
                data['total_sent'] = total_sent
            if total_failed is not None:
                data['total_failed'] = total_failed
                
            response = self.api_request(
                'POST', 
                f'/api/automation/campaign/{campaign_id}/progress',
                json=data
            )
            
            return response is not None
                
        except Exception:
            return False
    
    def get_processed_recipients(self, campaign_id):
        """Get processed recipients"""
        try:
            response = self.api_request(
                'GET',
                f'/api/automation/campaign/{campaign_id}/processed-recipients'
            )
            
            if response and response.status_code == 200:
                data = response.json()
                return data.get('processed_recipients', [])
            
            return []
                
        except Exception:
            return []

    def mark_campaign_completed(self, campaign_id, total_sent, total_failed):
        """Mark campaign as completed"""
        try:
            response = self.api_request(
                'POST',
                f'/api/automation/campaign/{campaign_id}/complete',
                json={
                    'total_sent': total_sent,
                    'total_failed': total_failed
                }
            )
            
            if response and response.status_code == 200:
                safe_print(f"Campaign {campaign_id} marked as completed", "✅", "INFO")
                return True
            
            return False
                
        except Exception:
            return False
    
    def mark_campaign_failed(self, campaign_id, reason):
        """Mark campaign as failed"""
        try:
            response = self.api_request(
                'POST',
                f'/api/automation/campaign/{campaign_id}/fail',
                json={'reason': reason}
            )
            
            return response is not None
                
        except Exception:
            return False
    
    def execute_unread_check(self, request_id, profile_ids=None):
        """Execute unread check for a specific request"""
        try:
            safe_print(f"Starting unread check for request {request_id}", "📬", "INFO")
            
            # Update status to running
            self.update_unread_request_status(request_id, 'running')
            
            # Get active profiles
            response = requests.get(
                f"{self.api_base_url}/api/profiles?page=1&limit=100",
                headers=self.session.headers,
                timeout=30
            )
            
            if response.status_code != 200:
                self.update_unread_request_status(request_id, 'failed', error='Failed to fetch profiles')
                return False
            
            profiles_data = response.json().get('profiles', [])
            active_profiles = [p for p in profiles_data if p.get('is_active', False)]
            
            # Filter by specific profile IDs if provided
            if profile_ids:
                safe_print(f"Filtering profiles by IDs: {profile_ids}", "🔍", "INFO")
                # Handle case where profile_ids might be a string representation of JSON
                try:
                    if isinstance(profile_ids, str):
                        import json
                        profile_ids = json.loads(profile_ids)
                    
                    # Convert profile_ids to integers for comparison
                    profile_ids_int = [int(pid) for pid in profile_ids if pid is not None]
                    active_profiles = [p for p in active_profiles if p['id'] in profile_ids_int]
                    safe_print(f"Filtered to {len(active_profiles)} profiles", "🔍", "INFO")
                except (ValueError, TypeError, json.JSONDecodeError) as e:
                    safe_print(f"Error filtering profiles: {str(e)}", "⚠️", "WARNING")
                    safe_print("Using all active profiles instead", "ℹ️", "INFO")
            
            safe_print(f"Checking {len(active_profiles)} active profile(s)", "📬", "INFO")
            
            results = []
            total_unread = 0
            
            for profile in active_profiles:
                profile_path = profile.get('profile_path')
                profile_name = profile.get('profile_name', 'Unknown')
                
                if not profile_path or not os.path.exists(profile_path):
                    results.append({
                        'profile_name': profile_name,
                        'unread_count': 0,
                        'error': 'Profile path does not exist'
                    })
                    continue
                
                safe_print(f"Checking: {profile_name}", "🔍", "INFO")
                unread_count = self._get_unread_for_profile(profile_path)
                
                results.append({
                    'profile_name': profile_name,
                    'unread_count': unread_count,
                    'error': None
                })
                
                total_unread += unread_count
                
                if unread_count > 0:
                    safe_print(f"  → {unread_count} unread message(s)", "📩", "INFO")
                else:
                    safe_print(f"  → No unread messages", "✅", "INFO")
            
            # Update request with results
            final_results = {
                'success': True,
                'results': results,
                'total_unread': total_unread,
                'profiles_checked': len(results)
            }
            
            self.update_unread_request_status(request_id, 'completed', results=final_results)
            safe_print(f"Unread check completed for request {request_id}", "✅", "SUCCESS")
            
            return True
            
        except Exception as e:
            safe_print(f"Error in unread check: {str(e)}", "❌", "ERROR")
            self.update_unread_request_status(request_id, 'failed', error=str(e))
            return False
    
    def _get_unread_for_profile(self, profile_path):
        """Check unread messages for a single profile"""
        options = Options()
        options.add_argument("--headless")
        options.add_argument("-profile")
        options.add_argument(profile_path)
        options.add_argument("--log-level=3")
        options.set_preference("dom.webdriver.enabled", False)
        options.set_preference('useAutomationExtension', False)
        
        driver = None
        unread = 0
        
        try:
            geckodriver_paths = [
                "geckodriver.exe",
                "C:\\geckodriver\\geckodriver.exe",
                "/usr/local/bin/geckodriver",
                "/usr/bin/geckodriver"
            ]
            
            for path in geckodriver_paths:
                if os.path.exists(path):
                    driver = webdriver.Firefox(options=options)
                    break
            
            if not driver:
                driver = webdriver.Firefox(options=options)
            
            driver.get("https://www.instagram.com")
            time.sleep(6)
            
            try:
                badge = WebDriverWait(driver, 6).until(
                    EC.presence_of_element_located((By.XPATH, "//a[contains(@href, '/direct/inbox')]//span"))
                )
                unread = extract_int(badge.text.strip())
            except:
                unread = 0
                
        except Exception as e:
            safe_print(f"Error checking profile: {str(e)[:50]}", "⚠️", "WARNING")
            unread = 0
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
        
        return unread
    
    def update_unread_request_status(self, request_id, status, results=None, error=None):
        """Update unread check request status"""
        try:
            data = {'status': status}
            if results:
                data['results'] = results
            if error:
                data['error_message'] = error
                
            response = self.api_request(
                'POST',
                f'/api/unread-checker/requests/{request_id}/update',
                json=data
            )
            
            return response is not None
                
        except Exception:
            return False
    
    def execute_profile_request(self, request_id, profile_path, profile_name, request_type='open'):
        """Execute profile opening or closing request"""
        try:
            if request_type == 'open':
                # Check if profile is already open
                if self._is_profile_already_open(profile_path):
                    safe_print(f"Profile {profile_name} is already opened.", "ℹ️", "INFO")
                    self.update_profile_request_status(request_id, 'completed')
                    return True
                
                safe_print(f"Opening profile: {profile_name}", "🦊", "INFO")
                
                # Update status to running
                self.update_profile_request_status(request_id, 'running')
                
                # Open Firefox profile
                options = Options()
                options.add_argument("-profile")
                options.add_argument(profile_path)
                options.set_preference("dom.webdriver.enabled", False)
                options.set_preference('useAutomationExtension', False)
                
                try:
                    driver = webdriver.Firefox(options=options)
                    driver.get("https://www.instagram.com")
                    
                    # Minimize window if on Windows
                    if sys.platform == "win32":
                        try:
                            self._minimize_firefox_windows()
                        except:
                            pass
                    
                    safe_print(f"Profile opened successfully: {profile_name}", "✅", "SUCCESS")
                    self.update_profile_request_status(request_id, 'completed')
                    
                    # Keep the driver alive (don't quit it)
                    return True
                    
                except Exception as e:
                    safe_print(f"Failed to open profile {profile_name}: {str(e)}", "❌", "ERROR")
                    self.update_profile_request_status(request_id, 'failed', error=str(e))
                    return False
                    
            elif request_type == 'close':
                safe_print(f"Closing profile: {profile_name}", "🦊", "INFO")
                
                # Update status to running
                self.update_profile_request_status(request_id, 'running')
                
                try:
                    # Close Firefox processes for this profile
                    if sys.platform == "win32":
                        # Windows: Kill Firefox processes
                        subprocess.run(['taskkill', '/F', '/IM', 'firefox.exe'], 
                                     capture_output=True, text=True)
                    else:
                        # Linux/Mac: Kill Firefox processes
                        subprocess.run(['pkill', '-f', 'firefox'], 
                                     capture_output=True, text=True)
                    
                    safe_print(f"Profile closed successfully: {profile_name}", "✅", "SUCCESS")
                    self.update_profile_request_status(request_id, 'completed')
                    return True
                    
                except Exception as e:
                    safe_print(f"Failed to close profile {profile_name}: {str(e)}", "❌", "ERROR")
                    self.update_profile_request_status(request_id, 'failed', error=str(e))
                    return False
                
        except Exception as e:
            safe_print(f"Error executing profile request: {str(e)}", "❌", "ERROR")
            self.update_profile_request_status(request_id, 'failed', error=str(e))
            return False
    
    def update_profile_request_status(self, request_id, status, error=None):
        """Update profile request status"""
        try:
            data = {'status': status}
            if error:
                data['error_message'] = error
                
            
            # Create a new session without retry logic for status updates
            import requests
            status_session = requests.Session()
            status_session.headers.update({
                'Authorization': f'Bearer {self.token}',
                'Content-Type': 'application/json'
            })
            
            # Use direct request without retry logic
            response = status_session.post(
                f"{self.api_base_url}/api/profiles/requests/{request_id}/update",
                json=data,
                timeout=10
            )
            
            if response.status_code == 200:
                # Remove from processed requests if status is completed or failed
                if status in ['completed', 'failed']:
                    self.processed_requests.discard(request_id)
                return True
            else:
                safe_print(f"Failed to update profile request {request_id}: {response.status_code}", "⚠️", "WARNING")
                return False
                
        except Exception as e:
            safe_print(f"Error updating profile request status: {str(e)}", "❌", "ERROR")
            return False
    
    def execute_firefox_profile_request(self, request_id, request_type, profile_name=None, profile_path=None, is_default=False):
        """Execute Firefox profile request"""
        try:
            safe_print(f"Processing Firefox profile request {request_id} ({request_type})", "🦊", "INFO")
            
            # Update status to running
            self.update_firefox_profile_request_status(request_id, 'running')
            
            profile_manager = FirefoxProfileManager()
            results = None
            success = False
            
            if request_type == 'list':
                safe_print("Listing Firefox profiles...", "📋", "INFO")
                result = profile_manager.list_profiles()
                results = result
                success = True
                
            elif request_type == 'create':
                safe_print(f"Creating Firefox profile: {profile_name}", "➕", "INFO")
                result = profile_manager.create_profile(profile_name, is_default)
                results = result
                success = result.get('success', False)
                
            elif request_type == 'delete':
                safe_print(f"Deleting Firefox profile: {profile_path}", "🗑️", "INFO")
                result = profile_manager.delete_profile(profile_path)
                results = result
                success = result.get('success', False)
                
            elif request_type == 'test':
                safe_print(f"Testing Firefox profile: {profile_path}", "🧪", "INFO")
                result = profile_manager.test_profile(profile_path)
                results = result
                success = result.get('valid', False)
            
            if success:
                self.update_firefox_profile_request_status(request_id, 'completed', results=results)
                safe_print(f"Firefox profile request {request_id} completed successfully", "✅", "SUCCESS")
            else:
                error_msg = results.get('error', 'Unknown error') if isinstance(results, dict) else 'Request failed'
                self.update_firefox_profile_request_status(request_id, 'failed', error=error_msg)
                safe_print(f"Firefox profile request {request_id} failed: {error_msg}", "❌", "ERROR")
            
            return success
            
        except Exception as e:
            safe_print(f"Error executing Firefox profile request: {str(e)}", "❌", "ERROR")
            self.update_firefox_profile_request_status(request_id, 'failed', error=str(e))
            return False
    
    def update_firefox_profile_request_status(self, request_id, status, results=None, error=None):
        """Update Firefox profile request status"""
        try:
            data = {'status': status}
            if results:
                data['results'] = results
            if error:
                data['error_message'] = error
                
            # Create a new session without retry logic for status updates
            import requests
            status_session = requests.Session()
            status_session.headers.update({
                'Authorization': f'Bearer {self.token}',
                'Content-Type': 'application/json'
            })
            
            # Use direct request without retry logic
            response = status_session.post(
                f"{self.api_base_url}/api/firefox-profiles/requests/{request_id}/update",
                json=data,
                timeout=10
            )
            
            if response.status_code == 200:
                # Remove from processed requests if status is completed or failed
                if status in ['completed', 'failed']:
                    self.processed_requests.discard(request_id)
                return True
            else:
                safe_print(f"Failed to update Firefox profile request {request_id}: {response.status_code}", "⚠️", "WARNING")
                return False
                
        except Exception as e:
            safe_print(f"Error updating Firefox profile request status: {str(e)}", "❌", "ERROR")
            return False
    
    # ========================================================================
    # PROFILE MANAGEMENT
    # ========================================================================
    
    def close_campaign_profiles(self, campaign_id):
        """Close profiles for a specific campaign ONLY"""
        with self.campaign_lock:
            if campaign_id not in self.active_campaigns:
                return
            
            campaign_info = self.active_campaigns[campaign_id]
            drivers = campaign_info.get('drivers', [])
            
            if not drivers:
                return
            
            safe_print(f"Closing {len(drivers)} profile(s) for campaign {campaign_id}...", "🔄", "INFO")
            
            closed_count = 0
            
            for driver in drivers[:]:
                try:
                    # Note: We can't easily determine which profile path this driver used
                    # So we'll let the individual profile cleanup handle the tracking
                    driver.quit()
                    closed_count += 1
                except Exception:
                    pass
            
            safe_print(f"Closed {closed_count}/{len(drivers)} profile(s)", "✅", "INFO")
            campaign_info['drivers'] = []
    
    def create_firefox_driver(self, profile_path):
        """Create Firefox driver"""
        # Check if profile is already open first
        if self._is_profile_already_open(profile_path):
            safe_print(f"Profile {profile_path} is already open, attempting to connect to existing instance", "ℹ️", "INFO")
            
            # Try to connect to existing Firefox instance
            try:
                # Create a new driver that connects to the existing Firefox instance
                options = Options()
                options.add_argument("-profile")
                options.add_argument(profile_path)
                options.set_preference("dom.webdriver.enabled", False)
                options.set_preference('useAutomationExtension', False)
                options.add_argument("--connect-existing")  # Try to connect to existing instance
                
                driver = webdriver.Firefox(options=options)
                safe_print(f"Successfully connected to existing profile: {profile_path}", "✅", "SUCCESS")
                return driver
            except Exception as e:
                safe_print(f"Could not connect to existing instance: {str(e)[:50]}", "⚠️", "WARNING")
                safe_print("Will create new instance instead", "ℹ️", "INFO")
        
        # Create new Firefox driver
        options = Options()
        options.add_argument("-profile")
        options.add_argument(profile_path)
        options.set_preference("dom.webdriver.enabled", False)
        options.set_preference('useAutomationExtension', False)
        
        try:
            driver = webdriver.Firefox(options=options)
            
            if sys.platform == "win32":
                try:
                    self._minimize_firefox_windows()
                except:
                    pass
            
            return driver
        except Exception:
            from selenium.webdriver.firefox.service import Service
            
            geckodriver_paths = [
                "geckodriver.exe",
                "C:\\geckodriver\\geckodriver.exe",
                "/usr/local/bin/geckodriver",
                "/usr/bin/geckodriver"
            ]
            
            for path in geckodriver_paths:
                if os.path.exists(path):
                    service = Service(path)
                    return webdriver.Firefox(service=service, options=options)
            
            raise ProfileException("Failed to create Firefox driver")
    
    def _is_profile_already_open(self, profile_path):
        """Check if a Firefox profile is already open"""
        try:
            # Method 1: Check for Firefox processes with this profile path
            if sys.platform == "win32":
                try:
                    result = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq firefox.exe'], 
                                          capture_output=True, text=True, timeout=5)
                    if 'firefox.exe' in result.stdout.lower():
                        # Check if any Firefox process is using this profile
                        try:
                            result = subprocess.run(['wmic', 'process', 'where', 'name="firefox.exe"', 'get', 'commandline'], 
                                                  capture_output=True, text=True, timeout=5)
                            if profile_path in result.stdout:
                                return True
                        except:
                            pass
                except:
                    pass
            
            # Method 2: Try to create a driver with the same profile to see if it's already in use
            options = Options()
            options.add_argument("-profile")
            options.add_argument(profile_path)
            options.set_preference("dom.webdriver.enabled", False)
            options.set_preference('useAutomationExtension', False)
            options.add_argument("--headless")  # Run in headless mode for check
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            
            try:
                # Try to create a driver - if it fails with "profile already in use", it's open
                driver = webdriver.Firefox(options=options)
                driver.quit()  # Close immediately if successful
                return False  # Profile is not in use
            except Exception as e:
                error_msg = str(e).lower()
                if any(keyword in error_msg for keyword in ["profile", "already", "in use", "locked", "busy"]):
                    return True  # Profile is already in use
                return False  # Other error, assume not in use
        except Exception:
            return False  # If we can't determine, assume not open
    
    def _minimize_firefox_windows(self):
        """Minimize Firefox windows (Windows only)"""
        if sys.platform != "win32":
            return
        
        def callback(hwnd, _):
            title = win32gui.GetWindowText(hwnd)
            if "Mozilla Firefox" in title:
                win32gui.ShowWindow(hwnd, win32con.SW_FORCEMINIMIZE)
        
        win32gui.EnumWindows(callback, None)
    
    # ========================================================================
    # MESSAGE SENDING
    # ========================================================================
    
def _set_clipboard_macos(text: str) -> bool:
    """Put UTF-8 text on macOS clipboard using AppKit, fallback to pbcopy."""
    try:
        from AppKit import NSPasteboard, NSPasteboardTypeString  # pip install pyobjc
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(text, NSPasteboardTypeString)
        return True
    except Exception:
        try:
            p = subprocess.Popen(["/usr/bin/pbcopy"], stdin=subprocess.PIPE)
            p.communicate(text.encode("utf-8"))
            return p.returncode == 0
        except Exception:
            return False

    def type_message(driver, element, message: str):
        """
        Paste/insert a message safely (UTF-8) on Windows & macOS.
        - macOS: normalize to NFC, prefer AppKit pasteboard; fallback pbcopy; ⌘V
        - Windows/Linux: Ctrl+V as usual
        - If the target is contenteditable/React-like, try JS insertion first.
        """
        # 1) Normalize text (fix accents/Arabic combining marks)
        message = unicodedata.normalize("NFC", str(message))

        # 2) Ensure focus
        WebDriverWait(driver, 10).until(lambda d: element.is_displayed() and element.is_enabled())
        element.click()
        time.sleep(0.1)

        # 3) Prefer direct JS insert for contenteditable (avoids clipboard issues)
        try:
            is_editable = (element.get_attribute("contenteditable") or "").lower() == "true"
            if is_editable:
                driver.execute_script(
                    """
                    const el = arguments[0], txt = arguments[1];
                    el.focus();
                    // Clear then insert plain text
                    if (window.getSelection && document.createRange) {
                        const sel = window.getSelection();
                        sel.removeAllRanges();
                        const range = document.createRange();
                        range.selectNodeContents(el);
                        sel.addRange(range);
                    }
                    document.execCommand('insertText', false, txt);
                    // Fire input event for React/Vue
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    """,
                    element, message
                )
                return
        except Exception:
            pass  # If JS path fails, fall back to clipboard paste below.

        # 4) Clipboard path
        system = platform.system()
        try:
            if system == "Darwin":  # macOS
                if not _set_clipboard_macos(message):
                    raise RuntimeError("Could not set clipboard on macOS")
                time.sleep(0.1)
                element.send_keys(Keys.COMMAND, "v")
            else:
                # Windows/Linux: keep pyperclip or your existing method
                try:
                    import pyperclip
                    pyperclip.copy(message)
                except Exception:
                    # last-resort: no pyperclip
                    pass
                time.sleep(0.1)
                element.send_keys(Keys.CONTROL, "v")
            time.sleep(0.1)
        except Exception as e:
            print(f"[type_message] Paste failed, last error: {e}")
            # 5) Last fallback: type characters directly (slow but safe)
            try:
                element.clear()
            except Exception:
                pass
            for chunk in message.split("\n"):
                element.send_keys(chunk)
                element.send_keys(Keys.SHIFT, Keys.ENTER)  # keep line breaks without sending

    def send_message(self, driver, user, message, campaign_id, profile_id, counters):
        """Send message to user"""
        try:
            driver.get("https://www.instagram.com/direct/inbox")
            time.sleep(6)

            if "Challenge Required" in driver.page_source:
                safe_print(f"Instagram challenge required", "❌", "ERROR")
                self.update_campaign_progress(campaign_id, profile_id, user, 
                                             "profile_blocked", "Instagram challenge required")
                return False

            try:
                new_message_btn = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, 
                        "//div[contains(@class, 'x6s0dn4') and contains(@class, 'x78zum5') and contains(@class, 'xdt5ytf') and contains(@class, 'xl56j7k')]"))
                )
                new_message_btn.click()
                time.sleep(3)
            except TimeoutException:
                safe_print(f"New message button not found", "⚠️", "WARNING")
                return False
            
            try:
                search_input = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, 
                        "//input[@autocomplete='off' and @placeholder='Search...' and @type='text']"))
                )
                search_input.clear()
                search_input.send_keys(user)
                time.sleep(5)
            except TimeoutException:
                safe_print(f"Search input not found", "❌", "ERROR")
                return False
                
            # Try 3 methods to select user
            user_clicked = False
            
            # Method 1: Exact match
            try:
                safe_print(f"Looking for user: {user}", "🔍", "INFO")
                username_span = WebDriverWait(driver, 12).until(
                    EC.presence_of_element_located((By.XPATH,
                        f"//span[contains(@class, 'x193iq5w') and contains(text(), '{user}')]"))
                )
                WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH,
                        f"//span[contains(@class, 'x193iq5w') and contains(text(), '{user}')]"))
                )
                time.sleep(1)
                username_span.click()
                user_clicked = True
                safe_print(f"Found user: {user} (Method 1)", "✅", "INFO")
            except (TimeoutException, NoSuchElementException):
                safe_print(f"Method 1 failed", "⚠️", "WARNING")

            # Method 2: Click parent container
            if not user_clicked:
                try:
                    safe_print(f"Trying Method 2", "🔍", "INFO")
                    user_element = WebDriverWait(driver, 8).until(
                        EC.element_to_be_clickable((By.XPATH,
                            f"//div[contains(@role, 'button') and .//span[contains(text(), '{user}')]]"))
                    )
                    time.sleep(1)
                    user_element.click()
                    user_clicked = True
                    safe_print(f"Found user: {user} (Method 2)", "✅", "INFO")
                except (TimeoutException, NoSuchElementException):
                    safe_print(f"Method 2 failed", "⚠️", "WARNING")

            # Method 3: Case-insensitive
            if not user_clicked:
                try:
                    safe_print(f"Trying Method 3", "🔍", "INFO")
                    user_element = WebDriverWait(driver, 8).until(
                        EC.element_to_be_clickable((By.XPATH,
                            f"//span[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{user.lower()}')]"))
                    )
                    time.sleep(1)
                    user_element.click()
                    user_clicked = True
                    safe_print(f"Found user: {user} (Method 3)", "✅", "INFO")
                except (TimeoutException, NoSuchElementException):
                    safe_print(f"Method 3 failed", "⚠️", "WARNING")

            if not user_clicked:
                safe_print(f"Username not found: {user}", "❌", "ERROR")
                counters['failed'] += 1
                self.update_campaign_progress(campaign_id, profile_id, user,
                                             "message_failed", "Username not found",
                                             total_failed=counters['failed'])
                return False

            try:
                chat_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, 
                        "//div[@role='button' and contains(text(), 'Chat')]"))
                )
                chat_button.click()
                time.sleep(3)
            except TimeoutException:
                safe_print(f"Chat button not found", "❌", "ERROR")
                counters['failed'] += 1
                self.update_campaign_progress(campaign_id, profile_id, user, 
                                             "message_failed", "Chat button error",
                                             total_failed=counters['failed'])
                return False

            try:
                message_input = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.XPATH, 
                        "//div[@role='textbox' and @aria-label='Message']"))
                )
                
                personalized_message = message.replace("{username}", user)
                self.type_message(message_input, personalized_message)
                safe_print(f"Message typed for: {user}", "✅", "INFO")
                time.sleep(1)
            except TimeoutException:
                safe_print(f"Message input not found", "❌", "ERROR")
                counters['failed'] += 1
                self.update_campaign_progress(campaign_id, profile_id, user, 
                                             "message_failed", "Message input error",
                                             total_failed=counters['failed'])
                return False
            
            try:
                send_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, 
                        "//div[@role='button' and contains(text(), 'Send')]"))
                )
                send_button.click()
            except TimeoutException:
                try:
                    send_button = WebDriverWait(driver, 10).until(
                        EC.element_to_be_clickable((By.XPATH, 
                            "//div[@role='button' and @aria-label='Send']"))
                    )
                    send_button.click()
                except TimeoutException:
                    safe_print(f"Send button not found", "❌", "ERROR")
                    counters['failed'] += 1
                    self.update_campaign_progress(campaign_id, profile_id, user, 
                                                 "message_failed", "Send button error",
                                                 total_failed=counters['failed'])
                    return False
            
            try:
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, 
                        "//*[contains(@aria-label, 'Failed')]"))
                )
                safe_print(f"Message failed: {user}", "❌", "ERROR")
                counters['failed'] += 1
                self.update_campaign_progress(campaign_id, profile_id, user, 
                                             "message_failed", "Instagram rejected",
                                             total_failed=counters['failed'])
                return False
                
            except TimeoutException:
                safe_print(f"Message sent: {user}", "✅", "SUCCESS")
                counters['sent'] += 1
                self.update_campaign_progress(campaign_id, profile_id, user, 
                                             "message_sent", "Success",
                                             total_sent=counters['sent'])
            
            time.sleep(6)
            try:
                dm_link = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, 
                        "//a[contains(@aria-label, 'Direct messaging -')]"))
                )
                dm_link.click()
                time.sleep(2)
                driver.get("https://www.instagram.com")
            except:
                driver.get("https://www.instagram.com")

            return True

        except Exception:
            counters['failed'] += 1
            self.update_campaign_progress(campaign_id, profile_id, user, 
                                         "message_failed", "Error",
                                         total_failed=counters['failed'])
            try:
                driver.get("https://www.instagram.com")
            except:
                pass
            return False

    # ========================================================================
    # PROFILE EXECUTION
    # ========================================================================
    
    def is_driver_alive(self, driver):
        """Check if driver is alive"""
        try:
            _ = driver.current_url
            return True
        except Exception:
            return False
    
    def run_profile(self, profile, users_to_message, campaign_id, profile_id, settings, counters):
        """Run a profile"""
        max_retries = settings.get('max_retries', Config.MAX_RETRIES_PROFILE)
        retry_count = 0
        driver = None
        profile_path = profile['profile_path']

        while retry_count < max_retries:
            if campaign_id not in self.active_campaigns or \
               self.active_campaigns[campaign_id].get('stop', False):
                safe_print(f"Campaign stopped, closing profile", "⚠️", "WARNING")
                break
            
            try:
                if driver is None:
                    # Check if profile is already open and being used by another campaign
                    if profile_path in self.open_profiles:
                        safe_print(f"Profile {profile['profile_name']} is already open and being used by another campaign", "ℹ️", "INFO")
                        safe_print(f"Skipping profile {profile['profile_name']} to avoid conflicts", "⏭️", "INFO")
                        return  # Skip this profile entirely
                    
                    driver = self.create_firefox_driver(profile_path)
                    
                    # Mark profile as open
                    self.open_profiles.add(profile_path)
                    
                    with self.campaign_lock:
                        if campaign_id in self.active_campaigns:
                            self.active_campaigns[campaign_id]['drivers'].append(driver)
                    
                    safe_print(f"Started profile: {profile['profile_name']}", "🚀", "INFO")
                
                processed_recipients = self.get_processed_recipients(campaign_id)
                remaining_users = [u for u in users_to_message if u not in processed_recipients]
                
                safe_print(f"Profile {profile['profile_name']}: {len(remaining_users)} remaining", "📋", "INFO")
                
                if not remaining_users:
                    safe_print(f"No users for {profile['profile_name']}", "⏭️", "INFO")
                else:
                    for user in remaining_users:
                        if campaign_id not in self.active_campaigns or \
                           self.active_campaigns[campaign_id].get('stop', False):
                            break
                        
                        if driver and not self.is_driver_alive(driver):
                            safe_print(f"Profile closed! Restarting...", "🔄", "WARNING")
                            
                            with self.campaign_lock:
                                if campaign_id in self.active_campaigns:
                                    try:
                                        self.active_campaigns[campaign_id]['drivers'].remove(driver)
                                    except:
                                        pass
                            
                            try:
                                driver = self.create_firefox_driver(profile['profile_path'])
                                
                                with self.campaign_lock:
                                    if campaign_id in self.active_campaigns:
                                        self.active_campaigns[campaign_id]['drivers'].append(driver)
                                
                                safe_print(f"Restarted: {profile['profile_name']}", "✅", "SUCCESS")
                            except Exception:
                                raise ProfileException("Restart failed")
                        
                        current_processed = self.get_processed_recipients(campaign_id)
                        if user in current_processed:
                            safe_print(f"Skipping {user} - processed", "⏭️", "INFO")
                            continue
                            
                        success = self.send_message(driver, user, settings['message_template'], 
                                                   campaign_id, profile_id, counters)
                        
                        delay = random.randint(settings['delay_start'], settings['delay_end'])
                        safe_print(f"Waiting {delay // 60} minutes...", "⏳", "INFO")
                        time.sleep(delay)
                
                if driver:
                    with self.campaign_lock:
                        if campaign_id in self.active_campaigns:
                            try:
                                self.active_campaigns[campaign_id]['drivers'].remove(driver)
                            except:
                                pass
                    
                    # Remove profile from open profiles tracking
                    self.open_profiles.discard(profile_path)
                    driver.quit()
                    driver = None
                
                break
                
            except ProfileException:
                retry_count += 1
                
                if driver:
                    try:
                        with self.campaign_lock:
                            if campaign_id in self.active_campaigns:
                                try:
                                    self.active_campaigns[campaign_id]['drivers'].remove(driver)
                                except:
                                    pass
                        # Remove profile from open profiles tracking
                        self.open_profiles.discard(profile_path)
                        driver.quit()
                    except:
                        pass
                    driver = None
                
                if retry_count < max_retries:
                    delay = exponential_backoff(retry_count - 1)
                    safe_print(f"Retrying in {int(delay)}s...", "🔄", "INFO")
                    time.sleep(delay)
                
            except Exception:
                retry_count += 1
        
        if driver:
            try:
                with self.campaign_lock:
                    if campaign_id in self.active_campaigns:
                        try:
                            self.active_campaigns[campaign_id]['drivers'].remove(driver)
                        except:
                            pass
                # Remove profile from open profiles tracking
                self.open_profiles.discard(profile_path)
                driver.quit()
            except:
                pass
    
    # ========================================================================
    # CAMPAIGN EXECUTION
    # ========================================================================
    
    def run_campaign_thread(self, campaign_id):
        """Run campaign in thread"""
        try:
            safe_print(f"Starting campaign {campaign_id}", "🚀", "INFO")
            
            campaign_data = self.get_campaign_data(campaign_id)
            if not campaign_data:
                safe_print(f"Failed to get data", "❌", "ERROR")
                return
            
            campaign = campaign_data['campaign']
            profiles = campaign_data['profiles']
            recipients = campaign_data['recipients']
            
            if not profiles:
                safe_print("No profiles", "❌", "ERROR")
                self.mark_campaign_failed(campaign_id, "No profiles")
                return
            
            if not recipients:
                safe_print("No recipients", "❌", "ERROR")
                self.mark_campaign_failed(campaign_id, "No recipients")
                return
            
            safe_print(f"Campaign: {campaign['name']}", "📊", "INFO")
            safe_print(f"Profiles: {len(profiles)} | Recipients: {len(recipients)}", "📊", "INFO")
            
            self.update_campaign_progress(campaign_id, recipient="campaign_start", 
                                         action="started", message="Started")
            
            counters = {
                'sent': campaign.get('total_sent', 0),
                'failed': campaign.get('total_failed', 0)
            }
            
            processed_recipients = self.get_processed_recipients(campaign_id)
            remaining_recipients = [r for r in recipients if r not in processed_recipients]
            
            safe_print(f"Remaining: {len(remaining_recipients)}", "📋", "INFO")
            
            user_groups = [[] for _ in range(len(profiles))]
            for i, user in enumerate(remaining_recipients):
                profile_index = i % len(profiles)
                user_groups[profile_index].append(user)

            active_threads = []
            
            for i, profile in enumerate(profiles):
                users_for_profile = user_groups[i]
                
                thread = threading.Thread(
                    target=self.run_profile,
                    args=(profile, users_for_profile, campaign_id, 
                          profile['id'], campaign, counters)
                )
                thread.daemon = True
                thread.start()
                active_threads.append(thread)
                
                safe_print(f"Started: {profile['profile_name']}", "🔄", "INFO")
                time.sleep(3)
            
            for thread in active_threads:
                thread.join()
            
            if campaign_id in self.active_campaigns and \
               self.active_campaigns[campaign_id].get('stop', False):
                safe_print(f"Campaign stopped", "⚠️", "WARNING")
            else:
                self.mark_campaign_completed(campaign_id, counters['sent'], counters['failed'])
                safe_print(f"Completed! Sent: {counters['sent']}, Failed: {counters['failed']}", 
                          "✅", "SUCCESS")
        
        except TokenExpiredException:
            safe_print("Token expired", "❌", "ERROR")
            raise
        
        except ConnectionLostException:
            safe_print("Connection lost", "❌", "ERROR")
            self.mark_campaign_failed(campaign_id, "Connection lost")

        except Exception:
            self.mark_campaign_failed(campaign_id, "Error")
        
        finally:
            self.close_campaign_profiles(campaign_id)
            
            with self.campaign_lock:
                if campaign_id in self.active_campaigns:
                    del self.active_campaigns[campaign_id]
    
    # ========================================================================
    # CAMPAIGN MONITORING
    # ========================================================================
    
    def monitor_campaigns(self):
        """Monitor and manage campaigns and unread check requests"""
        safe_print("Starting monitoring for campaigns and unread checks...", "🔄", "INFO")
        safe_print("Press Ctrl+C to stop", "💡", "INFO")
        safe_print("=" * 70, "ℹ️", "INFO")
        
        consecutive_errors = 0
        
        while not self.global_stop:
            try:
                # Check for campaigns
                running_campaigns = self.get_running_campaigns()
                running_campaign_ids = {c['id'] for c in running_campaigns}
                
                with self.campaign_lock:
                    active_campaign_ids = set(self.active_campaigns.keys())
                
                stopped_campaigns = active_campaign_ids - running_campaign_ids
                if stopped_campaigns:
                    safe_print(f"Stopped campaigns: {stopped_campaigns}", "⚠️", "WARNING")
                    
                    for campaign_id in stopped_campaigns:
                        with self.campaign_lock:
                            if campaign_id in self.active_campaigns:
                                self.active_campaigns[campaign_id]['stop'] = True
                        
                        self.close_campaign_profiles(campaign_id)
                
                new_campaigns = running_campaign_ids - active_campaign_ids
                if new_campaigns:
                    safe_print(f"New campaigns: {len(new_campaigns)}", "📊", "INFO")
                    
                    for campaign in running_campaigns:
                        if campaign['id'] in new_campaigns:
                            safe_print(f"Starting: {campaign['name']}", "🚀", "INFO")
                            
                            thread = threading.Thread(
                                target=self.run_campaign_thread,
                                args=(campaign['id'],)
                            )
                            thread.daemon = True
                            thread.start()
                            
                            with self.campaign_lock:
                                self.active_campaigns[campaign['id']] = {
                                    'thread': thread,
                                    'drivers': [],
                                    'stop': False
                                }
                
                # Check for unread check requests
                try:
                    pending_unread_requests = self.get_pending_unread_requests()
                    if pending_unread_requests:
                        safe_print(f"Found {len(pending_unread_requests)} unread check request(s)", "📬", "INFO")
                        
                        for request in pending_unread_requests:
                            safe_print(f"Processing unread check request {request['id']}", "📬", "INFO")
                            
                            # Execute unread check in a separate thread
                            thread = threading.Thread(
                                target=self.execute_unread_check,
                                args=(request['id'], request.get('profile_ids'))
                            )
                            thread.daemon = True
                            thread.start()
                except Exception as e:
                    safe_print(f"Error checking unread requests: {str(e)}", "⚠️", "WARNING")
                
                # Check for profile opening requests
                pending_profile_requests = []
                try:
                    pending_profile_requests = self.get_pending_profile_requests()
                    if pending_profile_requests:
                        safe_print(f"Found {len(pending_profile_requests)} profile opening request(s)", "🦊", "INFO")
                        
                        for request in pending_profile_requests:
                            request_id = request['id']
                            
                            # Skip if already processed
                            if request_id in self.processed_requests:
                                safe_print(f"Skipping already processed request {request_id}", "⏭️", "INFO")
                                continue
                            
                            safe_print(f"Processing profile request {request_id} ({request.get('request_type', 'open')})", "🦊", "INFO")
                            
                            # Mark as being processed
                            self.processed_requests.add(request_id)
                            
                            # Execute profile request in a separate thread
                            thread = threading.Thread(
                                target=self.execute_profile_request,
                                args=(request_id, request.get('profile_path'), request.get('profile_name'), request.get('request_type', 'open'))
                            )
                            thread.daemon = True
                            thread.start()
                except Exception as e:
                    safe_print(f"Error checking profile requests: {str(e)}", "⚠️", "WARNING")
                
                # Check for Firefox profile requests
                pending_firefox_profile_requests = []
                try:
                    pending_firefox_profile_requests = self.get_pending_firefox_profile_requests()
                    if pending_firefox_profile_requests:
                        safe_print(f"Found {len(pending_firefox_profile_requests)} Firefox profile request(s)", "🦊", "INFO")
                        
                        for request in pending_firefox_profile_requests:
                            request_id = request['id']
                            
                            # Skip if already processed
                            if request_id in self.processed_requests:
                                safe_print(f"Skipping already processed Firefox profile request {request_id}", "⏭️", "INFO")
                                continue
                            
                            safe_print(f"Processing Firefox profile request {request_id} ({request.get('request_type')})", "🦊", "INFO")
                            
                            # Mark as being processed
                            self.processed_requests.add(request_id)
                            
                            # Execute Firefox profile request in a separate thread
                            thread = threading.Thread(
                                target=self.execute_firefox_profile_request,
                                args=(request_id, request.get('request_type'), request.get('profile_name'), request.get('profile_path'), request.get('is_default', False))
                            )
                            thread.daemon = True
                            thread.start()
                except Exception as e:
                    safe_print(f"Error checking Firefox profile requests: {str(e)}", "⚠️", "WARNING")
                
                # Cleanup processed requests every 10 cycles to prevent memory buildup
                self.request_cleanup_counter += 1
                if self.request_cleanup_counter >= 10:
                    self.processed_requests.clear()
                    self.request_cleanup_counter = 0
                
                if not running_campaigns and not pending_unread_requests and not pending_profile_requests and not pending_firefox_profile_requests:
                    safe_print("No active campaigns, unread check requests, profile requests, or Firefox profile requests", "⏳", "INFO")
                else:
                    with self.campaign_lock:
                        active_count = len(self.active_campaigns)
                    safe_print(f"Processing {active_count} campaign(s), unread checks, profile requests, and Firefox profile requests", "📊", "INFO")
                
                consecutive_errors = 0
                time.sleep(Config.MONITOR_INTERVAL)
            
            except TokenExpiredException:
                safe_print("Token expired", "❌", "ERROR")
                self.global_stop = True
                break
            
            except KeyboardInterrupt:
                safe_print("Interrupted", "🛑", "INFO")
                self.global_stop = True
                break
            
            except ConnectionLostException:
                safe_print("Connection lost", "⚠️", "WARNING")
                if not self.wait_for_connection():
                    self.global_stop = True
                    break
            
            except Exception:
                consecutive_errors += 1
                safe_print(f"Error ({consecutive_errors}/5)", "❌", "ERROR")
                
                if consecutive_errors >= 5:
                    safe_print("Too many errors", "❌", "ERROR")
                    self.global_stop = True
                    break
                
                delay = exponential_backoff(consecutive_errors - 1)
                time.sleep(delay)
        
        safe_print("Closing profiles...", "🔄", "INFO")
        with self.campaign_lock:
            for campaign_id in list(self.active_campaigns.keys()):
                self.close_campaign_profiles(campaign_id)
        
        safe_print("Monitoring stopped", "✅", "INFO")

# ============================================================================
# UNIFIED HUB MENU SYSTEM
# ============================================================================

class IBotHub:
    """Unified hub for all automation tools"""
    
    def __init__(self, token):
        self.token = token
        self.api_url = Config.API_BASE_URL
        self.automation = None
        self.checker = None
        self.profile_manager = FirefoxProfileManager()
    
    def show_menu(self):
        """Display main menu"""
        while True:
            print("\n" + "=" * 70)
            print("🤖 LeaDMify HUB - Unified Automation Platform v4.0")
            print("=" * 70)
            print("\n📋 Available Tools:")
            print()
            print("  1. 🚀 Campaign Automation (Run campaigns automatically)")
            print("  2. 📬 Check Unread Messages (Check DMs across all profiles)")
            print("  3. 🦊 Firefox Profile Manager (List/test profiles)")
            print("  4. ℹ️  System Information")
            print("  5. 🔄 Refresh Token")
            print("  6. ❌ Exit")
            print()
            print("=" * 70)
            
            choice = input("\n👉 Select an option (1-6): ").strip()
            
            if choice == "1":
                self.run_campaign_automation()
            elif choice == "2":
                self.check_unread_messages()
            elif choice == "3":
                self.manage_profiles()
            elif choice == "4":
                self.show_system_info()
            elif choice == "5":
                self.refresh_token()
            elif choice == "6":
                safe_print("Exiting I-BOT Hub. Goodbye!", "👋", "INFO")
                break
            else:
                safe_print("Invalid option", "⚠️", "WARNING")
    
    def run_campaign_automation(self):
        """Start campaign automation"""
        safe_print("Starting Campaign Automation...", "🚀", "INFO")
        safe_print("Press Ctrl+C to return to menu", "💡", "INFO")
        
        try:
            if not self.automation:
                self.automation = IBotAutomation(token=self.token)
            
            self.automation.monitor_campaigns()
        except KeyboardInterrupt:
            safe_print("\nReturning to menu...", "🔙", "INFO")
            if self.automation:
                self.automation.global_stop = True
    
    def check_unread_messages(self):
        """Check unread messages"""
        safe_print("Checking Unread Messages...", "📬", "INFO")
        
        try:
            if not self.checker:
                self.checker = UnreadMessagesChecker(self.api_url, self.token)
            
            result = self.checker.check_all_profiles()
            
            if result.get('error'):
                safe_print(f"Error: {result['error']}", "❌", "ERROR")
            else:
                print("\n" + "=" * 60)
                print("📬 UNREAD MESSAGES SUMMARY")
                print("=" * 60)
                
                for profile_result in result['results']:
                    profile_name = profile_result['profile_name']
                    unread_count = profile_result['unread_count']
                    
                    if unread_count > 0:
                        print(f"📩 {profile_name}: {unread_count} unread")
                    else:
                        print(f"✅ {profile_name}: No unread")
                
                print("=" * 60)
                print(f"📊 TOTAL: {result['total_unread']}")
                print(f"🔍 CHECKED: {result['profiles_checked']}")
                print("=" * 60)
            
            input("\nPress Enter to continue...")
        except Exception as e:
            safe_print(f"Error: {str(e)[:100]}", "❌", "ERROR")
            input("\nPress Enter to continue...")
    
    def manage_profiles(self):
        """Firefox profile management"""
        print("\n" + "=" * 60)
        print("🦊 FIREFOX PROFILE MANAGER")
        print("=" * 60)
        
        result = self.profile_manager.list_profiles()
        
        if result.get('error'):
            safe_print(f"Error: {result['error']}", "❌", "ERROR")
        else:
            profiles = result['profiles']
            
            if not profiles:
                safe_print("No profiles found", "⚠️", "WARNING")
            else:
                print(f"\n📁 Directory: {result['profiles_dir']}")
                print(f"📊 Total: {len(profiles)}\n")
                
                for i, profile in enumerate(profiles, 1):
                    print(f"{i}. {profile['name']}")
                    print(f"   Path: {profile['path']}")
                    print(f"   Size: {profile['size_mb']} MB\n")
                
                print("Options:")
                print("  1. Test a profile")
                print("  2. Return")
                
                choice = input("\nSelect: ").strip()
                
                if choice == "1":
                    try:
                        num = int(input("Profile number: ").strip())
                        if 1 <= num <= len(profiles):
                            path = profiles[num - 1]['path']
                            test_result = self.profile_manager.test_profile(path)
                            
                            if test_result['valid']:
                                safe_print("Profile is valid!", "✅", "SUCCESS")
                            else:
                                safe_print(f"Invalid: {test_result['error']}", "❌", "ERROR")
                        else:
                            safe_print("Invalid number", "⚠️", "WARNING")
                    except ValueError:
                        safe_print("Invalid input", "⚠️", "WARNING")
        
        input("\nPress Enter to continue...")
    
    def show_system_info(self):
        """Display system info"""
        print("\n" + "=" * 60)
        print("ℹ️  SYSTEM INFORMATION")
        print("=" * 60)
        print(f"\n🔧 Python: {sys.version.split()[0]}")
        print(f"💻 Platform: {sys.platform}")
        print(f"🌐 API: {self.api_url}")
        print(f"🔑 Token: {self.token[:20]}...")
        print(f"📅 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        try:
            response = requests.get(f"{self.api_url}/api/campaigns", 
                                   headers={'Authorization': f'Bearer {self.token}'},
                                   timeout=5)
            if response.status_code == 200:
                safe_print("API: ✅ Connected", "✅", "SUCCESS")
            else:
                safe_print(f"API: ⚠️  HTTP {response.status_code}", "⚠️", "WARNING")
        except Exception:
            safe_print(f"API: ❌ Failed", "❌", "ERROR")
        
        print("=" * 60)
        input("\nPress Enter to continue...")
    
    def refresh_token(self):
        """Refresh token"""
        print("\n" + "=" * 60)
        print("🔄 REFRESH TOKEN")
        print("=" * 60)
        
        new_token = input("\n🔑 Enter new token: ").strip()
        
        if new_token:
            self.token = new_token
            self.automation = None
            self.checker = None
            safe_print("Token updated!", "✅", "SUCCESS")
        else:
            safe_print("Cancelled", "⚠️", "WARNING")
        
        input("\nPress Enter to continue...")

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Main entry point - Fully automated mode"""
    try:
        print("=" * 70)
        print("🤖 LeaDMify HUB v4.0")
        print("Fully Automated Mode")
        print("=" * 70)
        
        # Get token once
        token = input("\n🔑 Enter your authentication token: ").strip()
        
        if not token:
            safe_print("Token required", "❌", "ERROR")
            return
        
        safe_print("Token accepted. Starting fully automated mode...", "✅", "SUCCESS")
        safe_print("Script will run continuously and respond to server requests", "🔄", "INFO")
        safe_print("Press Ctrl+C to stop", "💡", "INFO")
        safe_print("=" * 70, "ℹ️", "INFO")
        
        # Initialize automation directly (no menu)
        automation = IBotAutomation(token=token)
        safe_print("Automation initialized. Monitoring for campaigns...", "🚀", "INFO")
        
        # Start monitoring campaigns (this runs forever)
        automation.monitor_campaigns()
        
    except KeyboardInterrupt:
        safe_print("\n\nUser interrupted. Shutting down gracefully...", "🛑", "INFO")
        if 'automation' in locals():
            automation.global_stop = True
            safe_print("Closing all profiles...", "🔄", "INFO")
            with automation.campaign_lock:
                for campaign_id in list(automation.active_campaigns.keys()):
                    automation.close_campaign_profiles(campaign_id)
        safe_print("Automation stopped successfully.", "✅", "SUCCESS")
    
    except Exception as e:
        safe_print(f"\n\nFatal error: {str(e)[:100]}", "❌", "ERROR")
        safe_print("Please report this error if it persists.", "ℹ️", "INFO")
        sys.exit(1)

if __name__ == "__main__":
    main()
