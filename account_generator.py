import asyncio
import aiohttp
import random
import string
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from fake_useragent import UserAgent
import requests
import json
import os

class DiscordAccountGenerator:
    def __init__(self):
        self.ua = UserAgent()
        self.session = None
        self.driver = None
        self.proxies = []
        
    def setup_driver(self):
        """Setup Chrome driver with stealth settings"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-plugins")
        chrome_options.add_argument(f"--user-agent={self.ua.random}")
        
        # Anti-detection measures
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return True
        except Exception as e:
            print(f"Failed to setup driver: {e}")
            return False
    
    def generate_random_credentials(self):
        """Generate random account credentials"""
        username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=random.randint(8, 12)))
        email_providers = ['gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com']
        email = f"{username}{random.randint(100, 999)}@{random.choice(email_providers)}"
        password = ''.join(random.choices(string.ascii_letters + string.digits + "!@#$%", k=random.randint(12, 16)))
        
        return {
            'username': username,
            'email': email,
            'password': password,
            'display_name': username.capitalize() + str(random.randint(10, 99))
        }
    
    async def get_temp_email(self):
        """Get temporary email for verification"""
        try:
            # Using 1secmail API for temporary emails
            async with aiohttp.ClientSession() as session:
                # Get available domains
                async with session.get('https://www.1secmail.cc/api/v1/?action=getDomainList') as resp:
                    domains = await resp.json()
                
                # Generate random email
                username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
                domain = random.choice(domains)
                temp_email = f"{username}@{domain}"
                
                return {
                    'email': temp_email,
                    'username': username,
                    'domain': domain
                }
        except Exception as e:
            print(f"Failed to get temp email: {e}")
            return None
    
    async def check_email_verification(self, temp_email_data, max_wait=300):
        """Check for Discord verification email"""
        username = temp_email_data['username']
        domain = temp_email_data['domain']
        
        for _ in range(max_wait // 10):
            try:
                async with aiohttp.ClientSession() as session:
                    url = f"https://www.1secmail.com/api/v1/?action=getMessages&login={username}&domain={domain}"
                    async with session.get(url) as resp:
                        messages = await resp.json()
                    
                    for msg in messages:
                        if 'discord' in msg.get('subject', '').lower():
                            # Get full message
                            msg_url = f"https://www.1secmail.com/api/v1/?action=readMessage&login={username}&domain={domain}&id={msg['id']}"
                            async with session.get(msg_url) as resp:
                                full_msg = await resp.json()
                            
                            # Extract verification link
                            if 'textBody' in full_msg:
                                text = full_msg['textBody']
                                # Look for verification link
                                import re
                                verify_link = re.search(r'https://discord\.com/verify[^\s]+', text)
                                if verify_link:
                                    return verify_link.group(0)
                
                await asyncio.sleep(10)
            except Exception as e:
                print(f"Error checking email: {e}")
                await asyncio.sleep(10)
        
        return None
    
    async def get_sms_number(self, service='sms-activate'):
        """Get SMS number for phone verification"""
        # This would integrate with SMS services like SMS-Activate
        # For now, return a placeholder that would need real implementation
        api_key = os.getenv('SMS_ACTIVATE_API_KEY')
        if not api_key:
            print("SMS service API key not found")
            return None
        
        try:
            # SMS-Activate API example
            url = f"https://sms-activate.org/stubs/handler_api.php?api_key={api_key}&action=getNumber&service=ds&country=0"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    response = await resp.text()
                    
                    if response.startswith('ACCESS_NUMBER'):
                        parts = response.split(':')
                        return {
                            'id': parts[1],
                            'number': parts[2]
                        }
            return None
        except Exception as e:
            print(f"Failed to get SMS number: {e}")
            return None
    
    async def get_sms_code(self, sms_data):
        """Get SMS verification code"""
        api_key = os.getenv('SMS_ACTIVATE_API_KEY')
        if not api_key or not sms_data:
            return None
        
        try:
            for _ in range(30):  # Wait up to 5 minutes
                url = f"https://sms-activate.org/stubs/handler_api.php?api_key={api_key}&action=getStatus&id={sms_data['id']}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        response = await resp.text()
                        
                        if response.startswith('STATUS_OK'):
                            return response.split(':')[1]
                        elif response == 'STATUS_WAIT_CODE':
                            await asyncio.sleep(10)
                            continue
                        else:
                            break
            return None
        except Exception as e:
            print(f"Failed to get SMS code: {e}")
            return None
    
    async def solve_captcha(self, site_key, page_url):
        """Solve reCAPTCHA using 2captcha service"""
        api_key = os.getenv('CAPTCHA_API_KEY')
        if not api_key:
            print("CAPTCHA service API key not found")
            return None
        
        try:
            # Submit captcha
            submit_url = "http://2captcha.com/in.php"
            submit_data = {
                'key': api_key,
                'method': 'userrecaptcha',
                'googlekey': site_key,
                'pageurl': page_url
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(submit_url, data=submit_data) as resp:
                    submit_response = await resp.text()
                    
                    if submit_response.startswith('OK|'):
                        captcha_id = submit_response.split('|')[1]
                        
                        # Wait for solution
                        for _ in range(60):  # Wait up to 10 minutes
                            result_url = f"http://2captcha.com/res.php?key={api_key}&action=get&id={captcha_id}"
                            async with session.get(result_url) as resp:
                                result = await resp.text()
                                
                                if result.startswith('OK|'):
                                    return result.split('|')[1]
                                elif result == 'CAPCHA_NOT_READY':
                                    await asyncio.sleep(10)
                                    continue
                                else:
                                    break
            return None
        except Exception as e:
            print(f"Failed to solve captcha: {e}")
            return None
    
    async def create_discord_account(self, credentials, temp_email_data=None, sms_data=None):
        """Create Discord account with provided credentials"""
        if not self.setup_driver():
            return None
        
        try:
            self.driver.get("https://discord.com/register")
            await asyncio.sleep(3)
            
            # Fill registration form
            email_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, "email"))
            )
            email_field.send_keys(temp_email_data['email'] if temp_email_data else credentials['email'])
            
            username_field = self.driver.find_element(By.NAME, "username")
            username_field.send_keys(credentials['username'])
            
            password_field = self.driver.find_element(By.NAME, "password")
            password_field.send_keys(credentials['password'])
            
            # Handle captcha if present
            try:
                captcha_frame = self.driver.find_element(By.CSS_SELECTOR, "iframe[src*='recaptcha']")
                if captcha_frame:
                    site_key = self.driver.execute_script(
                        "return window.___grecaptcha_cfg.clients[0].sitekey"
                    )
                    captcha_solution = await self.solve_captcha(site_key, self.driver.current_url)
                    
                    if captcha_solution:
                        self.driver.execute_script(
                            f"document.getElementById('g-recaptcha-response').innerHTML='{captcha_solution}';"
                        )
            except NoSuchElementException:
                pass
            
            # Submit registration
            register_button = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            register_button.click()
            
            await asyncio.sleep(5)
            
            # Check if email verification is required
            if "verify" in self.driver.current_url.lower():
                if temp_email_data:
                    verify_link = await self.check_email_verification(temp_email_data)
                    if verify_link:
                        self.driver.get(verify_link)
                        await asyncio.sleep(3)
            
            # Check if phone verification is required
            if "phone" in self.driver.current_url.lower() and sms_data:
                phone_field = self.driver.find_element(By.NAME, "phone")
                phone_field.send_keys(sms_data['number'])
                
                submit_btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                submit_btn.click()
                
                # Wait for SMS code
                sms_code = await self.get_sms_code(sms_data)
                if sms_code:
                    code_field = self.driver.find_element(By.NAME, "code")
                    code_field.send_keys(sms_code)
                    
                    verify_btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
                    verify_btn.click()
            
            await asyncio.sleep(5)
            
            # Extract token from localStorage or network requests
            token = self.extract_token()
            
            return {
                'token': token,
                'credentials': credentials,
                'status': 'success' if token else 'partial'
            }
            
        except Exception as e:
            print(f"Account creation failed: {e}")
            return None
        finally:
            if self.driver:
                self.driver.quit()
    
    def extract_token(self):
        """Extract Discord token from browser"""
        try:
            # Method 1: LocalStorage
            token = self.driver.execute_script(
                "return window.localStorage.token"
            )
            if token:
                return token.strip('"')
            
            # Method 2: Network monitoring (would need more complex setup)
            # This is a simplified version
            return None
            
        except Exception as e:
            print(f"Token extraction failed: {e}")
            return None
    
    async def validate_token(self, token):
        """Validate Discord token"""
        try:
            headers = {
                'Authorization': token,
                'Content-Type': 'application/json'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get('https://discord.com/api/v9/users/@me', headers=headers) as resp:
                    if resp.status == 200:
                        user_data = await resp.json()
                        return {
                            'valid': True,
                            'user_id': user_data['id'],
                            'username': user_data['username'],
                            'discriminator': user_data.get('discriminator', '0')
                        }
                    else:
                        return {'valid': False}
        except Exception as e:
            print(f"Token validation failed: {e}")
            return {'valid': False}
    
    async def generate_account(self, use_temp_email=True, use_sms=False):
        """Main method to generate a complete Discord account"""
        print("🔄 Starting account generation...")
        
        # Generate credentials
        credentials = self.generate_random_credentials()
        print(f"Generated credentials for: {credentials['username']}")
        
        # Get temporary email if requested
        temp_email_data = None
        if use_temp_email:
            temp_email_data = await self.get_temp_email()
            if temp_email_data:
                print(f"Got temp email: {temp_email_data['email']}")
        
        # Get SMS number if requested
        sms_data = None
        if use_sms:
            sms_data = await self.get_sms_number()
            if sms_data:
                print(f"Got SMS number: {sms_data['number']}")
        
        # Create account
        result = await self.create_discord_account(credentials, temp_email_data, sms_data)
        
        if result and result['token']:
            # Validate token
            validation = await self.validate_token(result['token'])
            if validation['valid']:
                print(f"✅ Account created successfully: {validation['username']}")
                return {
                    'success': True,
                    'token': result['token'],
                    'user_id': validation['user_id'],
                    'username': validation['username'],
                    'credentials': credentials
                }
            else:
                print("❌ Token validation failed")
                return {'success': False, 'error': 'Invalid token'}
        else:
            print("❌ Account creation failed")
            return {'success': False, 'error': 'Creation failed'}